# Regression coverage for worldwide search; fixtures and assertions document the expected behavior.
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from backend.search.collection import (
    ADZUNA_COUNTRIES,
    _location_matches,
    fetch_job_vacancies,
)


class WorldwideSearchTests(unittest.TestCase):
    def setUp(self):
        cache_setting = patch.dict(
            "os.environ", {"JOB_COLLECTION_CACHE_TTL_SECONDS": "0"}
        )
        cache_setting.start()
        self.addCleanup(cache_setting.stop)

    def test_empty_location_uses_global_scraper_input_and_keeps_foreign_jobs(self):
        import pandas as pd

        frame = pd.DataFrame(
            [
                {
                    "title": "Engineer",
                    "company": "Example",
                    "location": "Tokyo",
                    "description": "Python required.",
                    "job_url": "https://example.test/job",
                }
            ]
        )
        with patch("jobspy.scrape_jobs", return_value=frame) as scrape, patch.dict(
            "os.environ", {"JOB_SEARCH_PROVIDER": "jobspy", "APIFY_API_KEY": ""}
        ):
            jobs = fetch_job_vacancies(
                ["Engineer"], [], ["linkedin"], posted_days_old=0
            )
        # Check the expected behavior: empty location uses global scraper input and keeps foreign jobs.
        self.assertIsNone(scrape.call_args.kwargs["location"])
        self.assertEqual(jobs[0]["location"], "Tokyo")
        self.assertFalse(_location_matches("Tokyo", ["Sydney"]))
        self.assertTrue(_location_matches("", ["Worldwide"]))

    def test_adzuna_worldwide_queries_country_indexes_without_where(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"results": []}
        ).encode()
        with patch(
            "backend.search.collection.urlopen", return_value=response
        ) as request, patch.dict(
            "os.environ",
            {
                "JOB_SEARCH_PROVIDER": "adzuna",
                "ADZUNA_APP_ID": "test",
                "ADZUNA_APP_KEY": "test",
            },
        ):
            fetch_job_vacancies(["Engineer"], [], ["linkedin"], posted_days_old=0)
        urls = [urlparse(call.args[0].full_url) for call in request.call_args_list]
        # Check the expected behavior: adzuna worldwide queries country indexes without where.
        self.assertEqual(
            {url.path.split("/")[4] for url in urls}, set(ADZUNA_COUNTRIES)
        )
        self.assertTrue(all("where" not in parse_qs(url.query) for url in urls))
