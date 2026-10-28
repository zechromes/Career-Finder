"""Experiment boundaries and comparisons use synthetic data and mocked providers."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from backend import runs
from backend.evaluation import experiments as exp
from backend.routers.experiments import router
from backend.schemas.experiments import ExperimentRequest, ExperimentResult

SOURCE = "a" * 32


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        tracing = patch.dict(
            "os.environ",
            {
                "CAREER_LANGSMITH_TRACING": "false",
                "LANGCHAIN_TRACING_V2": "false",
                "LANGSMITH_TRACING": "false",
            },
        )
        tracing.start()
        self.addCleanup(tracing.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = {
            "profile": {"headline": "Python developer", "tech_skills": ["Python"]},
            "status": "complete",
            "saved_profile_name": "Synthetic profile",
            "recommendations": [
                dict(
                    title="Python Developer",
                    company="Example",
                    apply_url="https://example.test/1",
                    job_description="Build Python services.",
                ),
                dict(
                    title="Designer",
                    company="Example",
                    apply_url="https://example.test/2",
                    job_description="Design illustrations.",
                ),
            ],
            "preferences": {"queries": ["Python developer"]},
        }
        for obj, name, value in [
            (runs, "RUNS", {SOURCE: self.state}),
            (runs, "RUNS_DIR", Path(self.temp.name)),
            (runs, "DELETING", set()),
            (exp, "EXPERIMENTS", {}),
            (exp, "ACTIVE", set()),
        ]:
            patcher = patch.object(obj, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.public, self.profile, self.roles, self.docs = exp.dataset(SOURCE)

    def request(self, **changes):
        return ExperimentRequest(
            source_id=SOURCE, fingerprint=self.public.fingerprint, **changes
        )

    def prepare(self, body):
        with patch.object(exp.threading, "Thread"):
            result = exp.start(body)
        return result["id"]

    def test_read_only_dataset_and_validation(self):
        before = copy.deepcopy(self.state)
        with patch("langchain_openai.OpenAIEmbeddings") as embeddings, patch.object(
            exp, "evaluate_jobs"
        ) as generation:
            self.assertEqual(
                self.client.get("/api/experiments/options").status_code, 200
            )
            self.assertEqual(
                self.client.get("/api/experiments/sources").json()[0]["id"], SOURCE
            )
            data = self.client.get("/api/experiments/sources/" + SOURCE).json()
            self.assertIn("Saved results only", data["scope"])
            self.assertEqual(len(data["jobs"]), 2)
            embeddings.assert_not_called()
            generation.assert_not_called()
        self.assertEqual(self.state, before)
        self.assertEqual(
            self.client.get("/api/experiments/sources/invalid").status_code, 404
        )
        for changes in [
            dict(top_k=21),
            dict(embedding_models=[]),
            dict(providers=[]),
            dict(providers=["unknown"]),
            dict(labels={"x": "false"}),
        ]:
            payload = self.request().model_dump() | changes
            self.assertEqual(
                self.client.post("/api/experiments", json=payload).status_code, 422
            )
        for changes, status in [
            (dict(fingerprint="b" * 64), 409),
            (dict(labels={"foreign": True}), 422),
        ]:
            self.assertEqual(
                self.client.post(
                    "/api/experiments", json=self.request().model_dump() | changes
                ).status_code,
                status,
            )

    def test_metrics_never_treat_unlabeled_as_negative(self):
        metric = exp.metrics(
            {"a": True, "b": False, "d": True}, ["a", "b", "c", "d"], ["a", "c"]
        )
        self.assertEqual(metric["precision_on_labeled"], 1)
        self.assertEqual(metric["observed_recall_at_k"], 0.5)
        self.assertEqual(metric["label_coverage"], 0.75)
        self.assertEqual(metric["unlabeled_selected"], 1)
        self.assertEqual(metric["missed_labeled_positives"], ["d"])
        empty = exp.metrics({}, ["a"], ["a"])
        self.assertIsNone(empty["precision_on_labeled"])
        self.assertIsNone(empty["observed_recall_at_k"])

    def test_embedding_selection_and_rank_use_same_documents(self):
        doc = list(self.docs.values())
        with patch("langchain_openai.OpenAIEmbeddings") as embed:
            embed.return_value.embed_documents.side_effect = [
                [[1.0, 0.0], [0.0, 1.0]],
                [[1.0, 0.0], [1.0, 0.0]],
            ]
            ranked = exp.rank(
                self.profile,
                self.roles,
                doc,
                "text-embedding-3-large",
                1,
                lambda: False,
            )
            self.assertEqual(ranked, [0])
            self.assertEqual(embed.call_args.kwargs["model"], "text-embedding-3-large")
            self.assertIn(
                "Build Python services.",
                embed.return_value.embed_documents.call_args_list[0].args[0][0],
            )

    def test_comparison_uses_baseline_shortlist_and_never_changes_workspace(self):
        body = self.request(
            top_k=1,
            embedding_models=["text-embedding-3-small", "text-embedding-3-large"],
            providers=["gpt", "claude"],
        )
        key = self.prepare(body)
        before = copy.deepcopy(self.state)

        def generation(context, docs, **kwargs):
            self.assertEqual(docs[0].metadata["title"], "Designer")
            self.assertNotIn("cache_directory", kwargs)
            return [
                dict(
                    title="Designer",
                    company="Example",
                    apply_url="https://example.test/2",
                    fit_category="review",
                    score=30,
                )
            ]

        with patch.object(exp, "rank", side_effect=[[1], [0]]), patch.object(
            exp, "evaluate_jobs", side_effect=generation
        ) as call:
            exp.execute(key, body, self.profile, self.roles, self.docs)
        result = ExperimentResult.model_validate(exp.get(key))
        self.assertEqual(result.status, "complete")
        self.assertEqual(
            [trial.provider for trial in result.generation], ["gpt", "claude"]
        )
        self.assertEqual(
            call.call_args_list[0].kwargs["requirement_loader"],
            call.call_args_list[1].kwargs["requirement_loader"],
        )
        self.assertEqual(result.generation[0].input_ids, result.generation[1].input_ids)
        self.assertEqual(self.state, before)
        self.assertNotIn(key, exp.ACTIVE)

    def test_failure_is_visible_without_fallback_generation(self):
        body = self.request(providers=["gpt"])
        key = self.prepare(body)
        with patch.object(
            exp, "rank", side_effect=RuntimeError("synthetic private payload")
        ), patch.object(exp, "evaluate_jobs") as generate:
            exp.execute(key, body, self.profile, self.roles, self.docs)
        result = exp.get(key)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["retrieval"][0]["error"])
        self.assertNotIn("private payload", str(result))
        generate.assert_not_called()

    def test_generation_failure_does_not_erase_successful_provider(self):
        body = self.request(phase="generation", top_k=1, providers=["gpt", "claude"])
        key = self.prepare(body)
        with patch.object(
            exp,
            "evaluate_jobs",
            side_effect=[
                RuntimeError("synthetic"),
                [dict(title="Python Developer", fit_category="review")],
            ],
        ):
            exp.execute(key, body, self.profile, self.roles, self.docs)
        result = exp.get(key)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["generation"][0]["errors"])
        self.assertEqual(len(result["generation"][1]["results"]), 1)

    def test_cancellation_stops_later_trials_and_keeps_single_worker(self):
        body = self.request(providers=["gpt", "claude"])
        key = self.prepare(body)
        self.assertEqual(
            self.client.post("/api/experiments", json=body.model_dump()).status_code,
            409,
        )

        def rank(*args):
            exp.cancel(key)
            return [0]

        with patch.object(exp, "rank", side_effect=rank), patch.object(
            exp, "evaluate_jobs"
        ) as generation:
            exp.execute(key, body, self.profile, self.roles, self.docs)
        self.assertEqual(exp.get(key)["status"], "cancelled")
        generation.assert_not_called()
        self.assertFalse(exp.ACTIVE)

    def test_expiry_and_active_workspace(self):
        self.state["worker_active"] = True
        self.assertEqual(self.client.get("/api/experiments/sources").json(), [])
        self.assertEqual(
            self.client.get("/api/experiments/sources/" + SOURCE).status_code, 409
        )
        self.state["worker_active"] = False
        body = self.request()
        key = self.prepare(body)
        exp.ACTIVE.clear()
        exp.EXPERIMENTS[key]["created_at"] = 0
        self.assertEqual(self.client.get("/api/experiments/" + key).status_code, 404)

    def test_scoped_pool_uses_original_text_and_excludes_other_workspaces(self):
        from backend.search.shared_index import publish, _CORPORA
        from tests.test_shared_job_index import Embeddings

        root = Path(self.temp.name)
        original = Document(
            page_content="Python",
            metadata={
                "title": "Engineer",
                "company": "Example",
                "url": "https://example.test/scoped",
                "original_content": "Full Python posting",
            },
        )
        unrelated = Document(
            page_content="Design",
            metadata={"title": "Other", "url": "https://example.test/other"},
        )
        _CORPORA.clear()
        with patch.dict(
            "os.environ",
            {"JOB_INDEX_DIR": str(root / "index"), "ANONYMIZED_TELEMETRY": "False"},
        ):
            store = publish(
                [original], root / SOURCE / "vector_db_search_1", Embeddings()
            )
            publish([unrelated], root / "other", Embeddings())
            count = store._collection.count()
            with patch(
                "langchain_openai.OpenAIEmbeddings",
                side_effect=AssertionError("No embedding calls on preview"),
            ):
                public, _, _, docs = exp.dataset(SOURCE)
            self.assertEqual(len(docs), 1)
            self.assertEqual(
                next(iter(docs.values())).metadata["_experiment_embedding_text"],
                "Python",
            )
            self.assertEqual(public.jobs[0].description, "Full Python posting")
            self.assertIn("Collected posting pools", public.scope)
            self.assertEqual(store._collection.count(), count)
        _CORPORA.clear()

    def test_missing_scoped_index_is_an_error_without_creating_storage(self):
        import json

        path = Path(self.temp.name) / SOURCE / "vector_db_search_1"
        path.mkdir(parents=True)
        missing = Path(self.temp.name) / "missing-index"
        (path / "job_scope.json").write_text(
            json.dumps({"version": 1, "index_dir": str(missing), "ids": ["missing"]})
        )
        self.assertEqual(
            self.client.get("/api/experiments/sources/" + SOURCE).status_code, 409
        )
        self.assertFalse(missing.exists())

    def test_missing_urls_keep_distinct_jobs_and_score_the_correct_prediction(self):
        for row in self.state["recommendations"]:
            row["apply_url"] = "No URL provided"
        public, profile, roles, docs = exp.dataset(SOURCE)
        self.assertEqual(len(docs), 2)
        ids = list(docs)
        body = ExperimentRequest(
            source_id=SOURCE,
            fingerprint=public.fingerprint,
            phase="generation",
            labels={ids[0]: True, ids[1]: False},
        )
        key = self.prepare(body)
        output = dict(
            title="Python Developer",
            company="Example",
            apply_url="No URL provided",
            job_description="Build Python services.",
            fit_category="strong_match",
        )
        with patch.object(exp, "evaluate_jobs", return_value=[output]):
            exp.execute(key, body, profile, roles, docs)
        trial = exp.get(key)["generation"][0]
        self.assertEqual(trial["results"][0]["jobId"], ids[0])
        self.assertEqual(trial["metrics"]["precision_on_labeled"], 1)
        self.assertEqual(trial["metrics"]["unlabeled_selected"], 0)
