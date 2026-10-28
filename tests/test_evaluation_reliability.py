"""Exercise quota recovery and graduate-level matching with no model calls."""

import unittest
from langchain_core.documents import Document

from backend.evaluation.candidate_fit import enforce_experience_fit
from backend.evaluation.runtime import (
    EvaluationFailure,
    GeminiRequestPolicy,
    RequestPacer,
    classify_failure,
    retry_invalid_assessment,
)
from backend.schemas.evaluation import JobEvaluation
from backend.evaluation.providers import _evaluate_concurrently


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


class GoogleRateLimitError(Exception):
    pass


class ReliabilityTests(unittest.TestCase):
    def test_unpaced_requests_still_observe_rate_limit_backoff(self):
        policy = GeminiRequestPolicy(RequestPacer(0, self.clock.time, self.clock.sleep))
        starts = []

        def operation():
            starts.append(self.clock.now)
            if len(starts) == 3:
                raise GoogleRateLimitError(
                    "429 RESOURCE_EXHAUSTED. Please retry in 75s."
                )
            return "assessment"

        for _ in range(3):
            self.assertEqual(policy.invoke(operation), "assessment")
        self.assertEqual(starts, [0, 0, 0, 75])

    def test_malformed_assessment_recovers_with_paced_retry(self):
        starts = []

        # Perform one provider request and validate its structured response before accepting it.
        def operation():
            starts.append(self.clock.now)
            return JobEvaluation.model_validate(
                {"work_type": "invalid"}
                if len(starts) == 1
                else {
                    "match_rationale": "Synthetic assessment",
                    "missing_skills": [],
                    "apply_url": "https://example.test/job",
                }
            )

        result = retry_invalid_assessment(lambda: self.policy.invoke(operation))
        # Check the expected behavior: malformed assessment recovers with paced retry.
        self.assertIsInstance(result, JobEvaluation)
        self.assertEqual(starts, [0, 6])

    def test_repeated_invalid_output_stays_failed_after_two_attempts(self):
        calls = []

        # Perform one provider request and validate its structured response before accepting it.
        def operation():
            calls.append(1)
            return JobEvaluation.model_validate({"work_type": "invalid"})

        with self.assertRaises(Exception) as error:
            retry_invalid_assessment(operation)
        # Check the expected behavior: repeated invalid output stays failed after two attempts.
        self.assertEqual(classify_failure(error.exception).category, "invalid_output")
        self.assertEqual(len(calls), 2)

    def test_other_failures_do_not_trigger_format_retry(self):
        calls = []

        # Perform one provider request and validate its structured response before accepting it.
        def operation():
            calls.append(1)
            raise EvaluationFailure("credentials", "Rejected")

        with self.assertRaises(EvaluationFailure):
            retry_invalid_assessment(operation)
        # Check the expected behavior: other failures do not trigger format retry.
        self.assertEqual(len(calls), 1)

    # Initialize per-test state; individual cases supply additional fixtures and patches.
    def setUp(self):
        self.clock = FakeClock()
        self.policy = GeminiRequestPolicy(
            RequestPacer(10, self.clock.time, self.clock.sleep)
        )

    def test_rate_limit_waits_for_cooldown_then_recovers(self):
        starts = []

        # Perform one provider request and validate its structured response before accepting it.
        def operation():
            starts.append(self.clock.now)
            if len(starts) == 1:
                raise GoogleRateLimitError(
                    "429 RESOURCE_EXHAUSTED. Please retry in 75s."
                )
            return "assessment"

        # Check the expected behavior: rate limit waits for cooldown then recovers.
        self.assertEqual(self.policy.invoke(operation), "assessment")
        self.assertGreaterEqual(starts[1] - starts[0], 75)

    def test_repeated_rate_limits_stop_submitting_remaining_jobs(self):
        calls = []

        # Perform one provider request and validate its structured response before accepting it.
        def operation():
            calls.append(True)
            raise GoogleRateLimitError("429 RESOURCE_EXHAUSTED")

        errors = []
        results = _evaluate_concurrently(
            list(range(8)),
            lambda _: self.policy.invoke(operation),
            workers=1,
            on_error=lambda job, error: errors.append(error),
        )
        # Check the expected behavior: repeated rate limits stop submitting remaining jobs.
        self.assertEqual(results, [])
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(errors), 8)
        self.assertTrue(all(error.skipped for error in errors[1:]))
        self.assertTrue(all(error.category == "rate_limit" for error in errors))

    def test_daily_quota_stops_immediately_and_does_not_leak_error_payload(self):
        # Perform one provider request and validate its structured response before accepting it.
        def operation():
            raise GoogleRateLimitError(
                "quota PerDay reached; private resume text; key=private"
            )

        with self.assertRaises(EvaluationFailure) as result:
            self.policy.invoke(operation)
        # Check the expected behavior: daily quota stops immediately and does not leak error payload.
        self.assertEqual(result.exception.category, "quota")
        self.assertNotIn("private", str(result.exception))
        with self.assertRaises(EvaluationFailure) as skipped:
            self.policy.invoke(
                lambda: self.fail("Must not submit after exhausted quota")
            )
        self.assertTrue(skipped.exception.skipped)

    def test_requests_are_paced_even_without_failures(self):
        starts = []
        for _ in range(3):
            self.policy.invoke(lambda: starts.append(self.clock.now))
        # Check the expected behavior: requests are paced even without failures.
        self.assertEqual(starts, [0, 6, 12])


class ExperienceFitTests(unittest.TestCase):
    def evaluation(self, **overrides):
        fields = dict(
            fit_category="strong_match",
            experience_alignment="meets",
            is_strong_fit=True,
            match_rationale="Technology overlap.",
            missing_skills=[],
            apply_url="https://example.com",
        )
        return JobEvaluation(**(fields | overrides))

    def test_graduate_never_recommended_for_explicit_mid_or_senior_titles(self):
        for title in [
            "Mid-level Developer",
            "Mid-Senior ML Engineer",
            "Senior Developer",
            "Principal Engineer",
            "Lead Data Scientist",
        ]:
            with self.subTest(title=title):
                job = Document(
                    page_content="Python and machine learning.",
                    metadata={"title": title},
                )
                fit, reason = enforce_experience_fit(
                    self.evaluation(),
                    job,
                    "Years of experience: 2",
                    {"career_level": "graduate", "years_of_experience": 2},
                )
                self.assertEqual(fit, "not_suitable")
                self.assertIn("Seniority mismatch", reason)

    def test_mid_level_profile_needs_stated_years_for_senior_mismatch(self):
        profile = {"career_level": "mid", "years_of_experience": 2}
        senior = Document(
            page_content="Build Python services. Founded 15 years ago.",
            metadata={"title": "Senior AI Engineer"},
        )
        # A senior title alone no longer overrides the model for a mid-level profile.
        fit, _ = enforce_experience_fit(
            self.evaluation(), senior, "Years of experience: 2", profile
        )
        self.assertEqual(fit, "strong_match")
        senior.page_content = "5+ years building production Python services."
        fit, reason = enforce_experience_fit(
            self.evaluation(), senior, "Years of experience: 2", profile
        )
        self.assertEqual(fit, "not_suitable")
        self.assertIn("asks for 5 years", reason)
        executive = Document(
            page_content="Python services.", metadata={"title": "Head of AI"}
        )
        fit, reason = enforce_experience_fit(
            self.evaluation(), executive, "Years of experience: 2", profile
        )
        self.assertEqual(fit, "not_suitable")
        self.assertIn("executive-level", reason)

    def test_clear_experience_gap_cannot_be_hidden_in_review(self):
        job = Document(
            page_content="Minimum 5 years of professional experience required.",
            metadata={"title": "Developer"},
        )
        evaluation = self.evaluation(
            fit_category="review",
            minimum_professional_years=5,
            required_experience_evidence=job.page_content,
        )
        fit, reason = enforce_experience_fit(evaluation, job, "Years of experience: 2")
        # Check the expected behavior: clear experience gap cannot be hidden in review.
        self.assertEqual(fit, "not_suitable")
        self.assertIn("5 professional years", reason)

    def test_junior_role_is_not_excluded_for_senior_colleague_mentions(self):
        job = Document(
            page_content="Report to a senior engineer. Company founded 15 years ago.",
            metadata={"title": "Graduate Developer"},
        )
        # Check the expected behavior: junior role is not excluded for senior colleague mentions.
        self.assertEqual(
            enforce_experience_fit(self.evaluation(), job, "Years of experience: 0")[0],
            "strong_match",
        )

    def test_unknown_experience_cannot_be_strong_match(self):
        job = Document(page_content="Python.", metadata={"title": "Developer"})
        result = enforce_experience_fit(
            self.evaluation(experience_alignment="unknown"), job, ""
        )
        # Check the expected behavior: unknown experience cannot be strong match.
        self.assertEqual(result[0], "review")

    def test_junior_domain_pivot_remains_review(self):
        job = Document(
            page_content="Junior analytical work.",
            metadata={"title": "Junior Data Analyst"},
        )
        # Check the expected behavior: junior domain pivot remains review.
        self.assertEqual(
            enforce_experience_fit(
                self.evaluation(fit_category="review"), job, "Years of experience: 1"
            )[0],
            "review",
        )


if __name__ == "__main__":
    unittest.main()
