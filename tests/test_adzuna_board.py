# Adzuna as a board alongside the others: country check, paging and messages, no network.
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from backend.search import collection
from backend.search.collection import _country_for_location, fetch_job_vacancies


def page(count, start=0):
    return io.BytesIO(
        json.dumps(
            {
                "results": [
                    {
                        "title": f"Data Analyst {i}",
                        "company": {"display_name": "Example GmbH"},
                        "location": {"display_name": "Berlin, Germany"},
                        "description": "Analyse data with SQL…",
                        "redirect_url": f"https://adzuna.test/{i}",
                    }
                    for i in range(start, start + count)
                ]
            }
        ).encode()
    )


class AdzunaBoardTests(unittest.TestCase):
    def collect(self, location, responses, keys=True, max_batches="2"):
        errors = []
        env = {
            "JOB_SEARCH_PROVIDER": "jobspy",
            "JOB_COLLECTION_CACHE_TTL_SECONDS": "0",
            "JOB_COLLECTION_MAX_BATCHES": max_batches,
            "ADZUNA_APP_ID": "id" if keys else "",
            "ADZUNA_APP_KEY": "key" if keys else "",
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {**env, "JOBSPY_DESCRIPTION_CACHE_DIR": directory}
        ), patch.object(collection, "urlopen", side_effect=responses) as call:
            rows = fetch_job_vacancies(
                ["Data Analyst"], [location], ["adzuna"], adaptive=True, on_error=errors.append
            )
        return rows, errors, call

    def test_country_names_win_and_unknown_places_can_report_none(self):
        self.assertEqual(_country_for_location("Berlin, Germany"), "de")
        self.assertEqual(_country_for_location("Sydney"), "au")
        self.assertIsNone(_country_for_location("Tokyo, Japan", default=None))

    def test_a_covered_country_is_searched_page_by_page(self):
        rows, errors, call = self.collect("Berlin, Germany", [page(50), page(5, 50)])
        urls = [c.args[0].full_url for c in call.call_args_list]
        self.assertIn("/jobs/de/search/1?", urls[0])
        self.assertIn("where=Berlin", urls[0])
        self.assertIn("/jobs/de/search/2?", urls[1])
        self.assertEqual((len(rows), errors), (55, []))
        self.assertEqual(rows[0]["source_platform"], "adzuna")

    def test_requests_per_search_are_capped_for_the_free_tier(self):
        full = lambda start: page(50, start)
        rows, errors, call = self.collect(
            "Berlin, Germany", [full(0), full(50), full(100)], max_batches="5"
        )
        # Default cap of 2 requests, 50 jobs each, even with batches to spare.
        self.assertEqual(call.call_count, 2)
        self.assertIn("results_per_page=50", call.call_args_list[0].args[0].full_url)
        self.assertEqual((len(rows), errors), (100, []))

    def test_an_uncovered_country_gets_a_message_and_no_request(self):
        rows, errors, call = self.collect("Tokyo, Japan", [])
        call.assert_not_called()
        self.assertEqual(rows, [])
        self.assertIn("Adzuna can't search Tokyo, Japan", errors[0])
        self.assertIn("Germany", errors[0])

    def test_missing_keys_are_reported(self):
        rows, errors, call = self.collect("Berlin, Germany", [], keys=False)
        call.assert_not_called()
        self.assertIn("ADZUNA_APP_ID", errors[0])


if __name__ == "__main__":
    unittest.main()
