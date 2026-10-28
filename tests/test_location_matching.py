import unittest
from backend.search.collection import _location_matches as collection_match
from backend.search.retrieval import _location_matches as retrieval_match


class LocationMatchingTests(unittest.TestCase):
    def test_shared_location_policy(self):
        cases = [
            ("Sydney, New South Wales, Australia", ["Sydney NSW"], True),
            ("Parramatta NSW", ["Sydney"], True),
            ("Chatswood, New South Wales", ["Sydney, Australia"], True),
            ("Clayton VIC", ["Melbourne"], True),
            ("Fortitude Valley QLD", ["Brisbane"], True),
            ("Fremantle WA", ["Perth"], True),
            ("Sydney NSW", ["Australia"], True),
            ("Parramatta NSW", ["New South Wales"], True),
            ("Melbourne VIC", ["Sydney"], False),
            ("Sydney, Canada", ["Sydney, Australia"], False),
            ("Sydney NSW", ["Parramatta"], False),
            ("New York, USA", ["New York"], True),
            ("York, UK", ["New York"], False),
            ("Newcastle NSW", ["New York"], False),
            ("London, Canada", ["London, United Kingdom"], False),
            ("Remote - Australia", ["Remote Australia"], True),
            ("Remote - USA", ["Remote Australia"], False),
            ("Remote", ["Remote Australia"], False),
            ("Unknown location", ["Sydney"], False),
            ("", [], True),
            ("Tokyo, Japan", ["Worldwide"], True),
            ("Melbourne VIC", ["Sydney", "Melbourne"], True),
        ]
        for actual, requested, expected in cases:
            with self.subTest(actual=actual, requested=requested):
                self.assertEqual(collection_match(actual, requested), expected)
                self.assertEqual(retrieval_match(actual, requested), expected)
