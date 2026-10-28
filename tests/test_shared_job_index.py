"""Real local Chroma with deterministic fake embeddings, isolated temporary storage."""

from collections import Counter
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from langchain_core.documents import Document

from backend.search.shared_index import publish, read_scope, corpus, _CORPORA
from backend.search.retrieval import retrieve_relevant_jobs
from backend.search.ranking import BM25Index, tokens


class Embeddings:
    def __init__(self):
        self.embedded = []

    def embed_documents(self, texts):
        self.embedded.extend(texts)
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return [float("Python" in text), float("SQL" in text), 0.1]


class SharedIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(
            "os.environ",
            {
                "JOB_INDEX_DIR": str(self.root / "index"),
                "ANONYMIZED_TELEMETRY": "False",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        self.embeddings = Embeddings()
        self.embed_patch = patch(
            "langchain_openai.OpenAIEmbeddings", return_value=self.embeddings
        )
        self.embed_patch.start()
        self.addCleanup(self.embed_patch.stop)
        _CORPORA.clear()

    def doc(self, url="https://example.test/a", text="Python APIs"):
        return Document(
            page_content=text,
            metadata={
                "url": url,
                "title": "Engineer",
                "company": "Example",
                "location": "Sydney",
                "source": "test",
                "original_content": "Full posting " + text,
                "requested_location": "Private query location",
                "pre_screen_note": "Candidate hint",
            },
        )

    def test_unchanged_postings_are_indexed_once_changed_versions_are_isolated(self):
        store = publish([self.doc()], self.root / "one", self.embeddings)
        publish([self.doc()], self.root / "two", self.embeddings)
        self.assertEqual(len(self.embeddings.embedded), 1)
        self.assertEqual(store._collection.count(), 1)
        self.assertEqual(store._collection.configuration["hnsw"]["ef_search"], 500)
        publish([self.doc(text="Python SQL")], self.root / "three", self.embeddings)
        self.assertEqual(len(self.embeddings.embedded), 2)
        self.assertEqual(store._collection.count(), 2)
        old = retrieve_relevant_jobs(
            "Python", str(self.root / "one"), queries=["Python"]
        )
        new = retrieve_relevant_jobs("SQL", str(self.root / "three"), queries=["SQL"])
        self.assertEqual(old[0].page_content, "Full posting Python APIs")
        self.assertEqual(new[0].page_content, "Full posting Python SQL")
        self.assertNotIn("pre_screen_note", new[0].metadata)
        self.assertNotIn("requested_location", new[0].metadata)

    def test_cancellation_during_embedding_never_publishes_scope(self):
        cancelled = False
        original = self.embeddings.embed_documents

        def embed(texts):
            nonlocal cancelled
            values = original(texts)
            cancelled = True
            return values

        with patch.object(self.embeddings, "embed_documents", side_effect=embed):
            publish(
                [self.doc()], self.root / "stopped", self.embeddings, lambda: cancelled
            )
        self.assertFalse((self.root / "stopped" / "job_scope.json").exists())

    def test_scope_filters_out_other_searches_and_does_not_reload_corpus(self):
        store = publish([self.doc()], self.root / "one", self.embeddings)
        publish(
            [self.doc("https://example.test/b", "SQL")],
            self.root / "two",
            self.embeddings,
        )
        first = retrieve_relevant_jobs(
            "SQL", str(self.root / "one"), queries=["SQL", "Python"], top_k=0
        )
        self.assertEqual(
            [doc.metadata["url"] for doc in first], ["https://example.test/a"]
        )
        with patch.object(
            store.__class__, "get", side_effect=AssertionError("corpus reloaded")
        ):
            second = retrieve_relevant_jobs(
                "Python", str(self.root / "one"), queries=["Python"], top_k=0
            )
        self.assertEqual(first[0].page_content, second[0].page_content)
        cached = next(iter(_CORPORA.values()))[1][0]
        self.assertEqual(cached.page_content, "Python APIs")

    def test_dismissal_preferences_apply_before_shortlist_without_mutating_shared_index(
        self,
    ):
        first = self.doc("https://example.test/a", "Python APIs")
        first.metadata["location"] = "Sydney"
        second = self.doc("https://example.test/b", "Python APIs")
        second.metadata["location"] = "Melbourne"
        publish([first, second], self.root / "preferences", self.embeddings)
        feedback = {
            "dismissed": {
                "reason": "location",
                "title": "Engineer",
                "location": "Sydney",
            }
        }
        baseline = retrieve_relevant_jobs(
            "Python", str(self.root / "preferences"), queries=["Python"], top_k=0
        )
        chosen = retrieve_relevant_jobs(
            "Python",
            str(self.root / "preferences"),
            queries=["Python"],
            top_k=1,
            dismissal_feedback=feedback,
        )
        self.assertEqual(chosen[0].metadata["location"], "Melbourne")
        all_jobs = retrieve_relevant_jobs(
            "Python",
            str(self.root / "preferences"),
            queries=["Python"],
            top_k=0,
            dismissal_feedback=feedback,
        )
        self.assertEqual(len(all_jobs), 2)
        self.assertEqual(all_jobs[-1].metadata["location"], "Sydney")
        restored = retrieve_relevant_jobs(
            "Python", str(self.root / "preferences"), queries=["Python"], top_k=0
        )
        self.assertEqual(
            [d.metadata["url"] for d in baseline], [d.metadata["url"] for d in restored]
        )
        self.assertFalse(any("dismissal_feedback" in d.metadata for d in all_jobs))

    def test_dismissal_preference_does_not_override_early_career_safeguard(self):
        junior = self.doc("https://example.test/junior", "Python APIs")
        junior.metadata.update(title="Junior Developer", location="Sydney")
        senior = self.doc("https://example.test/senior", "Python APIs")
        senior.metadata.update(title="Senior Developer", location="Melbourne")
        publish([junior, senior], self.root / "levels", self.embeddings)
        result = retrieve_relevant_jobs(
            "Python",
            str(self.root / "levels"),
            queries=["Python"],
            top_k=1,
            candidate_profile={"years_of_experience": 0, "career_level": "graduate"},
            dismissal_feedback={
                "example": {"reason": "location", "location": "Sydney"}
            },
        )
        self.assertEqual(result[0].metadata["title"], "Junior Developer")

    def test_expiry_prunes_old_versions_and_cancel_does_not_publish_scope(self):
        store = publish([self.doc()], self.root / "one", self.embeddings)
        ids = read_scope(self.root / "one")["ids"]
        store._collection.update(ids=ids, metadatas=[{"last_seen_at": 0}])
        publish(
            [self.doc("https://example.test/b", "SQL")],
            self.root / "two",
            self.embeddings,
        )
        self.assertEqual(store._collection.count(), 1)
        with self.assertRaisesRegex(ValueError, "expired"):
            retrieve_relevant_jobs("Python", str(self.root / "one"), queries=["Python"])
        publish([self.doc()], self.root / "cancelled", self.embeddings, lambda: True)
        self.assertFalse((self.root / "cancelled" / "job_scope.json").exists())


class LexicalParityTests(unittest.TestCase):
    def test_optimized_ranks_match_original_formula(self):
        texts = [
            "Python Python SQL",
            "C++ robotics",
            "SQL Python",
            "C# .NET",
            "",
            "Python SQL",
            "Senior Java engineer five years",
        ]
        index = BM25Index(texts)
        for query in [
            "Python SQL",
            "C++",
            "C# .NET",
            "unknown",
            "",
            "Python Python",
            "Senior Java engineer",
        ]:
            documents = [Counter(tokens(text)) for text in texts]
            lengths = [sum(doc.values()) for doc in documents]
            average = sum(lengths) / len(lengths) or 1
            frequency = Counter(term for doc in documents for term in doc)
            scores = []
            for i, doc in enumerate(documents):
                score = 0.0
                for term in set(tokens(query)):
                    count = doc[term]
                    if count:
                        idf = math.log(
                            1
                            + (len(documents) - frequency[term] + 0.5)
                            / (frequency[term] + 0.5)
                        )
                        score += (
                            idf
                            * count
                            * 2.5
                            / (count + 1.5 * (0.25 + 0.75 * lengths[i] / average))
                        )
                if score > 0:
                    scores.append((i, score))
            expected = [
                i for i, _ in sorted(scores, key=lambda item: (-item[1], item[0]))
            ]
            self.assertEqual(index.rank(query, len(texts)), expected)
