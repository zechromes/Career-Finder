"""Seniority preference changes shortlist order without removing the wider pool."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document
from backend.search.retrieval import retrieve_relevant_jobs
from backend.evaluation.candidate_fit import title_exceeds_candidate_level
from backend.schemas.contracts import Preferences


class SeniorityPriorityTests(unittest.TestCase):
    def retrieve(self, profile, k):
        docs = [
            Document(
                page_content="Python", metadata={"title": title, "url": str(index)}
            )
            for index, title in enumerate(
                [
                    "Senior Developer",
                    "Graduate Developer",
                    "Developer",
                    "Junior/Senior Developer",
                ]
            )
        ]
        store = MagicMock()
        store._collection.count.return_value = len(docs)
        store.similarity_search.return_value = docs
        with patch.dict(
            "sys.modules",
            {
                "langchain_chroma": SimpleNamespace(
                    Chroma=MagicMock(return_value=store)
                ),
                "langchain_openai": SimpleNamespace(OpenAIEmbeddings=MagicMock()),
            },
        ):
            return [
                d.metadata["title"]
                for d in retrieve_relevant_jobs(
                    "profile", top_k=k, candidate_profile=profile
                )
            ]

    def test_prioritizes_before_shortlisting_and_keeps_senior_fallback(self):
        profile = {"career_level": "graduate"}
        # Check the expected behavior: prioritizes before shortlisting and keeps senior fallback.
        self.assertEqual(self.retrieve(profile, 2), ["Graduate Developer", "Developer"])
        self.assertEqual(
            self.retrieve(profile, 0),
            [
                "Graduate Developer",
                "Developer",
                "Junior/Senior Developer",
                "Senior Developer",
            ],
        )
        self.assertEqual(self.retrieve(profile, 4)[-1], "Senior Developer")

    def test_explicit_all_and_unknown_experience_preserve_order(self):
        # Check the expected behavior: explicit all and unknown experience preserve order.
        self.assertEqual(
            self.retrieve(None, 2), ["Senior Developer", "Graduate Developer"]
        )
        self.assertEqual(
            self.retrieve({"career_level": "unknown"}, 2),
            ["Senior Developer", "Graduate Developer"],
        )
        self.assertEqual(Preferences(queries=["Developer"]).seniority, "auto")
        self.assertEqual(
            Preferences(queries=["Developer"], seniority="any").seniority, "any"
        )

    def test_mixed_and_unknown_titles_are_not_demoted(self):
        for title in [
            "Junior/Senior Engineer",
            "Developer",
            "Graduate Engineer",
            "Entry-level intern",
        ]:
            self.assertFalse(
                title_exceeds_candidate_level(
                    title, profile={"career_level": "graduate"}
                )
            )
        # Check the expected behavior: mixed and unknown titles are not demoted.
        self.assertTrue(
            title_exceeds_candidate_level(
                "Senior Engineer", profile={"years_of_experience": 0}
            )
        )
        self.assertFalse(
            title_exceeds_candidate_level(
                "Senior Engineer", profile={"years_of_experience": None}
            )
        )
