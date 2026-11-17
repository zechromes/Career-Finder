# Regression coverage for jobspy migration; fixtures and assertions document the expected behavior.
import unittest
from unittest.mock import MagicMock, patch
from datetime import date
import pandas as pd
from backend.search.collection import fetch_job_vacancies, _jobspy_countries


class JobSpyMigrationTests(unittest.TestCase):
    def setUp(self):
        cache_setting = patch.dict(
            "os.environ",
            {
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "0",
                "JOBSPY_SCREEN_POOL_FACTOR": "1",
                "JOBSPY_DESCRIPTION_CACHE_TTL_SECONDS": "0",
            },
        )
        cache_setting.start()
        self.addCleanup(cache_setting.stop)

    def test_normalizes_missing_cells_dates_direct_links_and_multiple_queries(self):
        frame = pd.DataFrame(
            [
                dict(
                    title="Engineer",
                    company=float("nan"),
                    location="Sydney",
                    description=float("nan"),
                    company_logo=pd.NA,
                    date_posted=date(2026, 10, 5),
                    job_url_direct=None,
                    job_url="https://example.test/job",
                    site="linkedin",
                )
            ]
        )
        errors = []
        with patch("jobspy.scrape_jobs", return_value=frame) as scrape, patch.dict(
            "os.environ", {"JOB_SEARCH_PROVIDER": "jobspy", "APIFY_API_KEY": ""}
        ):
            jobs = fetch_job_vacancies(
                ["Engineer", "Developer"],
                ["Sydney"],
                ["linkedin"],
                posted_days_old=0,
                on_error=errors.append,
            )
        self.assertTrue(
            any("descriptions are unavailable" in message for message in errors)
        )
        # Check the expected behavior: normalizes missing cells dates direct links and multiple queries.
        self.assertEqual(scrape.call_count, 2)
        self.assertEqual(
            {c.kwargs["search_term"] for c in scrape.call_args_list},
            {"Engineer", "Developer"},
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Unknown Company")
        self.assertEqual(jobs[0]["description"], "")
        self.assertEqual(jobs[0]["company_logo"], "")
        self.assertEqual(jobs[0]["posted_at"], "2026-10-05")
        self.assertEqual(jobs[0]["url"], "https://example.test/job")

    def test_country_selection_and_worldwide_coverage(self):
        # Check the expected behavior: country selection and worldwide coverage.
        self.assertEqual(_jobspy_countries("Sydney", "indeed"), ["australia"])
        self.assertEqual(_jobspy_countries("Berlin, Germany", "indeed"), ["germany"])
        self.assertEqual(_jobspy_countries("London, UK", "indeed"), ["uk"])
        self.assertIn("japan", _jobspy_countries("Worldwide", "indeed"))
        with patch("jobspy.scrape_jobs", return_value=pd.DataFrame()) as scrape:
            fetch_job_vacancies(["Engineer"], [], ["indeed"], posted_days_old=0)
        self.assertEqual(
            {c.kwargs["country_indeed"] for c in scrape.call_args_list},
            set(_jobspy_countries("Worldwide", "indeed")),
        )
        self.assertTrue(
            all(c.kwargs["location"] is None for c in scrape.call_args_list)
        )

    def test_direct_seek_without_apify_and_other_board_failure_is_partial(self):
        errors = []
        rows = [
            dict(
                title="Engineer",
                company="Example",
                location="Sydney",
                description="Python engineering",
                url="https://www.seek.com.au/job/1",
                source_platform="seek",
                posted_at="",
            )
        ]
        with patch("jobspy.scrape_jobs", side_effect=RuntimeError("blocked")), patch(
            "backend.search.seek.collect", return_value=rows
        ) as collect, patch.dict(
            "os.environ", {"JOB_SEARCH_PROVIDER": "jobspy", "APIFY_API_KEY": ""}
        ):
            jobs = fetch_job_vacancies(
                ["Engineer"],
                ["Sydney"],
                ["linkedin", "seek"],
                posted_days_old=0,
                on_error=errors.append,
            )
        self.assertEqual(collect.call_args.args, ("Engineer", "Sydney"))
        self.assertEqual(jobs[0]["source_platform"], "seek")
        self.assertEqual(len(errors), 1)

    def test_remote_indeed_uses_local_date_filter_and_cancellation_skips_calls(self):
        with patch("jobspy.scrape_jobs", return_value=pd.DataFrame()) as scrape:
            fetch_job_vacancies(
                ["Engineer"], ["Sydney"], ["indeed"], remote=True, posted_days_old=7
            )
            self.assertNotIn("hours_old", scrape.call_args.kwargs)
            self.assertTrue(scrape.call_args.kwargs["is_remote"])
            scrape.reset_mock()
            fetch_job_vacancies(
                ["Engineer"], ["Sydney"], ["linkedin"], should_cancel=lambda: True
            )
            scrape.assert_not_called()

    def test_worldwide_board_budget_caps_overdelivery_and_stops_searching(self):
        for site in ("indeed",):
            with self.subTest(site=site):
                frame = pd.DataFrame(
                    [
                        dict(
                            title="Engineer",
                            job_url=f"https://example.test/{i}",
                            description="Synthetic description",
                        )
                        for i in range(100)
                    ]
                )
                progress = []
                with patch(
                    "jobspy.scrape_jobs", return_value=frame
                ) as scrape, patch.dict(
                    "os.environ", {"JOB_SEARCH_PROVIDER": "jobspy"}
                ):
                    jobs = fetch_job_vacancies(
                        ["Engineer", "Developer"],
                        [],
                        [site],
                        n_result=5,
                        posted_days_old=0,
                        on_progress=progress.append,
                    )
                self.assertEqual(len(jobs), 5)
                scrape.assert_called_once()
                self.assertEqual(scrape.call_args.kwargs["results_wanted"], 5)
                self.assertEqual(progress, [5])

    def test_board_budget_is_shared_and_duplicate_jobs_do_not_consume_it(self):
        for site in ("indeed",):
            with self.subTest(site=site):
                batches = [
                    pd.DataFrame(
                        [
                            dict(
                                title="Engineer",
                                job_url=f"https://example.test/{i}",
                                description="Synthetic description",
                            )
                            for i in ids
                        ]
                    )
                    for ids in ([1, 2], [2, 3], [4])
                ]
                with patch(
                    "jobspy.scrape_jobs", side_effect=batches
                ) as scrape, patch.dict(
                    "os.environ", {"JOB_SEARCH_PROVIDER": "jobspy"}
                ):
                    jobs = fetch_job_vacancies(
                        ["Engineer", "Developer", "Analyst", "Architect"],
                        ["Sydney"],
                        [site],
                        n_result=4,
                        posted_days_old=0,
                    )
                self.assertEqual(len(jobs), 4)
                self.assertEqual(
                    [c.kwargs["results_wanted"] for c in scrape.call_args_list],
                    [4, 2, 1],
                )
