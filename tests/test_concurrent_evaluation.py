"""Validate overlapping requests without contacting Claude."""

from threading import Barrier
import unittest

from backend.evaluation.providers import _evaluate_concurrently


class ConcurrentEvaluationTests(unittest.TestCase):
    def test_requests_overlap_preserve_order_and_isolate_failure(self):
        # Both workers must start before either can finish. Sequential
        # execution breaks the barrier and fails this test.
        overlap = Barrier(2, timeout=5)
        progress = []

        def evaluate(job):
            if job == "failed":
                raise TimeoutError("Simulated individual request failure")
            overlap.wait()
            return {"title": job}

        results = _evaluate_concurrently(
            ["first", "second", "failed"],
            evaluate,
            workers=2,
            on_progress=lambda *counts: progress.append(counts),
        )
        # Check the expected behavior: requests overlap preserve order and isolate failure.
        self.assertEqual(results, [{"title": "first"}, {"title": "second"}])
        self.assertEqual(progress[-1], (2, 1, 3))
        self.assertEqual(
            [success + failure for success, failure, _ in progress], [1, 2, 3]
        )

    def test_empty_pool_does_not_invoke_requests(self):
        def evaluate(job):
            self.fail("Empty pool must not call the evaluator")

        # Check the expected behavior: empty pool does not invoke requests.
        self.assertEqual(_evaluate_concurrently([], evaluate, 4), [])


if __name__ == "__main__":
    unittest.main()
