# Regression coverage for LinkedIn request reduction: shared budget, 429 stop,
# title screening and cached description reuse. All network calls are mocked.
import logging
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from backend.search import linkedin_details
from backend.search.collection import fetch_job_vacancies


def _cards(ids, title="Data Engineer"):
    return pd.DataFrame(
        [
            dict(
                title=title,
                job_url=f"https://www.linkedin.com/jobs/view/{i}",
                site="linkedin",
            )
            for i in ids
        ]
    )


class LinkedInCollectionTests(unittest.TestCase):
    def setUp(self):
        cooldown = patch.dict("backend.search.board_cooldown._UNTIL", {}, clear=True)
        cooldown.start()
        self.addCleanup(cooldown.stop)
        for setting in (
            patch.dict(
                "os.environ",
                {
                    "JOB_COLLECTION_CACHE_TTL_SECONDS": "0",
                    "JOB_SEARCH_PROVIDER": "jobspy",
                    "LINKEDIN_SCREEN_POOL_FACTOR": "3",
                },
            ),
            patch(
                "backend.search.jobspy_details.hydrate",
                side_effect=lambda board, jobs, *args, **kwargs: jobs,
            ),
        ):
            setting.start()
            self.addCleanup(setting.stop)

    def test_linkedin_shares_one_budget_with_descriptions_enabled(self):
        with patch(
            "jobspy.scrape_jobs", side_effect=[_cards(range(4)), _cards(range(4, 20))]
        ) as scrape:
            jobs = fetch_job_vacancies(
                ["Data Engineer", "Analytics Engineer"],
                ["Sydney", "Melbourne"],
                ["linkedin"],
                n_result=2,
                posted_days_old=0,
            )
        # Pool of 2 x 3 cards is filled by two sequential searches, not four parallel ones.
        self.assertEqual(
            [c.kwargs["results_wanted"] for c in scrape.call_args_list], [6, 2]
        )
        self.assertTrue(
            all(c.kwargs["fetch_description"] is True for c in scrape.call_args_list)
        )
        self.assertEqual(len(jobs), 2)

    def test_other_boards_request_optional_descriptions(self):
        with patch("jobspy.scrape_jobs", return_value=pd.DataFrame()) as scrape:
            fetch_job_vacancies(["Engineer"], ["Sydney"], ["indeed"], posted_days_old=0)
        self.assertTrue(scrape.call_args.kwargs["fetch_description"])

    def test_rate_limit_skips_remaining_linkedin_searches(self):
        def limited(**_):
            logging.getLogger("JobSpy:LinkedIn").error(
                "LinkedIn response status code 429"
            )
            return _cards([1])

        errors = []
        with patch("jobspy.scrape_jobs", side_effect=limited) as scrape:
            jobs = fetch_job_vacancies(
                ["Engineer", "Developer", "Analyst"],
                ["Sydney"],
                ["linkedin"],
                posted_days_old=0,
                on_error=errors.append,
            )
        scrape.assert_called_once()
        self.assertEqual(len(jobs), 1)  # Collected results are retained.
        self.assertTrue(any("HTTP 429" in message for message in errors))


class ScreeningAndHydrationTests(unittest.TestCase):
    def test_screen_keeps_best_title_matches_in_board_order(self):
        jobs = [
            {"title": "Sales Manager"},
            {"title": "Senior Data Engineer"},
            {"title": "Barista"},
            {"title": "Data Platform Engineer"},
        ]
        kept = linkedin_details.screen_by_title(jobs, ["Data Engineer"], 2)
        self.assertEqual(
            [j["title"] for j in kept],
            ["Senior Data Engineer", "Data Platform Engineer"],
        )
        self.assertEqual(linkedin_details.screen_by_title(jobs, ["x"], 10), jobs)

    def test_hydrate_reuses_cache_and_stops_after_rate_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = linkedin_details.DescriptionCache(directory, ttl=3600)
            cache.put("1", {"description": "Cached synthetic text"})
            jobs = [
                {
                    "url": f"https://www.linkedin.com/jobs/view/role-{i}",
                    "description": "",
                }
                for i in (1, 2, 3, 4)
            ]
            calls = []

            def fetch(identifier):
                calls.append(identifier)
                if identifier == "3":
                    raise linkedin_details.RateLimited()
                return {"description": f"Fetched {identifier}"}

            with self.assertLogs("JobSpy:LinkedIn", "ERROR"):
                linkedin_details.hydrate(jobs, cache=cache, fetch=fetch)
            self.assertEqual(calls, ["2", "3"])  # No request after the 429.
            self.assertEqual(
                [j["description"] for j in jobs],
                ["Cached synthetic text", "Fetched 2", "", ""],
            )
            self.assertEqual(cache.get("2")["description"], "Fetched 2")

    def test_expired_cache_entries_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            now = [1000.0]
            cache = linkedin_details.DescriptionCache(
                directory, ttl=10, clock=lambda: now[0]
            )
            cache.put("9", {"description": "Synthetic"})
            now[0] += 11
            self.assertIsNone(cache.get("9"))


if __name__ == "__main__":
    unittest.main()
