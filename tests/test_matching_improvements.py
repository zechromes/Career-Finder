# Regression coverage for matching improvements; fixtures and assertions document the expected behavior.
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock
from backend.search.ranking import bm25_rank, reciprocal_rank_fusion, retrieval_queries
from backend.schemas.evaluation import RequirementVerdict
from backend.evaluation.evidence import score_requirements
from backend.search.embedding_cache import CachedJobEmbeddings
from backend.search.collection import deduplicate_jobs
from scripts.measure_matching import measure


class MatchingTests(unittest.TestCase):
    def test_multi_query_keeps_roles_skills_and_recent_experience_separate(self):
        queries = retrieval_queries(
            {
                "name": "Private",
                "tech_skills": ["C++", "Python"],
                "work_history": ["Build APIs 2024-Present"],
            },
            ["Developer", "Analyst"],
        )
        # Check the expected behavior: multi query keeps roles skills and recent experience separate.
        self.assertEqual(queries[:2], ["Developer", "Analyst"])
        self.assertIn("C++ Python", queries)
        self.assertIn("Build APIs", queries[-1])
        self.assertNotIn("Private", " ".join(queries))

    def test_bm25_preserves_exact_tools_and_rrf_has_no_duplicate_votes(self):
        # Check the expected behavior: bm25 preserves exact tools and rrf has no duplicate votes.
        self.assertEqual(
            bm25_rank(["C# backend", "C++ robotics", "Python API"], "C++", 3), [1]
        )
        self.assertEqual(reciprocal_rank_fusion([[0, 0, 1], [1, 2]], 3)[0], 1)

    def row(self, **values):
        fields = dict(
            requirement="Python",
            importance="must_have",
            verdict="met",
            job_quote="Python required",
            resume_quote="Built Python APIs",
        )
        return RequirementVerdict(**(fields | values))

    def test_score_uses_quotes_and_not_model_number(self):
        score, category, _, rows = score_requirements(
            [self.row()], "Built Python APIs", "Python required"
        )
        # Check the expected behavior: score uses quotes and not model number.
        self.assertEqual((score, category), (100, "strong_match"))
        score, category, _, rows = score_requirements(
            [self.row(resume_quote="Invented")], "Built Python APIs", "Python required"
        )
        self.assertEqual(category, "review")
        self.assertEqual(rows[0]["verdict"], "unknown")

    def test_absence_cannot_cause_hard_rejection(self):
        result = score_requirements(
            [self.row(verdict="not_met", resume_quote="")],
            "Built APIs",
            "Python required",
        )
        # Check the expected behavior: absence cannot cause hard rejection.
        self.assertEqual(result[1], "review")
        self.assertEqual(score_requirements([], "", "")[:2], (None, "review"))

    def test_invalid_job_quote_cannot_earn_credit(self):
        # Check the expected behavior: invalid job quote cannot earn credit.
        self.assertEqual(
            score_requirements(
                [self.row()], "Built Python APIs", "No requirements listed"
            )[:2],
            (None, "review"),
        )

    def test_embedding_cache_reuses_content_but_not_candidate_queries(self):
        with TemporaryDirectory() as directory:
            delegate = MagicMock()
            delegate.embed_documents.return_value = [[1.0, 2.0]]
            cache = CachedJobEmbeddings(delegate, directory)
            self.assertEqual(
                cache.embed_documents(["same", "same"]), [[1.0, 2.0], [1.0, 2.0]]
            )
            cache.embed_documents(["same"])
            delegate.embed_documents.assert_called_once_with(["same"])
            cache.embed_query("private candidate")
            delegate.embed_query.assert_called_once_with("private candidate")
            cache.embed_documents(["changed"])
            self.assertEqual(delegate.embed_documents.call_count, 2)

    def test_cross_board_duplicates_require_matching_identity_and_description(self):
        base = dict(
            company="Example",
            title="Engineer",
            location="Sydney",
            description="Build Python APIs and distributed systems. " * 5,
        )
        # Check the expected behavior: cross board duplicates require matching identity and description.
        self.assertEqual(
            len(
                deduplicate_jobs(
                    [base | {"url": "https://a/1"}, base | {"url": "https://b/2"}]
                )
            ),
            1,
        )
        self.assertEqual(
            len(deduplicate_jobs([base, base | {"location": "Melbourne"}])), 2
        )

    def test_metrics_report_missed_matches_and_unlabeled_predictions(self):
        result = measure(
            [
                dict(
                    query_id="q",
                    labels={"a": True, "b": True, "c": False},
                    shortlist=["a", "c"],
                    predicted_strong=["a", "c", "d"],
                )
            ]
        )[0]
        # Check the expected behavior: metrics report missed matches and unlabeled predictions.
        self.assertEqual(result["observed_recall_at_k"], 0.5)
        self.assertEqual(result["strong_match_precision_on_labeled"], 0.5)
        self.assertEqual(result["missed_labeled_strong"], ["b"])
        self.assertEqual(result["unlabeled_strong_count"], 1)

    def test_hybrid_retrieval_adds_lexical_matches_and_restores_originals(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from langchain_core.documents import Document
        from backend.search.retrieval import retrieve_relevant_jobs

        documents = [
            Document(
                page_content="Python APIs",
                metadata={"url": "a", "original_content": "Full Python job"},
            ),
            Document(
                page_content="C++ robotics",
                metadata={"url": "b", "original_content": "Full robotics job"},
            ),
        ]
        store = MagicMock()
        store._collection.count.return_value = 2
        store.get.return_value = {
            "ids": ["a", "b"],
            "documents": [d.page_content for d in documents],
            "metadatas": [d.metadata for d in documents],
        }
        store.similarity_search.return_value = [documents[0]]
        with patch.dict(
            "sys.modules",
            {
                "langchain_chroma": SimpleNamespace(
                    Chroma=MagicMock(return_value=store)
                ),
                "langchain_openai": SimpleNamespace(OpenAIEmbeddings=MagicMock()),
            },
        ):
            result = retrieve_relevant_jobs("ignored", top_k=0, queries=["C++"])
        # Check the expected behavior: hybrid retrieval adds lexical matches and restores originals.
        self.assertEqual(
            {d.page_content for d in result}, {"Full Python job", "Full robotics job"}
        )
        store.similarity_search.assert_called_once_with("C++", k=2)
