# Google Jobs via SerpApi: field mapping, safe errors and token paging, with no network.
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from backend.search import board_cooldown, google_jobs
from backend.search.collection import fetch_job_vacancies


def response(payload):
    return io.BytesIO(json.dumps(payload).encode())


PAGE = {
    "jobs_results": [
        {
            "title": "Data Analyst",
            "company_name": "Example Co",
            "location": "Sydney NSW, Australia",
            "description": "Analyse data with SQL.",
            "apply_options": [{"title": "LinkedIn", "link": "https://example.test/apply"}],
            "share_link": "https://google.test/share",
            "detected_extensions": {"posted_at": "2 days ago"},
            "thumbnail": "https://example.test/logo.png",
        }
    ],
    "serpapi_pagination": {"next_page_token": "next"},
}


SYDNEYS = [
    {"name": "Sydney", "canonical_name": "Sydney,Nova Scotia,Canada", "country_code": "CA"},
    {"name": "Sydney", "canonical_name": "Sydney,New South Wales,Australia", "country_code": "AU"},
]


LONDON = [{"name": "London", "canonical_name": "London,England,United Kingdom", "country_code": "GB"}]


class GoogleJobsTests(unittest.TestCase):
    def setUp(self):
        for patcher in (
            patch.dict(os.environ, {"SERPAPI_API_KEY": "secret-key"}),
            patch.dict(google_jobs._LOCATIONS, {}, clear=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_searches_from_the_entered_location(self):
        with patch.object(
            google_jobs, "urlopen", side_effect=[response(SYDNEYS), response(PAGE)]
        ) as call:
            jobs, token = google_jobs.search_page(
                "Data Analyst", "Sydney, Australia", "abc", "au"
            )
        self.assertIn("locations.json?q=Sydney", call.call_args_list[0].args[0])
        url = call.call_args.args[0]
        # The later "Australia" part picks Sydney NSW over Sydney, Nova Scotia.
        self.assertIn("location=Sydney%2CNew+South+Wales%2CAustralia", url)
        self.assertIn("q=Data+Analyst&", url)
        self.assertNotIn("gl=", url)
        self.assertIn("next_page_token=abc", url)
        self.assertEqual(token, "next")
        self.assertEqual(jobs[0]["company"], "Example Co")
        self.assertEqual(jobs[0]["url"], "https://example.test/apply")
        self.assertEqual(jobs[0]["source_platform"], "google")
        self.assertEqual(jobs[0]["posted_at"], "2 days ago")

    def test_an_unknown_place_falls_back_to_the_query_and_country(self):
        with patch.object(
            google_jobs, "urlopen", side_effect=[response([]), response(PAGE)]
        ) as call:
            google_jobs.search_page("Data Analyst", "Nowhere", country="au")
        url = call.call_args.args[0]
        self.assertIn("q=Data+Analyst+Nowhere", url)
        self.assertIn("gl=au", url)

    def test_a_rejected_request_shows_serpapi_reason(self):
        rejected = HTTPError(
            "https://serpapi.com/search", 400, "", {}, io.BytesIO(b'{"error": "Unsupported location."}')
        )
        with patch.object(google_jobs, "urlopen", side_effect=rejected):
            with self.assertRaisesRegex(google_jobs.GoogleJobsError, "HTTP 400\\): Unsupported location"):
                google_jobs.search_page("Analyst")

    def test_errors_never_expose_the_key_and_429_is_a_rate_limit(self):
        with patch.dict(os.environ, {"SERPAPI_API_KEY": ""}):
            with self.assertRaisesRegex(google_jobs.GoogleJobsError, "SERPAPI_API_KEY"):
                google_jobs.search_page("Analyst")
        limited = HTTPError("https://serpapi.com/search?api_key=secret-key", 429, "", {}, None)
        with patch.object(google_jobs, "urlopen", side_effect=limited):
            with self.assertRaises(google_jobs.GoogleJobsError) as caught:
                google_jobs.search_page("Analyst")
        self.assertTrue(board_cooldown.is_rate_limit(caught.exception.args[0]))
        self.assertNotIn("secret-key", str(caught.exception))
        # An empty first page is reported, naming the search; a later empty page just ends paging.
        empty = {"error": "Google hasn't returned any results for this query."}
        with patch.object(google_jobs, "urlopen", return_value=response(empty)):
            with self.assertRaisesRegex(google_jobs.NoResults, "no jobs for 'Analyst'"):
                google_jobs.search_page("Analyst")
        with patch.object(google_jobs, "urlopen", return_value=response(empty)):
            self.assertEqual(google_jobs.search_page("Analyst", token="next"), ([], ""))

    def test_collection_pages_by_token_and_stores_an_absolute_date(self):
        # A full page of 10 tells the collector more pages may follow.
        full = {
            **PAGE,
            "jobs_results": [
                {**PAGE["jobs_results"][0], "location": "London, UK", "title": f"Data Analyst {i}", "apply_options": [{"link": f"https://example.test/{i}"}]}
                for i in range(10)
            ],
        }
        second = {**PAGE, "jobs_results": [{**PAGE["jobs_results"][0], "location": "London, UK", "title": "Data Analyst II", "apply_options": [{"link": "https://example.test/page-two"}]}], "serpapi_pagination": {}}
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "JOB_SEARCH_PROVIDER": "jobspy",
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "0",
                "JOBSPY_DESCRIPTION_CACHE_DIR": directory,
                "JOB_COLLECTION_MAX_BATCHES": "3",
            },
        ), patch.object(
            google_jobs,
            "urlopen",
            side_effect=[response(LONDON), response(full), response(second)],
        ) as call:
            rows = fetch_job_vacancies(
                ["Data Analyst"], ["London"], ["google"], adaptive=True, posted_days_old=7
            )
        # One location lookup (then cached), two pages; the second reuses the token.
        self.assertEqual(call.call_count, 3)
        self.assertIn("next_page_token=next", call.call_args_list[2].args[0])
        self.assertIn("location=London%2CEngland%2CUnited+Kingdom", call.call_args_list[1].args[0])
        self.assertEqual(len(rows), 11)
        self.assertRegex(rows[0]["posted_at"], r"^\d{4}-\d{2}-\d{2}T")


    def test_a_country_google_jobs_does_not_serve_is_skipped_without_a_search(self):
        errors = []
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "JOB_SEARCH_PROVIDER": "jobspy",
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "0",
                "JOBSPY_DESCRIPTION_CACHE_DIR": directory,
            },
        ), patch.object(google_jobs, "urlopen") as call:
            rows = fetch_job_vacancies(
                ["Data Analyst"], ["Sydney"], ["google"], adaptive=True, on_error=errors.append
            )
        call.assert_not_called()
        self.assertEqual(rows, [])
        self.assertIn("not offer job search in AU", errors[0])

if __name__ == "__main__":
    unittest.main()
