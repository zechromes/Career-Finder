"""Incremental searches preserve prior assessments and evaluate only new postings."""

from backend.search import service as search_service
from backend.search import retrieval
from backend.search import collection
from backend import runs
from backend.profiles import storage
from backend.profiles import service as profiles_service
from backend.evaluation import service as evaluation_service
from backend.evaluation import orchestration


import copy
import json
import time
from threading import Thread
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from backend import app as api
from backend.search.history import unseen_postings
from backend.evaluation.runtime import EvaluationFailure


class FindMoreJobsTests(unittest.TestCase):
    def test_loading_profile_recovers_missing_journal_jobs_once(self):
        old = {
            **self.old,
            "apply_url": "https://example.test/missing",
            "jobId": "missing",
        }
        duplicate = {
            **self.old,
            "apply_url": self.old["apply_url"] + "?utm_source=test",
        }
        (self.path / "job_assessments.jsonl").write_text(
            "\n".join(json.dumps(row) for row in [old, old, duplicate])
            + '\n{"truncated":'
        )
        runs.RUNS["test"]["saved_profile_id"] = "saved"
        with patch.object(
            storage,
            "read_profile",
            return_value={"name": "Synthetic", "source_run_id": "test"},
        ):
            first = self.client.post("/api/profiles/saved/searches")
            second = self.client.post("/api/profiles/saved/searches")
        # Check the expected behavior: loading profile recovers missing journal jobs once.
        self.assertEqual(first.json()["runId"], "test")
        self.assertEqual(second.json()["runId"], "test")
        self.assertEqual(len(runs.RUNS["test"]["recommendations"]), 2)
        self.assertEqual(runs.RUNS["test"]["recommendations"][0], self.old)
        self.assertTrue((self.path / "state.before-history-recovery.json").exists())
        self.assertEqual(
            len(json.loads((self.path / "state.json").read_text())["recommendations"]),
            2,
        )

    def test_retry_preserves_original_date_added(self):
        self.old["added_at"] = "2026-10-01T10:00:00+00:00"
        runs.RUNS["test"]["recommendations"] = [self.old.copy()]
        result = evaluation_service.upsert_assessment(
            "test", {**self.old, "added_at": "2026-10-09T10:00:00+00:00"}
        )
        # Check the expected behavior: retry preserves original date added.
        self.assertEqual(result["added_at"], "2026-10-01T10:00:00+00:00")

    # Initialize per-test state; individual cases supply additional fixtures and patches.
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test"
        self.path.mkdir()
        self.old = {
            "jobId": "stable-old",
            "title": "Developer",
            "company": "Example",
            "location": "Sydney",
            "apply_url": "https://example.test/old",
            "score": 85,
            "fit_category": "strong_match",
            "is_strong_fit": True,
            "job_description": "Python required",
            "model_evaluations": {"gpt": {"status": "complete", "score": 85}},
        }
        run = {
            "id": "test",
            "created_at": time.time(),
            "status": "complete",
            "phase": 4,
            "profile": {"name": "Synthetic candidate", "tech_skills": ["Python"]},
            "recommendations": [copy.deepcopy(self.old)],
            "excluded_recommendations": [],
            "evaluated_jobs": 1,
            "displayed_jobs": 1,
            "jobs_found": 1,
            "jobs_screened": 1,
            "search_inputs": {"queries": ["Developer"]},
            "evaluation_errors": [],
        }
        for name, value in [
            ("RUNS_DIR", Path(self.temp.name)),
            ("RUNS", {"test": run}),
            ("RUN_CONTEXTS", {"test": "Synthetic candidate"}),
            ("ACTIVE_WORKERS", set()),
            ("DELETING", set()),
        ]:
            p = patch.object(runs, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(profiles_service, "save_completed_search_profile")
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(api.app)
        self.options = {
            "queries": ["Analyst"],
            "locations": ["Sydney"],
            "platforms": ["linkedin"],
            "remote": False,
            "posted_days_old": 7,
            "top_k": 50,
            "persist_dir": str(self.path / "vectors"),
            "append": True,
        }

    def posting(self, url="https://example.test/new", title="Analyst"):
        return {
            "url": url,
            "title": title,
            "company": "Example",
            "location": "Sydney",
            "description": "Python required",
            "job_description": "Python required",
        }

    def run_search(self, postings, evaluate=None):
        doc = Document(page_content="Python required", metadata=self.posting())

        def successful(context, jobs, **kw):
            result = {
                **self.old,
                "jobId": "stable-new",
                "title": "Analyst",
                "apply_url": doc.metadata["url"],
            }
            kw["on_result"](result)
            return [result]

        with patch.object(
            collection, "fetch_job_vacancies", return_value=postings
        ) as collect, patch.object(
            collection, "vectorize_jobs_to_db"
        ) as index, patch.object(
            retrieval, "retrieve_relevant_jobs", return_value=[doc]
        ), patch.object(
            orchestration, "evaluate_jobs", side_effect=evaluate or successful
        ) as model:
            search_service.execute_job_search("test", None, self.options)
        self.assertTrue(collect.call_args.kwargs["force_refresh"])
        return index, model

    def test_new_roles_append_and_normalized_old_url_is_not_evaluated(self):
        index, model = self.run_search(
            [
                self.posting("https://example.test/old/?utm_source=test", "Developer"),
                self.posting(),
            ]
        )
        # Check the expected behavior: new roles append and normalized old url is not evaluated.
        self.assertEqual(index.call_args.args[0], [self.posting()])
        self.assertEqual(model.call_args.kwargs["target_roles"], ["Analyst"])
        self.assertEqual(runs.RUNS["test"]["recommendations"][0], self.old)
        self.assertEqual(
            [row["jobId"] for row in runs.RUNS["test"]["recommendations"]],
            ["stable-old", "stable-new"],
        )
        self.assertEqual(runs.RUNS["test"]["last_search_added"], 1)
        self.assertEqual(runs.RUNS["test"]["evaluated_jobs"], 2)
        self.assertTrue((self.path / "relevant_jobs.xlsx").is_file())

    def test_repeat_worker_preserves_results_when_old_caller_omits_append_flag(self):
        self.options.pop("append")
        self.run_search([self.posting()])
        # Check the expected behavior: repeat worker preserves results when old caller omits append flag.
        self.assertEqual(runs.RUNS["test"]["recommendations"][0], self.old)
        self.assertEqual(len(runs.RUNS["test"]["recommendations"]), 2)
        self.assertEqual(runs.RUNS["test"]["evaluated_jobs"], 2)

    def test_no_new_postings_preserve_results_and_retry_checkpoint(self):
        entry = {
            "page_content": "prior",
            "metadata": {
                "url": self.old["apply_url"],
                "_evaluation_provider": "claude",
            },
        }
        (self.path / "failed_jobs.json").write_text(json.dumps([entry]))
        index, model = self.run_search(
            [self.posting(self.old["apply_url"], "Developer")]
        )
        # Check the expected behavior: no new postings preserve results and retry checkpoint.
        index.assert_not_called()
        model.assert_not_called()
        self.assertEqual(runs.RUNS["test"]["recommendations"], [self.old])
        self.assertEqual(runs.RUNS["test"]["status"], "complete")
        self.assertEqual(runs.RUNS["test"]["last_search_added"], 0)
        self.assertIn("No new jobs", runs.RUNS["test"]["message"])
        self.assertEqual(
            json.loads((self.path / "failed_jobs.json").read_text()), [entry]
        )

    def test_provider_failure_keeps_prior_failed_jobs_and_original_roles(self):
        entry = {
            "page_content": "prior",
            "metadata": {
                "url": self.old["apply_url"],
                "_evaluation_provider": "claude",
                "_evaluation_target_roles": ["Developer"],
            },
        }
        (self.path / "failed_jobs.json").write_text(json.dumps([entry]))
        runs.RUNS["test"]["evaluation_errors"] = [
            {"provider": "claude", "message": "prior"}
        ]

        def fail(context, jobs, **kw):
            kw["on_error"](
                Document(
                    page_content=jobs[0].page_content,
                    metadata={**jobs[0].metadata, "_evaluation_provider": "gpt"},
                ),
                EvaluationFailure("quota", "Synthetic quota failure"),
            )
            return []

        self.run_search([self.posting()], fail)
        # Check the expected behavior: provider failure keeps prior failed jobs and original roles.
        self.assertEqual(runs.RUNS["test"]["status"], "error")
        self.assertEqual(runs.RUNS["test"]["recommendations"], [self.old])
        entries = json.loads((self.path / "failed_jobs.json").read_text())
        self.assertEqual(entries[0], entry)
        self.assertEqual(
            entries[1]["metadata"]["_evaluation_target_roles"], ["Analyst"]
        )
        runs.RUNS["test"]["status"] = "running"
        calls = []

        def retry(context, jobs, **kw):
            calls.append(kw["target_roles"])

        with patch.object(orchestration, "evaluate_jobs", side_effect=retry):
            evaluation_service.retry_failed_evaluations("test")
        self.assertEqual(calls, [["Developer"], ["Analyst"]])

    def test_cancel_before_publication_does_not_reserve_unshown_jobs(self):
        def cancel(context, jobs, **kw):
            runs.RUNS["test"]["status"] = "cancelled"
            return []

        self.run_search([self.posting()], cancel)
        # Check the expected behavior: cancel before publication does not reserve unshown jobs.
        self.assertEqual(runs.RUNS["test"]["recommendations"], [self.old])
        self.assertFalse((self.path / "shortlisted_jobs.json").exists())

    def test_cancel_after_publication_preserves_pending_retry_and_restart_dedup(self):
        from backend.evaluation import orchestration

        def cancel_provider(context, jobs, **kw):
            runs.RUNS["test"]["status"] = "cancelled"

        with patch.object(
            orchestration, "evaluate_provider", side_effect=cancel_provider
        ):
            self.run_search([self.posting()], orchestration.evaluate_jobs)
        # Check the expected behavior: cancel after publication preserves pending retry and restart dedup.
        self.assertEqual(runs.RUNS["test"]["status"], "cancelled")
        self.assertEqual(len(runs.RUNS["test"]["recommendations"]), 2)
        checkpoints = json.loads((self.path / "failed_jobs.json").read_text())
        self.assertEqual(
            {entry["metadata"]["_evaluation_provider"] for entry in checkpoints},
            {"claude", "gpt", "gemini"},
        )
        self.assertEqual(
            len(json.loads((self.path / "shortlisted_jobs.json").read_text())), 2
        )
        # Reload persisted state, rather than relying on an in-memory dedup cache.
        runs.RUNS["test"] = json.loads((runs.run_state_path("test")).read_text())
        runs.RUNS["test"]["status"] = "running"
        index, models = self.run_search([self.posting()])
        index.assert_not_called()
        models.assert_not_called()
        self.assertEqual(len(runs.RUNS["test"]["recommendations"]), 2)
        self.assertEqual(
            json.loads((self.path / "failed_jobs.json").read_text()), checkpoints
        )

    def test_retry_scraping_targets_failed_board_and_preserves_preferences(self):
        thread = MagicMock()
        prefs = {"queries": ["Developer"], "platforms": ["linkedin", "indeed"]}
        runs.RUNS["test"].update(
            preferences=prefs, scrape_errors=["LinkedIn description request failed."]
        )
        with patch.object(runs, "threading", SimpleNamespace(Thread=thread)), patch(
            "backend.search.board_cooldown.remaining", return_value=0
        ):
            response = self.client.post("/api/searches/test/retry-scraping")
        self.assertEqual(response.status_code, 202)
        options = thread.call_args.kwargs["args"][-1]
        self.assertEqual(options["platforms"], ["linkedin"])
        self.assertTrue(options["append"])
        self.assertEqual(
            runs.RUNS["test"]["preferences"]["platforms"], prefs["platforms"]
        )
        self.assertEqual(runs.RUNS["test"]["recommendations"], [self.old])
        self.assertEqual(runs.RUNS["test"]["scrape_errors"], [])

    def test_retry_scraping_starts_immediately_after_rate_limit(self):
        thread = MagicMock()
        runs.RUNS["test"].update(
            scrape_errors=["LinkedIn rate-limited description requests (HTTP 429)."]
        )
        before = copy.deepcopy(runs.RUNS["test"])
        with patch.object(runs, "threading", SimpleNamespace(Thread=thread)), patch(
            "backend.search.board_cooldown.remaining", return_value=600
        ):
            response = self.client.post("/api/searches/test/retry-scraping")
        self.assertEqual(response.status_code, 202)
        thread.assert_called_once()
        self.assertEqual(
            runs.RUNS["test"]["recommendations"], before["recommendations"]
        )
        self.assertEqual(runs.RUNS["test"]["scrape_errors"], [])

    def test_endpoint_reuses_profile_and_rejects_overlapping_work(self):
        thread = MagicMock()
        before = copy.deepcopy(runs.RUNS["test"]["profile"])
        with patch.object(runs, "threading", SimpleNamespace(Thread=thread)):
            response = self.client.post(
                "/api/searches/test/find-more",
                json={"preferences": {"queries": ["Analyst"]}},
            )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json(), {"id": "test", "runId": "test"})
            self.assertEqual(
                self.client.post(
                    "/api/searches/test/find-more",
                    json={"preferences": {"queries": ["Analyst"]}},
                ).status_code,
                409,
            )
        # Check the expected behavior: endpoint reuses profile and rejects overlapping work.
        self.assertEqual(runs.RUNS["test"]["profile"], before)
        self.assertEqual(runs.RUNS["test"]["recommendations"], [self.old])
        self.assertTrue(thread.call_args.kwargs["args"][-1]["append"])
        self.assertEqual(
            self.client.post(
                "/api/searches/unknown/find-more",
                json={"preferences": {"queries": ["Analyst"]}},
            ).status_code,
            404,
        )

    def test_repeat_confirm_profile_adds_fifteen_to_fifty_existing_results(self):
        from backend.schemas.resume import ResumeProfile
        from backend.evaluation import orchestration

        original_profile = ResumeProfile.model_validate(
            runs.RUNS["test"]["profile"]
        ).model_dump()
        runs.RUNS["test"]["profile"] = original_profile
        original = [
            {
                **copy.deepcopy(self.old),
                "jobId": f"old-{index}",
                "apply_url": f"https://example.test/old-{index}",
            }
            for index in range(50)
        ]
        runs.RUNS["test"].update(
            recommendations=copy.deepcopy(original),
            evaluated_jobs=50,
            displayed_jobs=50,
            jobs_found=50,
            jobs_screened=50,
        )
        docs = [
            Document(
                page_content="Python required",
                metadata=self.posting(f"https://example.test/new-{index}"),
            )
            for index in range(15)
        ]

        def evaluate(context, jobs, **kw):
            results = []
            for index, doc in enumerate(jobs):
                row = {**self.old, "apply_url": doc.metadata["url"]}
                row.pop("model_evaluations")
                results.append(row)
                kw["on_result"](row)
            return results

        launched = []

        def launch(*, target, args, **kwargs):
            thread = Thread(target=target, args=args, **kwargs)
            launched.append(thread)
            return thread

        with patch.object(
            runs, "threading", SimpleNamespace(Thread=launch)
        ), patch.object(
            collection,
            "fetch_job_vacancies",
            return_value=[doc.metadata for doc in docs],
        ), patch.object(
            collection, "vectorize_jobs_to_db"
        ), patch.object(
            retrieval, "retrieve_relevant_jobs", return_value=docs
        ), patch.object(
            orchestration, "evaluate_provider", side_effect=evaluate
        ) as models:
            response = self.client.put(
                "/api/searches/test/confirm-profile",
                json={
                    "profile": original_profile,
                    "preferences": {"queries": ["Analyst"], "top_k": 15},
                },
            )
            for thread in launched:
                thread.join(timeout=10)
                self.assertFalse(thread.is_alive())
        # Check the expected behavior: repeat confirm profile adds fifteen to fifty existing results.
        self.assertEqual(response.status_code, 202)
        self.assertEqual(runs.RUNS["test"]["recommendations"][:50], original)
        self.assertEqual(len(runs.RUNS["test"]["recommendations"]), 65)
        self.assertEqual(runs.RUNS["test"]["evaluated_jobs"], 65)
        self.assertEqual(runs.RUNS["test"]["last_search_added"], 15)
        self.assertEqual(models.call_count, 3)
        self.assertTrue(all(len(call.args[1]) == 15 for call in models.call_args_list))
        self.assertTrue(
            all(
                len(row["model_evaluations"]) == 3
                for row in runs.RUNS["test"]["recommendations"][50:]
            )
        )
        persisted = json.loads(runs.run_state_path("test").read_text())
        self.assertEqual(len(persisted["recommendations"]), 65)
        self.assertEqual(runs.RUN_CONTEXTS["test"], "Synthetic candidate")

    def test_legacy_find_jobs_entry_points_append_instead_of_replacing(self):
        for endpoint in ("/api/searches/test/find-jobs", "/api/runs/test/search"):
            with self.subTest(endpoint=endpoint):
                runs.RUNS["test"]["status"] = "complete"
                runs.ACTIVE_WORKERS.clear()
                thread = MagicMock()
                with patch.object(runs, "threading", SimpleNamespace(Thread=thread)):
                    response = self.client.post(
                        endpoint,
                        data={
                            "queries": "Analyst",
                            "top_k": "15",
                            "platforms": "linkedin",
                        },
                    )
                self.assertEqual(response.status_code, 202)
                self.assertTrue(thread.call_args.kwargs["args"][-1]["append"])
                self.assertEqual(thread.call_args.kwargs["args"][-1]["top_k"], 15)
                self.assertEqual(runs.RUNS["test"]["recommendations"], [self.old])

    def test_repeat_confirm_profile_rejects_changed_profile_without_touching_results(
        self,
    ):
        from backend.schemas.resume import ResumeProfile

        changed = ResumeProfile.model_validate(
            runs.RUNS["test"]["profile"]
        ).model_dump()
        changed["tech_skills"] = ["Unrelated skill"]
        before = copy.deepcopy(runs.RUNS["test"])
        response = self.client.put(
            "/api/searches/test/confirm-profile",
            json={"profile": changed, "preferences": {"queries": ["Analyst"]}},
        )
        # Check the expected behavior: repeat confirm profile rejects changed profile without touching results.
        self.assertEqual(response.status_code, 409)
        self.assertIn("Start a new search", response.json()["detail"])
        self.assertEqual(runs.RUNS["test"], before)
        self.assertEqual(runs.RUN_CONTEXTS["test"], "Synthetic candidate")

    def test_find_more_preserves_original_roles_for_legacy_failure_checkpoint(self):
        entry = {
            "page_content": "prior",
            "metadata": {
                "url": self.old["apply_url"],
                "_evaluation_provider": "claude",
            },
        }
        (self.path / "failed_jobs.json").write_text(json.dumps([entry]))
        with patch.object(runs, "threading", SimpleNamespace(Thread=MagicMock())):
            response = self.client.post(
                "/api/searches/test/find-more",
                json={"preferences": {"queries": ["Analyst"]}},
            )
        # Check the expected behavior: find more preserves original roles for legacy failure checkpoint.
        self.assertEqual(response.status_code, 202)
        saved = json.loads((self.path / "failed_jobs.json").read_text())
        self.assertEqual(
            saved[0]["metadata"]["_evaluation_target_roles"], ["Developer"]
        )
        self.assertEqual(runs.RUNS["test"]["search_inputs"]["queries"], ["Analyst"])

    def test_cross_board_duplicate_requires_matching_description_not_title_alone(self):
        old = {
            **self.posting(),
            "description": "Python developer responsible for software and testing. "
            * 6,
        }
        duplicate = {**old, "url": "https://other.test/job"}
        distinct = {
            **old,
            "url": "https://other.test/other",
            "description": "Marketing and sales outreach for new customers. " * 6,
        }
        # Check the expected behavior: cross board duplicate requires matching description not title alone.
        self.assertEqual(unseen_postings([duplicate, distinct], [old]), [distinct])
