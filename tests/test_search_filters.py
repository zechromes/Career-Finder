import unittest
from backend.search.filters import work_arrangement, matches_seniority


class SearchFilterTests(unittest.TestCase):
    def test_remote_is_work_arrangement_not_an_arbitrary_keyword(self):
        for text in [
            "This is not a remote role.",
            "Build remote control systems.",
            "Remote working is not available.",
        ]:
            with self.subTest(text=text):
                self.assertNotEqual(work_arrangement({"description": text}), "remote")
        self.assertEqual(
            work_arrangement({"description": "A fully remote role."}), "remote"
        )
        self.assertEqual(
            work_arrangement({"description": "Hybrid working with two office days."}),
            "hybrid",
        )
        self.assertEqual(
            work_arrangement({"description": "Office-based role."}), "on-site"
        )
        self.assertEqual(
            work_arrangement({"description": "Build software."}), "unknown"
        )

    def test_explicit_seniority_uses_boundaries_and_preserves_unmarked_possibilities(
        self,
    ):
        self.assertTrue(matches_seniority("Software Engineer", "entry"))
        self.assertTrue(matches_seniority("Software Engineer", "mid"))
        self.assertFalse(matches_seniority("Senior Engineer", "entry"))
        self.assertTrue(matches_seniority("Sr. Engineer", "senior"))
        self.assertFalse(matches_seniority("Seniority analyst", "senior"))
