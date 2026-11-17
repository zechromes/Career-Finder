"""Bounded collection behavior using synthetic postings and no external calls."""

import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from backend.search import adaptive, jobspy_details
from backend.search.collection import fetch_job_vacancies


def posting(i, **extra):
    return dict(
        title=f"Engineer {i}",
        company=f"Company {i}",
        url=f"https://example.test/jobs/{i}",
        location="Sydney, Australia",
        description="Engineering work",
        source_platform="indeed",
        **extra,
    )


def unique(rows, previous):
    seen = {r["url"] for r in previous}
    result = []
    for row in rows:
        if row["url"] not in seen:
            result.append(row)
            seen.add(row["url"])
    return result


class AdaptiveTests(unittest.TestCase):
    def run_collection(self, streams, cards, **kwargs):
        config = dict(batches=4, details=20, candidates=100, seconds=120)
        config.update(kwargs.pop("config", {}))
        return adaptive.collect(
            streams,
            cards,
            kwargs.pop("hydrate", lambda rows, budget: rows),
            kwargs.pop("early", lambda row: True),
            lambda row: True,
            kwargs.pop("unique", unique),
            config,
            **kwargs,
        )

    def test_visits_boards_before_expanding_best_yield(self):
        calls = []

        def cards(stream, budget):
            calls.append((stream.board, stream.offset))
            rows = [
                posting(f"{stream.board}-{stream.offset+i}") for i in range(stream.size)
            ]
            return (
                rows
                if stream.board == "indeed"
                else [dict(r, description="") for r in rows]
            )

        self.run_collection(
            [adaptive.Stream(b, "Engineer", "Sydney") for b in ["linkedin", "indeed"]],
            cards,
        )
        self.assertEqual(
            calls, [("linkedin", 0), ("indeed", 0), ("indeed", 20), ("indeed", 40)]
        )

    def test_exploration_includes_a_non_title_match(self):
        rows = [
            dict(posting(i), title="Engineer" if i else "Unusual role")
            for i in range(20)
        ]
        selected = adaptive.select_details(rows, ["Engineer"], 4)
        self.assertEqual(len(selected), 4)
        self.assertIn(rows[0], selected)

    def test_filters_before_details_and_caps_candidates(self):
        admitted = []

        def hydrate(rows, budget):
            admitted.extend(rows)
            return rows

        result = self.run_collection(
            [adaptive.Stream("indeed", "Engineer", "Sydney")],
            lambda *_: [posting(i) for i in range(20)],
            hydrate=hydrate,
            early=lambda row: int(row["url"].split("/")[-1]) % 2 == 0,
            config=dict(candidates=3),
        )
        self.assertEqual(len(result), 3)
        self.assertTrue(
            all(int(row["url"].split("/")[-1]) % 2 == 0 for row in admitted)
        )

    def test_known_page_does_not_prevent_find_more(self):
        old = [posting(i) for i in range(20)]
        calls = []

        def cards(stream, budget):
            calls.append(stream.offset)
            return old if not stream.offset else [posting(21)]

        result = self.run_collection(
            [adaptive.Stream("indeed", "Engineer", "Sydney")],
            cards,
            unique=lambda rows, previous: unique(rows, old + previous),
        )
        self.assertEqual(calls, [0, 20])
        self.assertEqual([r["url"] for r in result], [posting(21)["url"]])

    def test_repeated_page_stops_and_deduplicates(self):
        calls = []

        def cards(*_):
            calls.append(1)
            return [posting(i) for i in range(20)]

        result = self.run_collection(
            [adaptive.Stream("indeed", "Engineer", "Sydney")], cards
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(result), 20)

    def test_deadline_and_cancellation(self):
        now = [0]

        def cards(*_):
            now[0] = 121
            return [posting(1)]

        result = self.run_collection(
            [adaptive.Stream("indeed", "Engineer", "Sydney")],
            cards,
            clock=lambda: now[0],
        )
        # The deadline ends search rounds; the checkpoint still reads collected cards.
        self.assertEqual([job["url"] for job in result], [posting(1)["url"]])
        result = self.run_collection(
            [adaptive.Stream("indeed", "Engineer", "Sydney")],
            lambda *_: self.fail("cancelled search fetched"),
            cancelled=lambda: True,
        )
        self.assertEqual(result, [])

    def test_fetch_limit_defers_descriptions_to_the_checkpoint(self):
        def hydrate(rows, budget):
            for row in rows:
                if budget.can_detail():
                    budget.fetch_detail(lambda job: None, row)
                    row["description"] = "Fetched"
            return rows

        result = self.run_collection(
            [adaptive.Stream("indeed", "Engineer", "Sydney")],
            lambda stream, budget: [
                dict(posting(f"{stream.offset}-{i}"), description="") for i in range(3)
            ]
            if stream.offset == 0
            else [],
            hydrate=hydrate,
            config=dict(details=1),
        )
        self.assertEqual(len(result), 3)
        self.assertTrue(all(job["description"] == "Fetched" for job in result))

    def test_search_stops_once_waiting_cards_fill_the_fetch_budget(self):
        calls = []

        def cards(stream, budget):
            calls.append((stream.query, stream.offset))
            return [
                dict(posting(f"{stream.query}-{stream.offset}-{i}"), description="")
                for i in range(stream.size)
            ]

        def hydrate(rows, budget):
            for row in rows:
                if budget.can_detail():
                    budget.fetch_detail(lambda job: None, row)
                    row["description"] = "Fetched"
            return rows

        result = self.run_collection(
            [
                adaptive.Stream("indeed", "Engineer", "Sydney"),
                adaptive.Stream("indeed", "Analyst", "Sydney"),
            ],
            cards,
            hydrate=hydrate,
            config=dict(details=5),
        )
        # The first page fills the 5-fetch budget, but every combination still gets
        # its first page; no second pages; the checkpoint reads every collected card.
        self.assertEqual(calls, [("Engineer", 0), ("Analyst", 0)])
        self.assertEqual(len(result), 40)

    def test_description_budget_still_allows_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = jobspy_details.DescriptionCache(directory)
            cache.put(
                "seek:" + posting(2)["url"], {"description": "Cached description"}
            )
            budget = adaptive.Budget(dict(seconds=120, details=1))
            fetched = []

            def fetch(row):
                fetched.append(row)
                return {"description": "Fetched description"}

            rows = [dict(posting(i), description="") for i in range(3)]
            jobspy_details.hydrate(
                "seek",
                rows,
                cache=cache,
                fetch=lambda row: budget.fetch_detail(fetch, row),
                can_fetch=budget.can_detail,
            )
            self.assertEqual(len(fetched), 1)
            self.assertEqual(rows[2]["description"], "Cached description")
            self.assertFalse(rows[1]["description"])

    def test_web_mode_filters_cards_before_seek_details(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {
                "JOB_SEARCH_PROVIDER": "jobspy",
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "0",
                "JOBSPY_DESCRIPTION_CACHE_DIR": directory,
                "JOB_COLLECTION_MAX_BATCHES": "2",
            },
        ), patch.dict("backend.search.board_cooldown._UNTIL", {}, clear=True), patch(
            "backend.search.seek.collect",
            return_value=[
                dict(posting(1), source_platform="seek", description=""),
                dict(
                    posting(2),
                    source_platform="seek",
                    location="London, UK",
                    description="",
                ),
            ],
        ) as cards, patch(
            "backend.search.seek._request", return_value="html"
        ) as fetch, patch(
            "backend.search.seek.description", return_value="Engineering work"
        ):
            rows = fetch_job_vacancies(
                ["Engineer"], ["Sydney"], ["seek"], adaptive=True, posted_days_old=0
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(fetch.call_count, 1)
            self.assertFalse(cards.call_args.kwargs["fetch_description"])
            self.assertEqual(cards.call_args.kwargs["page_limit"], 1)

    def test_jobspy_offsets_and_combined_batch_budget(self):
        calls = []

        def scrape(**kwargs):
            calls.append(kwargs)
            offset = kwargs.get("offset", 0)
            return pd.DataFrame(
                [
                    dict(
                        title=f"Engineer {i}",
                        company=f"Company {i}",
                        job_url=f"https://example.test/{i}",
                        location="Sydney, Australia",
                        description="Engineering work",
                        site="indeed",
                    )
                    for i in range(offset, offset + 20)
                ]
            )

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {
                "JOB_SEARCH_PROVIDER": "jobspy",
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "0",
                "JOBSPY_DESCRIPTION_CACHE_DIR": directory,
                "JOB_COLLECTION_MAX_BATCHES": "2",
            },
        ), patch.dict("backend.search.board_cooldown._UNTIL", {}, clear=True), patch(
            "jobspy.scrape_jobs", side_effect=scrape
        ):
            rows = fetch_job_vacancies(
                ["Engineer"], ["Sydney"], ["indeed"], adaptive=True, posted_days_old=0
            )
        self.assertEqual([c.get("offset", 0) for c in calls], [0, 20])
        self.assertEqual(len(rows), 40)
        self.assertTrue(all(c["fetch_description"] for c in calls))

    def test_seek_rate_limit_stops_subsequent_detail_requests(self):
        from backend.search.seek import SeekError

        errors = []
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {
                "JOB_SEARCH_PROVIDER": "jobspy",
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "0",
                "JOBSPY_DESCRIPTION_CACHE_DIR": directory,
            },
        ), patch.dict("backend.search.board_cooldown._UNTIL", {}, clear=True), patch(
            "backend.search.seek.collect",
            return_value=[
                dict(posting(i), source_platform="seek", description="")
                for i in range(3)
            ],
        ), patch(
            "backend.search.seek._request",
            side_effect=SeekError(
                "SEEK is temporarily rate-limited. Retry later.", rate_limited=True
            ),
        ) as fetch:
            rows = fetch_job_vacancies(
                ["Engineer"],
                ["Sydney"],
                ["seek"],
                adaptive=True,
                posted_days_old=0,
                on_error=errors.append,
            )
            self.assertEqual(rows, [])
            self.assertEqual(fetch.call_count, 1)
            self.assertTrue(any("rate-limited" in error for error in errors))

    def test_failure_keeps_other_source_results(self):
        errors = []

        def cards(stream, budget):
            if stream.board == "linkedin":
                raise RuntimeError("synthetic source failure")
            return [posting(1)]

        rows = self.run_collection(
            [
                adaptive.Stream(board, "Engineer", "Sydney")
                for board in ["linkedin", "indeed"]
            ],
            cards,
            on_error=errors.append,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(errors), 1)
