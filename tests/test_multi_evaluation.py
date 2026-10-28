# Regression coverage for multi evaluation; fixtures and assertions document the expected behavior.
import unittest
import threading
from unittest.mock import patch
from langchain_core.documents import Document
from backend.evaluation import orchestration as multi
from backend.evaluation.runtime import EvaluationFailure
from backend.schemas.contracts import JobResult


class MultiEvaluationTests(unittest.TestCase):
    # Initialize per-test state; individual cases supply additional fixtures and patches.
    def setUp(self):
        self.doc = Document(
            page_content="Python required",
            metadata={
                "url": "https://example.test/job",
                "title": "Developer",
                "company": "Example",
                "job_description": "Python required",
            },
        )

    def assessment(self, provider, score=85, category="strong_match"):
        return {
            "apply_url": self.doc.metadata["url"],
            "title": "Developer",
            "company": "Example",
            "score": score,
            "fit_category": category,
            "evaluation_model_id": provider + "-model",
            "rationale": provider + " rationale",
            "requirement_verdicts": [],
            "is_strong_fit": category == "strong_match",
        }

    def test_all_models_persist_independent_results_and_average(self):
        snapshots = []

        def evaluate(context, jobs, **kwargs):
            kwargs["on_result"](
                self.assessment(
                    kwargs["provider"],
                    {"claude": 80, "gpt": 90, "gemini": 85}[kwargs["provider"]],
                )
            )

        with patch.object(multi, "evaluate_provider", side_effect=evaluate) as mock:
            results = multi.evaluate_jobs(
                "resume", [self.doc], include_all=True, on_result=snapshots.append
            )
        # Check the expected behavior: all models persist independent results and average.
        self.assertEqual(
            {call.kwargs["provider"] for call in mock.call_args_list},
            {"claude", "gpt", "gemini"},
        )
        self.assertEqual(results[0]["score"], 85)
        self.assertEqual(results[0]["fit_category"], "strong_match")
        self.assertEqual(len(snapshots), 4)
        self.assertTrue(
            all(
                row["status"] == "pending"
                for row in snapshots[0]["model_evaluations"].values()
            )
        )
        self.assertIsNone(snapshots[0]["score"])
        self.assertEqual(len(JobResult.model_validate(results[0]).model_evaluations), 3)

    def test_disagreement_is_review_and_failure_is_provider_specific(self):
        errors = []

        def evaluate(context, jobs, **kwargs):
            if kwargs["provider"] == "gpt":
                kwargs["on_error"](
                    jobs[0], EvaluationFailure("quota", "Quota unavailable")
                )
            else:
                kwargs["on_result"](self.assessment(kwargs["provider"]))

        with patch.object(multi, "evaluate_provider", side_effect=evaluate):
            result = multi.evaluate_jobs(
                "resume",
                [self.doc],
                include_all=True,
                on_error=lambda doc, error: errors.append(doc),
            )[0]
        # Check the expected behavior: disagreement is review and failure is provider specific.
        self.assertEqual(result["model_evaluations"]["gpt"]["status"], "failed")
        self.assertEqual(result["fit_category"], "review")
        self.assertIsNone(result["score"])
        self.assertEqual(errors[0].metadata["_evaluation_provider"], "gpt")
        retry = errors[0]
        with patch.object(
            multi,
            "evaluate_provider",
            side_effect=lambda context, jobs, **kw: kw["on_result"](
                self.assessment("gpt", 20, "not_suitable")
            ),
        ) as mock:
            incoming = multi.evaluate_jobs("resume", [retry], include_all=True)[0]
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(mock.call_args.kwargs["provider"], "gpt")
        merged = multi.merge_result(result, incoming)
        self.assertEqual(merged["fit_category"], "review")
        self.assertEqual(merged["model_evaluations"]["claude"]["status"], "complete")
        self.assertEqual(merged["score"], 63)

    def test_provider_setup_failure_does_not_stop_other_models(self):
        def evaluate(context, jobs, **kwargs):
            if kwargs["provider"] == "gemini":
                raise ValueError("Missing credentials")
            kwargs["on_result"](self.assessment(kwargs["provider"]))

        with patch.object(multi, "evaluate_provider", side_effect=evaluate):
            result = multi.evaluate_jobs("resume", [self.doc], include_all=True)[0]
        # Check the expected behavior: provider setup failure does not stop other models.
        self.assertEqual(result["model_evaluations"]["gemini"]["status"], "failed")
        self.assertEqual(result["model_evaluations"]["gpt"]["status"], "complete")

    def test_cancel_does_not_launch_providers(self):
        with patch.object(multi, "evaluate_provider") as mock:
            multi.evaluate_jobs("resume", [self.doc], should_cancel=lambda: True)
        # Check the expected behavior: cancel does not launch providers.
        mock.assert_not_called()

    def test_provider_batches_overlap_and_callbacks_are_serialized(self):
        barrier = threading.Barrier(3, timeout=3)
        callback_lock = threading.Lock()
        snapshots = []

        # Persist retry progress without repeating providers that already succeeded.
        def save(result):
            self.assertTrue(callback_lock.acquire(blocking=False))
            try:
                snapshots.append(result)
            finally:
                callback_lock.release()

        def evaluate(context, jobs, **kwargs):
            barrier.wait()
            kwargs["on_result"](self.assessment(kwargs["provider"]))

        with patch.object(multi, "evaluate_provider", side_effect=evaluate):
            result = multi.evaluate_jobs(
                "resume", [self.doc], include_all=True, on_result=save
            )[0]
        # Check the expected behavior: provider batches overlap and callbacks are serialized.
        self.assertEqual(result["score"], 85)
        self.assertEqual(len(snapshots), 4)

    def test_metadata_preference_is_stable_when_claude_finishes_last(self):
        completed = threading.Barrier(3, timeout=3)
        other_results = threading.Barrier(2, timeout=3)
        released = threading.Event()

        def evaluate(context, jobs, **kwargs):
            provider = kwargs["provider"]
            completed.wait()
            if provider == "claude":
                self.assertTrue(released.wait(3))
            result = {
                **self.assessment(provider),
                "salary": provider + " salary",
                "about_company": provider + " company",
                "candidate_requirements": [provider],
                "work_type": provider + " work",
            }
            kwargs["on_result"](result)
            if provider != "claude":
                other_results.wait()
                released.set()

        with patch.object(multi, "evaluate_provider", side_effect=evaluate):
            result = multi.evaluate_jobs("resume", [self.doc], include_all=True)[0]
        # Check the expected behavior: metadata preference is stable when claude finishes last.
        self.assertEqual(result["salary"], "claude salary")
        self.assertEqual(result["about_company"], "claude company")
        self.assertEqual(result["candidate_requirements"], ["claude"])
        self.assertEqual(result["work_type"], "claude work")

    def test_cancel_after_start_rejects_late_results_and_failures(self):
        barrier = threading.Barrier(3, timeout=3)
        cancelled = threading.Event()
        snapshots, errors = [], []

        def evaluate(context, jobs, **kwargs):
            barrier.wait()
            cancelled.set()
            kwargs["on_result"](self.assessment(kwargs["provider"]))
            kwargs["on_error"](jobs[0], EvaluationFailure("quota", "Quota unavailable"))

        with patch.object(multi, "evaluate_provider", side_effect=evaluate):
            result = multi.evaluate_jobs(
                "resume",
                [self.doc],
                include_all=True,
                on_result=snapshots.append,
                on_error=lambda *args: errors.append(args),
                should_cancel=cancelled.is_set,
            )[0]
        # Check the expected behavior: cancel after start rejects late results and failures.
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(errors, [])
        self.assertTrue(
            all(
                row["status"] == "pending"
                for row in result["model_evaluations"].values()
            )
        )

    def test_progress_counts_completed_jobs_separately_from_failed_assessments(self):
        progress = []

        def evaluate(context, jobs, **kwargs):
            kwargs["on_error"](jobs[0], EvaluationFailure("quota", "Quota unavailable"))

        with patch.object(multi, "evaluate_provider", side_effect=evaluate):
            multi.evaluate_jobs(
                "resume",
                [self.doc],
                include_all=True,
                on_progress=lambda *args: progress.append(args),
            )
        # Check the expected behavior: progress counts completed jobs separately from failed assessments.
        self.assertEqual(progress[-1], (1, 3, 1))
        self.assertTrue(all(done <= total for done, failed, total in progress))

    def test_targeted_retry_does_not_publish_pending_only_rows(self):
        retry = Document(
            page_content=self.doc.page_content,
            metadata={**self.doc.metadata, "_evaluation_provider": "gpt"},
        )
        snapshots = []

        def evaluate(context, jobs, **kwargs):
            kwargs["on_result"](self.assessment(kwargs["provider"]))

        with patch.object(multi, "evaluate_provider", side_effect=evaluate) as mock:
            multi.evaluate_jobs(
                "resume", [retry], include_all=True, on_result=snapshots.append
            )
        # Check the expected behavior: targeted retry does not publish pending only rows.
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["model_evaluations"]["gpt"]["status"], "complete")
