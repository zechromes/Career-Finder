import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

from backend.search import hyde
from backend.search.hyde import HYDE_PREFIX
from backend.search.ranking import retrieval_queries, retrieval_query_weights

ENTRY = "Data engineer | Built Python ETL pipelines on Airflow | 2024 - Present"
PROFILE = {
    "tech_skills": ["Python", "Airflow"],
    "work_history": [ENTRY],
    "years_of_experience": 2,
    "career_level": "junior",
}
ADS = [
    "Junior Data Engineer. Build Python ETL pipelines on Airflow.",
    "Data Engineer. Maintain Airflow DAGs; 2+ years of Python.",
]


class HydeQueryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patcher = patch.object(hyde, "HYDE_QUERY_CACHE_DIR", Path(directory.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        hyde._FAILED.clear()

    def test_ads_replace_role_queries_and_keep_evidence_queries(self):
        with patch.object(hyde, "_generate", return_value=ADS) as generate:
            weights = retrieval_query_weights(PROFILE, ["Data Engineer"], builder="hyde")
            queries = retrieval_queries(PROFILE, ["Data Engineer"], builder="hyde")
        # The second call reads the disk cache, so queries and weights agree.
        generate.assert_called_once()
        self.assertEqual(queries, list(weights))
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertNotIn("Data Engineer", weights)
        ads = {query: weight for query, weight in weights.items() if query.startswith(HYDE_PREFIX)}
        self.assertEqual(list(ads), [HYDE_PREFIX + ad for ad in ADS])
        evidence = retrieval_query_weights(PROFILE, ["Data Engineer"])
        # The role vote is unchanged in total; the other queries are the evidence builder's.
        self.assertAlmostEqual(sum(ads.values()), evidence["Data Engineer"])
        self.assertEqual(
            {q: w for q, w in weights.items() if q not in ads},
            {q: w for q, w in evidence.items() if q != "Data Engineer"},
        )
        prompt = generate.call_args.args[0]
        self.assertIn("junior", prompt)
        self.assertIn("more than 2 years", prompt)

    def test_searches_use_hyde_when_no_builder_is_configured(self):
        import os

        with patch.dict(os.environ), patch.object(hyde, "_generate", return_value=ADS):
            os.environ.pop("QUERY_BUILDER", None)
            weights = retrieval_query_weights(PROFILE, ["Data Engineer"])
        self.assertIn(HYDE_PREFIX + ADS[0], weights)
        self.assertNotIn("Data Engineer", weights)

    def test_failure_falls_back_to_role_titles_and_is_not_retried_at_once(self):
        with patch.object(hyde, "_generate", side_effect=RuntimeError("down")) as generate:
            weights = retrieval_query_weights(PROFILE, ["Data Engineer"], builder="hyde")
            queries = retrieval_queries(PROFILE, ["Data Engineer"], builder="hyde")
        self.assertEqual(weights, retrieval_query_weights(PROFILE, ["Data Engineer"]))
        self.assertEqual(queries, list(weights))
        generate.assert_called_once()

    def test_ads_asking_for_more_years_than_the_candidate_has_are_dropped(self):
        inflated = "Senior Data Engineer. 5+ years of Airflow required."
        with patch.object(hyde, "_generate", return_value=[inflated, ADS[0]]):
            ads = hyde.job_ads(["Data Engineer"], ["Python"], [ENTRY], years=2)
        self.assertEqual(ads, [ADS[0]])
        with patch.object(hyde, "_generate", return_value=[ADS[1]]):
            # Unknown tenure: any stated number of years is invented.
            self.assertEqual(hyde.job_ads(["Data Engineer"], ["Python"], [ENTRY]), [])

    def test_ads_are_searched_densely_only(self):
        doc = Document(page_content="Python ETL", metadata={"url": "a"})
        store = MagicMock()
        store._collection.count.return_value = 1
        store.similarity_search.return_value = [doc]
        lexical = MagicMock()
        lexical.rank.return_value = [0]
        modules = {
            "langchain_chroma": SimpleNamespace(Chroma=MagicMock(return_value=store)),
            "langchain_openai": SimpleNamespace(OpenAIEmbeddings=MagicMock()),
        }
        ad = HYDE_PREFIX + ADS[0]
        with patch.dict("sys.modules", modules), patch(
            "backend.search.retrieval.corpus", return_value=(["a"], [doc], lexical)
        ), patch("backend.search.retrieval.reciprocal_rank_fusion", return_value=[0]) as fuse:
            from backend.search.retrieval import retrieve_relevant_jobs

            retrieve_relevant_jobs(
                "ignored", "/unused", top_k=0, queries=[ad, "Python"],
                query_weights={ad: 0.6, "Python": 0.4},
            )
        lexical.rank.assert_called_once_with("Python", 1)
        # The ad keeps its whole weight on its one dense ranking.
        self.assertEqual(fuse.call_args.kwargs["weights"], [0.6, 0.2, 0.2])


class AutomaticShortlistTests(unittest.TestCase):
    def retrieve(self, pool_size):
        from backend.search import retrieval

        docs = [Document(page_content=f"job {i}", metadata={"url": f"u{i}"}) for i in range(pool_size)]
        store = MagicMock()
        store._collection.count.return_value = pool_size
        store.similarity_search.return_value = docs
        lexical = MagicMock()
        lexical.rank.return_value = list(range(pool_size))
        modules = {
            "langchain_chroma": SimpleNamespace(Chroma=MagicMock(return_value=store)),
            "langchain_openai": SimpleNamespace(OpenAIEmbeddings=MagicMock()),
        }
        with patch.dict("sys.modules", modules), patch(
            "backend.search.retrieval.corpus",
            return_value=([d.metadata["url"] for d in docs], docs, lexical),
        ), patch.object(retrieval, "AUTO_ALL_UP_TO", 3), patch.object(
            retrieval, "AUTO_LARGE_POOL_TOP_K", 2
        ):
            return retrieval.retrieve_relevant_jobs(
                "ignored", "/unused", top_k=retrieval.AUTO_SHORTLIST, queries=["Python"]
            )

    def test_small_pool_is_evaluated_whole_and_large_pool_is_cut(self):
        self.assertEqual(len(self.retrieve(3)), 3)
        self.assertEqual(len(self.retrieve(4)), 2)


if __name__ == "__main__":
    unittest.main()
