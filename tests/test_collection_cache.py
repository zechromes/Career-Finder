"""Collection reuse, expiry, cancellation and failure isolation without live boards."""

import json
import logging
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from backend.search.collection_cache import CollectionCache
from backend.search.collection import fetch_job_vacancies


class CollectionCacheTests(unittest.TestCase):
    def setUp(self):
        cooldown = patch.dict("backend.search.board_cooldown._UNTIL", {}, clear=True)
        cooldown.start()
        self.addCleanup(cooldown.stop)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = Mock(return_value=1000)
        self.cache = CollectionCache(self.temp.name, ttl=60, clock=self.clock)
        self.jobs = [
            {
                "title": "Engineer",
                "description": "Python",
                "url": "https://example.test/1",
            }
        ]
        self.fetch = Mock(side_effect=lambda: (self.jobs.copy(), True))

    def test_reuse_expiry_refresh_and_changed_content(self):
        first, hit = self.cache.collect({"q": "Python"}, self.fetch)
        self.assertFalse(hit)
        second, hit = self.cache.collect({"q": "Python"}, self.fetch)
        self.assertTrue(hit)
        self.assertEqual(first, second)
        self.fetch.assert_called_once()
        self.clock.return_value = 1060
        self.jobs[0]["description"] = "Python and SQL"
        refreshed, hit = self.cache.collect({"q": "Python"}, self.fetch)
        self.assertFalse(hit)
        self.assertEqual(refreshed[0]["description"], "Python and SQL")
        self.cache.collect({"q": "Python"}, self.fetch, force_refresh=True)
        self.assertEqual(self.fetch.call_count, 3)

    def test_nested_feed_snapshot_does_not_extend_source_freshness(self):
        self.jobs[0]["collection_fetched_at"] = 950
        self.cache.collect({}, self.fetch)
        self.clock.return_value = 1011
        self.cache.collect({}, self.fetch)
        self.assertEqual(self.fetch.call_count, 2)

    def test_filters_limits_and_order_are_separate_keys(self):
        for parameters in (
            {"limit": 50},
            {"limit": 100},
            {"remote": True},
            {"roles": ["a", "b"]},
            {"roles": ["b", "a"]},
        ):
            self.cache.collect(parameters, self.fetch)
        self.assertEqual(self.fetch.call_count, 5)

    def test_failures_empty_and_cancellation_are_not_cached(self):
        for result in (([], True), (self.jobs, False)):
            fetch = Mock(return_value=result)
            self.cache.collect({}, fetch)
            self.cache.collect({}, fetch)
            self.assertEqual(fetch.call_count, 2)
        cancelled = threading.Event()

        def fetch():
            cancelled.set()
            return self.jobs, True

        self.assertEqual(self.cache.collect({}, fetch, cancelled.is_set), ([], False))
        self.assertEqual(list(Path(self.temp.name).glob("*.json")), [])

    def test_expired_data_is_not_used_when_refresh_fails(self):
        self.cache.collect({}, self.fetch)
        self.clock.return_value = 1100
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            self.cache.collect({}, Mock(side_effect=RuntimeError("unavailable")))
        self.assertEqual(list(Path(self.temp.name).glob("*.json")), [])

    def test_corrupt_cache_and_unwritable_cache_do_not_fail_collection(self):
        self.cache.collect({}, self.fetch)
        next(Path(self.temp.name).glob("*.json")).write_text("{broken")
        self.cache.collect({}, self.fetch)
        self.assertEqual(self.fetch.call_count, 2)
        blocked = Path(self.temp.name) / "file"
        blocked.write_text("not a directory")
        jobs, hit = CollectionCache(blocked).collect({}, self.fetch)
        self.assertEqual(jobs, self.jobs)
        self.assertFalse(hit)

    def test_identical_concurrent_calls_share_one_collection(self):
        entered, release = threading.Event(), threading.Event()

        def fetch():
            entered.set()
            self.assertTrue(release.wait(3))
            return self.jobs, True

        fetch = Mock(side_effect=fetch)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.cache.collect, {}, fetch)
            self.assertTrue(entered.wait(3))
            second = pool.submit(self.cache.collect, {}, fetch)
            release.set()
            self.assertEqual(first.result()[0], second.result()[0])
        fetch.assert_called_once()

    def test_waiting_search_can_cancel(self):
        entered, release = threading.Event(), threading.Event()

        def fetch():
            entered.set()
            self.assertTrue(release.wait(3))
            return self.jobs, True

        cancelled = threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.cache.collect, {}, fetch)
            self.assertTrue(entered.wait(3))
            second = pool.submit(self.cache.collect, {}, self.fetch, cancelled.is_set)
            cancelled.set()
            self.assertEqual(second.result(timeout=2), ([], False))
            release.set()
            first.result()
        self.fetch.assert_not_called()

    def test_cache_is_bounded(self):
        cache = CollectionCache(self.temp.name, ttl=900, max_entries=2)
        for i in range(4):
            cache.collect({"q": i}, self.fetch)
        self.assertEqual(len(list(Path(self.temp.name).glob("*.json"))), 2)


class CollectionCacheIntegrationTests(unittest.TestCase):
    def setUp(self):
        cooldown = patch.dict("backend.search.board_cooldown._UNTIL", {}, clear=True)
        cooldown.start()
        self.addCleanup(cooldown.stop)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(
            "os.environ",
            {
                "JOB_COLLECTION_CACHE_DIR": self.temp.name,
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "900",
                "JOB_SEARCH_PROVIDER": "jobspy",
            },
        )
        env.start()
        self.addCleanup(env.stop)

    def test_repeated_search_avoids_scraping_and_rechecks_posting_age(self):
        jobs = [
            {
                "title": "Engineer",
                "posted_at": "2026-10-15",
                "url": "https://example.test/1",
            }
        ]
        progress = Mock()
        with patch(
            "backend.search.collection._fetch_job_vacancies_uncached", return_value=jobs
        ) as fetch, patch(
            "backend.search.collection._filter_recent_jobs", side_effect=[jobs, []]
        ):
            self.assertEqual(
                fetch_job_vacancies(["Engineer"], ["Sydney"], ["linkedin"]), jobs
            )
            self.assertEqual(
                fetch_job_vacancies(
                    ["Engineer"], ["Sydney"], ["linkedin"], on_progress=progress
                ),
                [],
            )
        fetch.assert_called_once()
        progress.assert_called_once_with(0)

    def test_logged_jobspy_failure_is_visible_and_not_cached(self):
        logger = logging.getLogger("JobSpy:LinkedIn")

        def partial(*args):
            logger.error("Synthetic response status code 429")
            return [{"title": "Engineer"}]

        errors = Mock()
        with patch(
            "backend.search.collection._fetch_job_vacancies_uncached",
            side_effect=partial,
        ) as fetch:
            for _ in range(2):
                fetch_job_vacancies(
                    ["Engineer"], [], ["linkedin"], posted_days_old=0, on_error=errors
                )
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(errors.call_count, 2)
        self.assertIn(
            "LinkedIn rate-limited the request (HTTP 429)", errors.call_args.args[0]
        )
        self.assertEqual(list(Path(self.temp.name).glob("*.json")), [])


class ScraperWarningTests(unittest.TestCase):
    def test_warning_categories_are_safe_specific_and_deduplicated(self):
        from backend.search.collection import _ScraperFailures

        handler = _ScraperFailures()
        for board, detail in [
            ("LinkedIn", "response status code 429 private-url"),
            ("LinkedIn", "response status code 429 private-url"),
            ("Indeed", "HTTP 403 private-token"),
            ("Glassdoor", "parse failure with private-query and 429 rows"),
        ]:
            handler.handle(
                logging.LogRecord(
                    "JobSpy:" + board, logging.ERROR, "", 0, detail, (), None
                )
            )
        messages = handler.messages()
        self.assertEqual(len(messages), 3)
        self.assertTrue(any("LinkedIn rate-limited" in message for message in messages))
        self.assertTrue(any("Indeed blocked" in message for message in messages))
        self.assertTrue(
            any(
                "Glassdoor reported a request failure" in message
                for message in messages
            )
        )
        self.assertNotIn("private-", " ".join(messages))
