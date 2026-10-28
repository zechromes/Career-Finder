"""Synthetic collection/detail tests; external services are always mocked."""

import logging
import tempfile
import unittest
from unittest.mock import Mock, patch
import pandas as pd
from backend.search import jobspy_details as details
from backend.search.collection import fetch_job_vacancies


class JobSpyDetailsTests(unittest.TestCase):
    def setUp(self):
        cooldown = patch.dict("backend.search.board_cooldown._UNTIL", {}, clear=True)
        cooldown.start()
        self.addCleanup(cooldown.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = details.DescriptionCache(self.temp.name)
        env = patch.dict(
            "os.environ",
            {
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "0",
                "JOB_SEARCH_PROVIDER": "jobspy",
                "JOBSPY_SCREEN_POOL_FACTOR": "3",
                "JOBSPY_DESCRIPTION_CACHE_DIR": self.temp.name,
            },
        )
        env.start()
        self.addCleanup(env.stop)

    def test_all_boards_screen_before_loading_descriptions(self):
        for board in ("linkedin", "indeed", "glassdoor"):
            frame = pd.DataFrame(
                [
                    {
                        "title": title,
                        "job_url": f"https://example.test/{i}",
                        "site": board,
                        "description": "Inline" if board == "indeed" else "",
                    }
                    for i, title in enumerate(
                        ["Barista", "Engineer", "Senior Engineer"]
                    )
                ]
            )
            with patch(
                "jobspy.scrape_jobs", return_value=frame
            ) as scrape, patch.object(
                details,
                "hydrate",
                side_effect=lambda board, jobs, *args, **kwargs: jobs,
            ) as hydrate:
                jobs = fetch_job_vacancies(
                    ["Engineer"], ["Sydney"], [board], n_result=1, posted_days_old=0
                )
            self.assertEqual(scrape.call_args.kwargs["results_wanted"], 3)
            self.assertTrue(scrape.call_args.kwargs["fetch_description"])
            self.assertEqual(
                [row["title"] for row in hydrate.call_args.args[1]], ["Engineer"]
            )
            self.assertEqual(len(jobs), 1)

    def test_search_429_forbids_detail_network_on_every_board(self):
        for board, name in [
            ("linkedin", "LinkedIn"),
            ("indeed", "Indeed"),
            ("glassdoor", "Glassdoor"),
        ]:

            def scrape(**kwargs):
                logging.getLogger("JobSpy:" + name).error("response status code 429")
                return pd.DataFrame(
                    [
                        {
                            "title": "Engineer",
                            "job_url": "https://example.test/job",
                            "site": board,
                        }
                    ]
                )

            with patch(
                "jobspy.scrape_jobs", side_effect=scrape
            ) as search, patch.object(details, "hydrate", return_value=[]) as hydrate:
                fetch_job_vacancies(
                    ["Engineer", "Analyst"],
                    ["Sydney"],
                    [board],
                    posted_days_old=0,
                    on_error=Mock(),
                )
            search.assert_called_once()
            self.assertFalse(hydrate.call_args.kwargs["allow_network"])

    def test_inline_cache_and_board_identity(self):
        fetch = Mock()
        job = {"url": "https://example.test/job", "description": "Indeed inline text"}
        details.hydrate("indeed", [job], cache=self.cache, fetch=fetch)
        again = {"url": job["url"]}
        details.hydrate("indeed", [again], cache=self.cache, fetch=fetch)
        self.assertEqual(again["description"], "Indeed inline text")
        fetch.assert_not_called()
        fetch.return_value = {"description": "Glassdoor text"}
        details.hydrate(
            "glassdoor", [{"url": job["url"]}], cache=self.cache, fetch=fetch
        )
        fetch.assert_called_once()

    def test_detail_429_stops_calls_but_keeps_cached_text(self):
        self.cache.put("glassdoor:https://example.test/2", {"description": "Cached"})
        fetch = Mock(side_effect=details.linkedin_details.RateLimited())
        errors = Mock()
        jobs = [{"url": f"https://example.test/{i}"} for i in range(3)]
        details.hydrate(
            "glassdoor", jobs, cache=self.cache, fetch=fetch, on_error=errors
        )
        fetch.assert_called_once()
        self.assertEqual(jobs[2]["description"], "Cached")
        self.assertTrue(any("429" in call.args[0] for call in errors.call_args_list))
        self.assertEqual(errors.call_count, 1)

    def test_blocked_cancellation_and_missing_inline_do_not_fetch(self):
        fetch = Mock()
        details.hydrate(
            "glassdoor",
            [{"url": "https://example.test/1"}],
            cache=self.cache,
            fetch=fetch,
            allow_network=False,
        )
        details.hydrate(
            "glassdoor",
            [{"url": "https://example.test/1"}],
            cache=self.cache,
            fetch=fetch,
            should_cancel=lambda: True,
        )
        fetch.assert_not_called()
        errors = Mock()
        details.hydrate(
            "indeed",
            [{"url": "https://example.test/1"}],
            cache=self.cache,
            on_error=errors,
        )
        errors.assert_called_once()

    def test_glassdoor_adapter_reuses_session_and_surfaces_status(self):
        response = Mock(status_code=429)
        session = Mock()
        session.post.return_value = response
        with self.assertRaises(details.linkedin_details.RateLimited):
            details._CheckedSession(session).post("https://example.test")
        session.post.assert_called_once_with("https://example.test", timeout=30)
        with patch("jobspy.glassdoor.Glassdoor") as factory, patch(
            "jobspy.util.create_session"
        ):
            factory.return_value._fetch_job_description.return_value = "Full posting"
            fetch = details.GlassdoorDetails()
            job = {
                "url": "https://www.glassdoor.com.au/job-listing/j?jl=123",
                "collection_country": "australia",
                "requested_location": "Sydney",
            }
            self.assertEqual(fetch(job)["description"], "Full posting")
            fetch({**job, "url": "https://www.glassdoor.com.au/job-listing/j?jl=456"})
            factory.assert_called_once()
            factory.return_value._get_location.assert_called_once_with("Sydney", False)

    def test_incomplete_descriptions_prevent_collection_reuse(self):
        from pathlib import Path

        directory = Path(self.temp.name) / "collections"
        frame = pd.DataFrame(
            [
                {
                    "title": "Engineer",
                    "job_url": "https://example.test/missing",
                    "site": "indeed",
                    "description": "",
                }
            ]
        )
        errors = []
        with patch.dict(
            "os.environ",
            {
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "900",
                "JOB_COLLECTION_CACHE_DIR": str(directory),
            },
        ), patch("jobspy.scrape_jobs", return_value=frame) as search:
            for _ in range(2):
                rows = fetch_job_vacancies(
                    ["Engineer"],
                    ["Sydney"],
                    ["indeed"],
                    n_result=1,
                    posted_days_old=0,
                    on_error=errors.append,
                )
                self.assertEqual(len(rows), 1)
        self.assertEqual(search.call_count, 2)
        self.assertTrue(errors)
        self.assertEqual(list(directory.glob("*.json")), [])

    def test_screening_configuration_changes_collection_cache_identity(self):
        with patch("backend.search.collection.CollectionCache") as cache:
            cache.return_value.collect.return_value = ([], False)
            fetch_job_vacancies(["Engineer"], ["Sydney"], ["indeed"], posted_days_old=0)
            first = cache.return_value.collect.call_args.args[0]
            with patch.dict("os.environ", {"JOBSPY_SCREEN_POOL_FACTOR": "1"}):
                fetch_job_vacancies(
                    ["Engineer"], ["Sydney"], ["indeed"], posted_days_old=0
                )
            second = cache.return_value.collect.call_args.args[0]
        self.assertEqual(first["screen_pool_factors"], {"indeed": 3})
        self.assertEqual(second["screen_pool_factors"], {"indeed": 1})

    def test_description_progress_distinguishes_cached_ready_and_missing(self):
        self.cache.put(
            "glassdoor:https://example.test/cached", {"description": "Cached text"}
        )
        rows = [
            {"url": "https://example.test/inline", "description": "Inline text"},
            {"url": "https://example.test/cached"},
            {"url": "https://example.test/missing"},
        ]
        statuses = []
        details.hydrate(
            "glassdoor",
            rows,
            cache=self.cache,
            fetch=lambda job: {},
            on_error=Mock(),
            on_status=statuses.append,
        )
        self.assertIn("0/3 checked", statuses[0])
        self.assertIn("3/3 checked, 2 ready (1 cached)", statuses[-1])
        self.assertNotIn("Inline text", " ".join(statuses))

    def test_collection_reports_screening_and_detail_status(self):
        frame = pd.DataFrame(
            [
                {
                    "title": "Engineer",
                    "job_url": "https://example.test/progress",
                    "description": "Inline",
                    "site": "indeed",
                }
            ]
        )
        statuses = []
        with patch("jobspy.scrape_jobs", return_value=frame):
            fetch_job_vacancies(
                ["Engineer"],
                ["Sydney"],
                ["indeed"],
                n_result=1,
                posted_days_old=0,
                on_status=statuses.append,
            )
        self.assertTrue(
            any("collecting job postings" in message for message in statuses)
        )
        self.assertTrue(
            any("screening 1 job titles" in message for message in statuses)
        )
        self.assertIn("1/1 checked, 1 ready (0 cached)", statuses[-1])

    def test_rate_limit_allows_immediate_new_searches(self):
        from backend.search import board_cooldown

        calls = []

        def scrape(**kwargs):
            board = kwargs["site_name"][0]
            calls.append(board)
            if len(calls) == 1:
                logging.getLogger("JobSpy:LinkedIn").error("response status code 429")
            return pd.DataFrame(
                [
                    {
                        "title": "Engineer",
                        "description": "Inline text",
                        "job_url": "https://example.test/cooldown",
                        "site": board,
                    }
                ]
            )

        errors = []
        with patch("jobspy.scrape_jobs", side_effect=scrape):
            fetch_job_vacancies(
                ["Engineer"],
                ["Sydney"],
                ["linkedin"],
                posted_days_old=0,
                on_error=errors.append,
            )
            fetch_job_vacancies(
                ["Engineer"],
                ["Sydney"],
                ["linkedin", "indeed"],
                posted_days_old=0,
                on_error=errors.append,
            )
            self.assertEqual(calls.count("linkedin"), 2)
            self.assertEqual(calls.count("indeed"), 1)
            self.assertEqual(board_cooldown.remaining("linkedin"), 0)
            fetch_job_vacancies(
                ["Engineer"],
                ["Sydney"],
                ["linkedin"],
                posted_days_old=0,
                on_error=errors.append,
            )
            self.assertEqual(calls.count("linkedin"), 3)

    def test_fresh_collection_cache_is_usable_during_cooldown(self):
        from backend.search import board_cooldown
        from pathlib import Path

        frame = pd.DataFrame(
            [
                {
                    "title": "Engineer",
                    "description": "Inline text",
                    "job_url": "https://example.test/cached-posting",
                    "site": "indeed",
                }
            ]
        )
        with patch.dict(
            "os.environ",
            {
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "900",
                "JOB_COLLECTION_CACHE_DIR": str(Path(self.temp.name) / "collections"),
            },
        ), patch("jobspy.scrape_jobs", return_value=frame) as scrape:
            first = fetch_job_vacancies(
                ["Engineer"], ["Sydney"], ["indeed"], posted_days_old=0
            )
            board_cooldown.mark_limited("indeed")
            second = fetch_job_vacancies(
                ["Engineer"], ["Sydney"], ["indeed"], posted_days_old=0
            )
        scrape.assert_called_once()
        self.assertEqual(first, second)

    def test_adaptive_linkedin_rate_limit_reports_one_cause_across_batches(self):
        errors = []
        frame = pd.DataFrame(
            [
                {
                    "title": f"Engineer {i}",
                    "company": f"Company {i}",
                    "job_url": f"https://www.linkedin.com/jobs/view/{10000+i}/",
                    "site": "linkedin",
                    "location": "Sydney, Australia",
                    "description": "",
                }
                for i in range(10)
            ]
        )
        with patch("jobspy.scrape_jobs", return_value=frame) as scrape, patch.object(
            details.linkedin_details, "DescriptionCache", return_value=self.cache
        ), patch.object(
            details.linkedin_details,
            "fetch_details",
            side_effect=details.linkedin_details.RateLimited(),
        ) as fetch:
            rows = fetch_job_vacancies(
                ["Engineer", "Developer"],
                ["Sydney"],
                ["linkedin"],
                adaptive=True,
                posted_days_old=0,
                on_error=errors.append,
            )
        self.assertEqual(rows, [])
        self.assertEqual(scrape.call_count, 1)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("429", errors[0])
