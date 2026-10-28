import unittest
from pydantic import ValidationError
from backend.schemas.contracts import Preferences
from backend.search.collection import fetch_job_vacancies


class RetiredSourcesTests(unittest.TestCase):
    def test_saved_mixed_sources_keep_supported_boards(self):
        prefs = Preferences(
            queries=["Engineer"], platforms=["greenhouse", "indeed", "lever"]
        )
        self.assertEqual(prefs.platforms, ["indeed"])

    def test_feed_only_preferences_require_a_board(self):
        with self.assertRaisesRegex(
            ValidationError, "Select at least one supported job board"
        ):
            Preferences(queries=["Engineer"], platforms=["greenhouse", "lever"])

    def test_direct_feed_only_collection_does_not_make_requests(self):
        with self.assertRaisesRegex(
            ValueError, "Select at least one supported job board"
        ):
            fetch_job_vacancies(["Engineer"], [], ["greenhouse", "lever"])
