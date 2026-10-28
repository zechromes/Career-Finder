"""Processing modules share the canonical schema classes."""

import importlib
import unittest


class BackendLayoutTests(unittest.TestCase):
    def test_processing_models_are_the_canonical_schemas(self):
        symbols = [
            ("profiles.extraction", "schemas.resume", "ResumeProfile"),
            ("profiles.storage", "schemas.saved_profiles", "SavedProfile"),
            ("profiles.storage", "schemas.saved_profiles", "SavedProfileInput"),
            ("evaluation.providers", "schemas.evaluation", "JobEvaluation"),
            ("evaluation.evidence", "schemas.evaluation", "RequirementVerdict"),
        ]
        for legacy, canonical, symbol in symbols:
            with self.subTest(legacy=legacy, symbol=symbol):
                self.assertIs(
                    getattr(importlib.import_module("backend." + legacy), symbol),
                    getattr(importlib.import_module("backend." + canonical), symbol),
                )
