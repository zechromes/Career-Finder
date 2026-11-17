"""Review regressions use synthetic data and never call external providers."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from collections import defaultdict, deque
from langchain_core.documents import Document
from backend.schemas.resume import ResumeProfile
from backend.profiles.upload import classify_and_extract_resume, ResumeVerificationError
from backend.evaluation.cache import cached_assessment
from backend.evaluation import orchestration
from backend.evaluation.runtime import EvaluationFailure
from backend.search.ranking import retrieval_query_weights, reciprocal_rank_fusion


def setUpModule():
    # Saving an action also updates its labeled dataset; keep that out of data/.
    datasets = tempfile.TemporaryDirectory()
    unittest.addModuleCleanup(datasets.cleanup)
    patcher = patch("backend.evaluation.action_dataset.REVIEW_DATASETS_DIR", Path(datasets.name))
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)


class ReviewTests(unittest.TestCase):
    def profile(self):
        return ResumeProfile(
            name="Example", headline="Developer", profile="Builds software"
        )

    def test_combined_intake_accepts_once_and_rejects_invalid_outputs(self):
        with patch("langchain_openai.ChatOpenAI") as client:
            invoke = client.return_value.with_structured_output.return_value.invoke
            invoke.return_value = {
                "document_type": "resume",
                "profile": self.profile().model_dump(),
            }
            # The original text is attached by the app, never requested from the model.
            self.assertEqual(
                classify_and_extract_resume("Synthetic CV"),
                self.profile().model_copy(update={"source_text": "Synthetic CV"}),
            )
            schema = client.return_value.with_structured_output.call_args.args[0]
            self.assertNotIn(
                "source_text", schema.model_json_schema()["$defs"]["ExtractedProfile"]["properties"]
            )
            invoke.assert_called_once()
            self.assertEqual(invoke.call_args.args[0][-1], ("human", "Synthetic CV"))
            for kind in ("not_resume", "uncertain"):
                invoke.return_value = {"document_type": kind, "profile": None}
                with self.assertRaises(ValueError) as caught:
                    classify_and_extract_resume("Synthetic document")
                self.assertNotIsInstance(caught.exception, ResumeVerificationError)
            for result in (
                None,
                {},
                {"document_type": "resume", "profile": None},
                {"document_type": "not_resume", "profile": self.profile().model_dump()},
            ):
                invoke.return_value = result
                with self.assertRaises(ResumeVerificationError):
                    classify_and_extract_resume("Synthetic document")
            invoke.side_effect = RuntimeError("private details")
            with self.assertRaises(ResumeVerificationError) as caught:
                classify_and_extract_resume("Synthetic document")
            self.assertNotIn("private details", str(caught.exception))

    def test_cache_reuse_identity_expiry_corruption_and_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            owner = Path(temporary) / "owner"
            owner.mkdir()
            directory = owner / "evaluations"
            operation = Mock(return_value=self.profile())

            def get(identity="original"):
                return cached_assessment(directory, identity, ResumeProfile, operation)

            self.assertEqual(get(), get())
            self.assertEqual(operation.call_count, 1)
            for key in (
                "changed-profile",
                "changed-posting",
                "changed-model",
                "changed-policy",
            ):
                get(key)
            self.assertEqual(operation.call_count, 5)
            for file in directory.glob("*.json"):
                record = json.loads(file.read_text())
                record["created_at"] = 0
                file.write_text(json.dumps(record))
            get()
            self.assertEqual(operation.call_count, 6)
            for file in directory.glob("*.json"):
                file.write_text("broken")
            get()
            self.assertEqual(operation.call_count, 7)
            import shutil

            shutil.rmtree(owner)
            get()
            self.assertFalse(owner.exists())

    def test_failed_and_cancelled_calls_are_not_cached(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "evaluations"
            with self.assertRaises(ValueError):
                cached_assessment(
                    directory,
                    "x",
                    ResumeProfile,
                    Mock(side_effect=ValueError("failure")),
                )
            cancelled = [False]

            def operation():
                cancelled[0] = True
                return self.profile()

            with self.assertRaisesRegex(RuntimeError, "cancelled"):
                cached_assessment(
                    directory, "x", ResumeProfile, operation, lambda: cancelled[0]
                )
            self.assertFalse(directory.exists())

    def test_role_group_weight_is_constant_and_duplicate_roles_do_not_count_twice(self):
        profile = {"tech_skills": ["Python"]}
        one = retrieval_query_weights(profile, ["Developer"])
        many = retrieval_query_weights(profile, ["Developer", "Analyst", "Developer"])
        self.assertEqual(one["Developer"], many["Developer"] + many["Analyst"])
        self.assertEqual(one["Python"], many["Python"])
        # Equal query votes would promote role-only evidence as roles multiply.
        rankings = [["role"], ["role"], ["skills"], ["work"]]
        self.assertEqual(reciprocal_rank_fusion(rankings, 3)[0], "role")
        balanced = reciprocal_rank_fusion(rankings, 3, weights=[0.5, 0.5, 1, 1])
        self.assertEqual(set(balanced), {"role", "skills", "work"})

    def test_partial_agreement_is_visible_but_not_a_final_verdict(self):
        result = orchestration.summarize(
            {
                "model_evaluations": {
                    "gpt": {
                        "status": "complete",
                        "score": 80,
                        "fit_category": "strong_match",
                    },
                    "claude": {
                        "status": "complete",
                        "score": 90,
                        "fit_category": "strong_match",
                    },
                    "gemini": {"status": "failed"},
                }
            }
        )
        self.assertEqual(result["fit_category"], "review")
        self.assertIsNone(result["score"])
        self.assertEqual(result["provisional_score"], 85)
        self.assertEqual(result["agreement_count"], 2)
        self.assertIn("2/3 models complete", result["assessment_summary"])

    def test_progressive_waves_and_permanent_failure_isolation(self):
        docs = [
            Document(
                page_content="Python", metadata={"url": f"https://example.test/{i}"}
            )
            for i in range(31)
        ]
        for fail in (None, "quota", "rate_limit"):
            calls = defaultdict(list)

            def evaluate(context, wave, **kw):
                provider = kw["provider"]
                calls[provider].append(len(wave))
                for doc in wave:
                    if fail and provider == "gpt":
                        kw["on_error"](doc, EvaluationFailure(fail, "Unavailable"))
                    else:
                        kw["on_result"](
                            {
                                "apply_url": doc.metadata["url"],
                                "score": 80,
                                "fit_category": "strong_match",
                            }
                        )

            with patch.object(orchestration, "evaluate_provider", side_effect=evaluate):
                results = orchestration.evaluate_jobs(
                    "Synthetic profile", docs, include_all=True
                )
            self.assertEqual(calls["claude"], [15, 15, 1])
            self.assertEqual(calls["gemini"], [15, 15, 1])
            self.assertEqual(calls["gpt"], [15] if fail else [15, 15, 1])
            self.assertEqual(len(results), 31)
            self.assertTrue(
                all(
                    row["model_evaluations"]["gpt"]["status"]
                    == ("failed" if fail else "complete")
                    for row in results
                )
            )

    def test_filtered_collection_uses_bounded_allowance_and_caps_eligible_jobs(self):
        from backend.search.collection import fetch_job_vacancies

        jobs = [
            dict(
                title="Senior Engineer",
                description="",
                source_platform="seek",
                url=f"https://example.test/s{i}",
            )
            for i in range(3)
        ] + [
            dict(
                title="Junior Engineer",
                description="",
                source_platform="seek",
                url=f"https://example.test/j{i}",
            )
            for i in range(3)
        ]
        with patch(
            "backend.search.collection._fetch_job_vacancies_uncached", return_value=jobs
        ) as fetch, patch("backend.search.collection.CollectionCache") as cache:
            cache.return_value.collect.side_effect = (
                lambda parameters, operation, *args: (operation()[0], False)
            )
            result = fetch_job_vacancies(
                ["Engineer"],
                [],
                ["seek"],
                n_result=2,
                search_filters={"seniority": "junior"},
            )
            self.assertEqual(fetch.call_args.args[3], 6)
            self.assertEqual(len(result), 2)
            self.assertTrue(all(job["title"] == "Junior Engineer" for job in result))
            self.assertEqual(
                cache.return_value.collect.call_args.args[0]["search_filters"],
                {"seniority": "junior"},
            )

    def test_actions_survive_fresh_run_profile_edit_and_source_deletion(self):
        from backend import runs, app
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as temporary, patch(
            "backend.profiles.storage.PROFILES_DIR", Path(temporary) / "profiles"
        ), patch.object(runs, "RUNS_DIR", Path(temporary) / "runs"), patch.object(
            runs, "RUNS", {}
        ), patch.object(
            runs, "RUN_CONTEXTS", {}
        ), patch.object(
            runs, "RATE_WINDOWS", defaultdict(deque)
        ):
            client = TestClient(app.app)
            body = {"name": "Example", "profile": self.profile().model_dump()}
            saved = client.post("/api/profiles", json=body).json()
            first = client.post(f"/api/profiles/{saved['id']}/searches").json()["id"]
            action = {
                "key": "https://example.test/job",
                "action": "saved",
                "value": True,
            }
            self.assertEqual(
                client.put(f"/api/searches/{first}/actions", json=action).status_code,
                200,
            )
            self.assertEqual(
                client.put(f"/api/profiles/{saved['id']}", json=body).status_code, 200
            )
            second = client.post(
                f"/api/profiles/{saved['id']}/searches?fresh=true"
            ).json()["id"]
            self.assertNotEqual(first, second)
            self.assertEqual(client.delete(f"/api/searches/{first}").status_code, 200)
            self.assertTrue(
                client.get(f"/api/searches/{second}/actions").json()["actions"][
                    action["key"]
                ]["saved"]
            )
            action.update(action="applied", value=True)
            client.put(f"/api/searches/{second}/actions", json=action)
            flags = client.get(f"/api/searches/{second}/actions").json()["actions"][
                action["key"]
            ]
            self.assertEqual(flags, {"saved": True, "applied": True})
            self.assertEqual(
                client.put(
                    f"/api/searches/{second}/actions",
                    json={**action, "action": "invalid"},
                ).status_code,
                422,
            )

    def test_cancellation_does_not_start_later_waves(self):
        import threading

        cancelled = threading.Event()
        docs = [
            Document(
                page_content="Python", metadata={"url": f"https://example.test/{i}"}
            )
            for i in range(31)
        ]
        batches = []

        def evaluate(context, wave, **kw):
            batches.append([doc.metadata["url"] for doc in wave])
            cancelled.set()

        with patch.object(orchestration, "evaluate_provider", side_effect=evaluate):
            orchestration.evaluate_jobs(
                "Synthetic profile", docs, should_cancel=cancelled.is_set
            )
        self.assertTrue(batches)
        self.assertTrue(
            all(
                batch == [doc.metadata["url"] for doc in docs[:15]] for batch in batches
            )
        )

    def test_splitting_one_role_signal_preserves_the_ranking(self):
        role, skills, work = ["a", "b", "c"], ["c", "a", "b"], ["b", "c", "a"]
        baseline = reciprocal_rank_fusion([role, skills, work], 3)
        proposed = reciprocal_rank_fusion(
            [role, role, skills, work], 3, weights=[0.5, 0.5, 1, 1]
        )
        self.assertEqual(baseline, proposed)

    def test_provider_reuses_success_but_invalidates_changed_inputs(self):
        from types import SimpleNamespace
        from langchain_core.runnables import RunnableLambda
        from backend.evaluation.providers import evaluate_jobs
        from backend.schemas.evaluation import JobEvaluation, RequirementSet

        response = JobEvaluation(
            match_rationale="Synthetic",
            missing_skills=[],
            apply_url="https://example.test/job",
        )
        operation = Mock(return_value=response)
        client = SimpleNamespace(
            with_structured_output=lambda *args, **kwargs: RunnableLambda(operation)
        )
        doc = Document(
            page_content="Python required", metadata={"url": "https://example.test/job"}
        )
        with tempfile.TemporaryDirectory() as temporary, patch(
            "backend.evaluation.providers.create_evaluation_llm", return_value=client
        ):

            def evaluate(context="Python experience", roles=None):
                return evaluate_jobs(
                    context,
                    [doc],
                    include_all=True,
                    provider="gpt",
                    target_roles=roles,
                    cache_directory=Path(temporary) / "evaluations",
                    requirement_loader=lambda job: RequirementSet(
                        posting_hash="test",
                        extraction_model="test",
                        extraction_version="test",
                        requirements=[],
                    ),
                )

            self.assertEqual(evaluate(), evaluate())
            self.assertEqual(operation.call_count, 1)
            evaluate("SQL experience")
            evaluate(roles=["Analyst"])
            doc.page_content = "SQL required"
            evaluate()
            with patch.dict(
                "os.environ", {"GPT_EVALUATION_MODEL": "synthetic-changed-model"}
            ):
                evaluate()
            self.assertEqual(operation.call_count, 5)


class ResumeReaderModelTests(unittest.TestCase):
    def test_reasoning_models_get_effort_and_older_models_keep_temperature(self):
        from backend.profiles import extraction

        with patch("langchain_openai.ChatOpenAI") as client:
            extraction.profile_llm("gpt-6.1-sol")
            self.assertEqual(client.call_args.kwargs["reasoning_effort"], "low")
            self.assertNotIn("temperature", client.call_args.kwargs)
            extraction.profile_llm("gpt-4o-mini")
            self.assertEqual(client.call_args.kwargs["temperature"], 0)
            self.assertNotIn("reasoning_effort", client.call_args.kwargs)
