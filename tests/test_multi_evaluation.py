# Regression coverage for multi evaluation; fixtures and assertions document the expected behavior.
import os
import unittest
import threading
import time
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

    def unavailable(self, provider):
        return (
            EvaluationFailure("quota", "Provider quota is exhausted.")
            if provider == "gemini"
            else None
        )

    def test_unavailable_provider_is_skipped_reported_and_not_required(self):
        snapshots, skipped = [], []

        def evaluate(context, jobs, **kwargs):
            kwargs["on_result"](self.assessment(kwargs["provider"]))

        with patch.object(multi, "check_availability", side_effect=self.unavailable):
            with patch.object(multi, "evaluate_provider", side_effect=evaluate) as mock:
                results = multi.evaluate_jobs(
                    "resume",
                    [self.doc],
                    include_all=True,
                    on_result=snapshots.append,
                    on_unavailable=lambda item, failure: skipped.append(item["value"]),
                )
        self.assertEqual(
            {call.kwargs["provider"] for call in mock.call_args_list}, {"claude", "gpt"}
        )
        self.assertEqual(skipped, ["gemini"])
        # The skipped row is kept so a retry can fill it, but it is not required.
        self.assertEqual(results[0]["model_evaluations"]["gemini"]["status"], "skipped")
        self.assertEqual(results[0]["fit_category"], "strong_match")
        self.assertEqual(results[0]["score"], 85)
        self.assertEqual(results[0]["evaluation_model_id"], "Claude + GPT")
        self.assertIn("2/2 models complete", results[0]["assessment_summary"])

    def test_retried_skipped_model_joins_the_verdict(self):
        complete = {"status": "complete", "fit_category": "strong_match", "score": 90}
        existing = multi.summarize(
            {
                "model_evaluations": {
                    "claude": complete,
                    "gpt": complete,
                    "gemini": {"status": "skipped", "error": "Quota exhausted."},
                }
            }
        )
        self.assertEqual(existing["fit_category"], "strong_match")
        incoming = {
            "model_evaluations": {
                "gemini": {"status": "complete", "fit_category": "review", "score": 60}
            }
        }
        merged = multi.merge_result(existing, incoming)
        self.assertEqual(merged["fit_category"], "review")
        self.assertIn("3/3 models complete", merged["assessment_summary"])
        # A later skip never replaces a completed assessment.
        again = multi.merge_result(
            merged, {"model_evaluations": {"gemini": {"status": "skipped"}}}
        )
        self.assertEqual(again["model_evaluations"]["gemini"]["status"], "complete")

    def test_saved_three_model_job_still_needs_all_three(self):
        job = {
            "model_evaluations": {
                "claude": {"status": "complete", "fit_category": "strong_match", "score": 90},
                "gpt": {"status": "complete", "fit_category": "strong_match", "score": 90},
                "gemini": {"status": "failed"},
            }
        }
        result = multi.summarize(job)
        self.assertEqual(result["fit_category"], "review")
        self.assertIn("2/3 models complete", result["assessment_summary"])

    def test_no_available_model_still_records_failures(self):
        with patch.object(
            multi,
            "check_availability",
            return_value=EvaluationFailure("quota", "Provider quota is exhausted."),
        ):
            with patch.object(multi, "evaluate_provider") as mock:
                multi.evaluate_jobs("resume", [self.doc], include_all=True)
        self.assertEqual(mock.call_count, 3)

    def test_quota_failure_marks_provider_unavailable(self):
        def evaluate(context, jobs, **kwargs):
            kwargs["on_error"](jobs[0], EvaluationFailure("quota", "Quota exhausted."))

        with patch.object(multi, "check_availability", return_value=None):
            with patch.object(multi, "evaluate_provider", side_effect=evaluate):
                with patch.object(multi, "mark_unavailable") as mark:
                    multi.evaluate_jobs("resume", [self.doc], include_all=True)
        self.assertEqual(
            {call.args[0] for call in mark.call_args_list}, {"claude", "gpt", "gemini"}
        )

    def test_retry_checks_only_its_model_and_never_resends_while_unavailable(self):
        retry = Document(
            page_content=self.doc.page_content,
            metadata={**self.doc.metadata, "_evaluation_provider": "gemini"},
        )
        skipped = []
        with patch.object(
            multi, "check_availability", side_effect=self.unavailable
        ) as check:
            with patch.object(multi, "evaluate_provider") as mock:
                multi.evaluate_jobs(
                    "resume",
                    [retry],
                    include_all=True,
                    on_unavailable=lambda item, failure: skipped.append(item["value"]),
                )
        self.assertEqual([call.args[0] for call in check.call_args_list], ["gemini"])
        mock.assert_not_called()
        self.assertEqual(skipped, ["gemini"])
        # Once the model works again, the same retry is sent.
        with patch.object(multi, "check_availability", return_value=None):
            with patch.object(multi, "evaluate_provider") as mock:
                multi.evaluate_jobs("resume", [retry], include_all=True)
        self.assertEqual(mock.call_args.kwargs["provider"], "gemini")

    def test_slow_availability_check_does_not_hold_the_search(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def slow(provider):
            if provider == "gpt":
                release.wait(5)
            return None

        started = time.monotonic()
        with patch.object(multi, "AVAILABILITY_CHECK_SECONDS", 0.1):
            with patch.object(multi, "check_availability", side_effect=slow):
                with patch.object(multi, "evaluate_provider") as mock:
                    multi.evaluate_jobs("resume", [self.doc], include_all=True)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(mock.call_count, 3)


class AvailabilityCheckTests(unittest.TestCase):
    def setUp(self):
        from backend.evaluation import providers

        self.providers = providers
        providers._AVAILABILITY.clear()
        self.addCleanup(providers._AVAILABILITY.clear)
        env = patch.dict(os.environ, {"CAREER_EVALUATION_PREFLIGHT": "true"})
        env.start()
        self.addCleanup(env.stop)

    def test_spend_cap_is_unavailable_and_cached(self):
        class Capped(Exception):
            status_code = 429

        llm = patch.object(self.providers, "create_evaluation_llm")
        create = llm.start()
        self.addCleanup(llm.stop)
        create.return_value.invoke.side_effect = Capped(
            "RESOURCE_EXHAUSTED: project exceeded its monthly spending cap"
        )
        first = self.providers.check_availability("gemini")
        second = self.providers.check_availability("gemini")
        self.assertEqual(first.category, "quota")
        self.assertIs(second, first)
        self.assertEqual(create.return_value.invoke.call_count, 1)

    def test_timeout_does_not_skip_a_model(self):
        with patch.object(self.providers, "create_evaluation_llm") as create:
            create.return_value.invoke.side_effect = TimeoutError("timed out")
            self.assertIsNone(self.providers.check_availability("claude"))

    def test_concurrent_checks_send_one_request(self):
        release = threading.Event()
        with patch.object(self.providers, "create_evaluation_llm") as create:
            create.return_value.invoke.side_effect = lambda prompt: release.wait(5)
            self.providers.warm_availability()
            waiter = threading.Thread(
                target=self.providers.check_availability, args=("claude",)
            )
            waiter.start()
            release.set()
            waiter.join(5)
            for thread in threading.enumerate():
                if thread.name.startswith("availability-"):
                    thread.join(5)
        # Three warm-up requests, one per provider; the waiting caller reuses Claude's.
        self.assertEqual(create.call_count, 3)

    def test_check_can_be_turned_off(self):
        with patch.dict(os.environ, {"CAREER_EVALUATION_PREFLIGHT": "false"}):
            with patch.object(self.providers, "create_evaluation_llm") as create:
                self.assertIsNone(self.providers.check_availability("gpt"))
        create.assert_not_called()
