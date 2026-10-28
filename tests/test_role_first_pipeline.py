"""Exercise the web pipeline with local fixtures; no paid services are called."""

from backend.search import service as search_service
from backend.search import retrieval
from backend.search import collection
from backend import runs
from backend.evaluation import orchestration
from backend import configuration


import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import pandas as pd
from langchain_core.documents import Document
from backend.evaluation.runtime import EvaluationFailure


class RoleFirstPipelineTests(unittest.TestCase):
    def setUp(self):
        profiles = TemporaryDirectory()
        self.addCleanup(profiles.cleanup)
        isolated = patch("backend.profiles.storage.PROFILES_DIR", Path(profiles.name))
        isolated.start()
        self.addCleanup(isolated.stop)

    def test_provider_failures_are_persisted_without_counting_as_exclusions(self):
        job = Document(
            page_content="Graduate developer",
            metadata={
                "title": "Graduate developer",
                "company": "Example",
                "url": "https://example.com/job",
            },
        )

        def fail_evaluation(*args, **kwargs):
            kwargs["on_error"](
                job,
                EvaluationFailure(
                    "quota", "Provider quota is exhausted.", skipped=True
                ),
            )
            kwargs["on_progress"](0, 1, 1)
            return []

        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "test-run"
            run_dir.mkdir()
            state = {
                "test-run": {"id": "test-run", "profile": {"years_of_experience": 0}}
            }
            options = {
                "queries": ["Developer"],
                "locations": ["Australia"],
                "platforms": ["linkedin"],
                "remote": False,
                "posted_days_old": 7,
                "top_k": 0,
                "persist_dir": str(run_dir / "vectors"),
            }
            with (
                patch.object(runs, "RUNS_DIR", Path(temporary)),
                patch.object(runs, "RUNS", state),
                patch.object(runs, "RUN_CONTEXTS", {"test-run": "Graduate"}),
                patch.object(
                    collection, "fetch_job_vacancies", return_value=[job.metadata]
                ),
                patch.object(collection, "vectorize_jobs_to_db"),
                patch.object(retrieval, "retrieve_relevant_jobs", return_value=[job]),
                patch.object(
                    orchestration, "evaluate_jobs", side_effect=fail_evaluation
                ),
            ):
                search_service.execute_job_search("test-run", None, options)
            snapshot = json.loads((run_dir / "state.json").read_text())
            self.assertEqual(snapshot["status"], "error")
            self.assertIn("Provider quota is exhausted", snapshot["error"])
            self.assertEqual(
                snapshot["evaluation_errors"][0]["title"], "Graduate developer"
            )
            self.assertEqual(snapshot["evaluation_errors"][0]["category"], "quota")
            self.assertEqual(snapshot["evaluation_skipped"], 1)
            self.assertEqual(snapshot["evaluation_failed"], 1)
            self.assertEqual(snapshot["excluded_jobs"], 0)

    def test_full_pool_reaches_evaluation_and_only_suitable_jobs_are_exported(self):
        jobs = [
            {
                "title": title,
                "company": "Example",
                "location": "Australia",
                "description": description,
            }
            for title, description in [
                ("Director of Engineering", "10 years of experience required"),
                ("Data Analyst", "Python and transferable analytical skills"),
                ("Python Developer", "2 years of Python experience"),
            ]
        ]
        documents = [
            Document(page_content=job["description"], metadata=dict(job))
            for job in jobs
        ]
        evaluations = [
            {
                **job,
                "fit_category": category,
                "is_strong_fit": category == "strong_match",
                "apply_url": "https://example.com/jobs/" + category,
                "source": "linkedin",
                "posted_at": "2026-09-15",
                "mismatch_reason": reason,
            }
            for job, category, reason in zip(
                jobs,
                ["not_suitable", "review", "strong_match"],
                ["required experience exceeds profile", "career change", ""],
            )
        ]
        with TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "test-run"
            run_dir.mkdir()
            state = {
                "test-run": {
                    "id": "test-run",
                    "profile": {"years_of_experience": 2},
                    "excluded_jobs": 99,
                    "recommendations_found": 99,
                }
            }
            options = {
                "queries": ["Engineer", "Data Analyst"],
                "locations": ["Australia"],
                "platforms": ["linkedin"],
                "remote": False,
                "posted_days_old": 7,
                "top_k": 0,
                "persist_dir": str(run_dir / "vectors"),
            }
            with (
                patch.object(runs, "RUNS_DIR", Path(temporary)),
                patch.object(runs, "RUNS", state),
                patch.object(
                    runs,
                    "RUN_CONTEXTS",
                    {"test-run": "2 years Python; interest in data"},
                ),
                patch.object(
                    collection, "fetch_job_vacancies", return_value=jobs
                ) as fetch,
                patch.object(collection, "vectorize_jobs_to_db") as vectorize,
                patch.object(
                    retrieval, "retrieve_relevant_jobs", return_value=documents
                ) as retrieve,
                patch.object(
                    orchestration, "evaluate_jobs", return_value=evaluations
                ) as evaluate,
            ):
                search_service.execute_job_search("test-run", None, options)

            self.assertEqual(state["test-run"]["status"], "complete")
            self.assertEqual(fetch.call_args.args[0], options["queries"])
            self.assertEqual(vectorize.call_args.args[0], jobs)
            self.assertEqual(evaluate.call_args.args[1], documents)
            self.assertEqual(
                [
                    {key: doc.metadata[key] for key in jobs[0]}
                    for doc in evaluate.call_args.args[1]
                ],
                jobs,
            )
            self.assertEqual(
                evaluate.call_args.kwargs["target_roles"], options["queries"]
            )
            self.assertEqual(
                evaluate.call_args.kwargs["provider"],
                configuration.DEFAULT_EVALUATION_PROVIDER,
            )
            self.assertNotIn("locations", retrieve.call_args.kwargs)
            snapshot = json.loads((run_dir / "state.json").read_text())
            self.assertEqual(
                [
                    snapshot[key]
                    for key in [
                        "jobs_found",
                        "jobs_screened",
                        "evaluated_jobs",
                        "displayed_jobs",
                        "excluded_jobs",
                    ]
                ],
                [3, 3, 3, 2, 1],
            )
            self.assertEqual(
                snapshot["excluded_reasons"], {"required experience exceeds profile": 1}
            )
            excluded = snapshot["excluded_recommendations"]
            self.assertEqual(len(excluded), 1)
            self.assertEqual(excluded[0]["title"], "Director of Engineering")
            self.assertEqual(excluded[0]["location"], "Australia")
            self.assertEqual(
                excluded[0]["reason"], "required experience exceeds profile"
            )
            self.assertEqual(excluded[0]["fit_category"], "not_suitable")
            self.assertEqual(
                excluded[0]["apply_url"], "https://example.com/jobs/not_suitable"
            )
            self.assertEqual(excluded[0]["source"], "linkedin")
            self.assertEqual(excluded[0]["posted_at"], "2026-09-15")
            exported = pd.read_excel(run_dir / "relevant_jobs.xlsx")
            self.assertEqual(
                exported["title"].tolist(), ["Python Developer", "Data Analyst"]
            )
            self.assertEqual(
                exported["fit_category"].tolist(), ["strong_match", "review"]
            )


if __name__ == "__main__":
    unittest.main()
