"""Automatic completed-search saving uses isolated synthetic workspaces."""

from backend.search import service as search_service
from backend.search import collection
from backend import runs
from backend.profiles import service as profiles_service


import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.profiles import storage


class ProfileAutosaveTests(unittest.TestCase):
    # Initialize per-test state; individual cases supply additional fixtures and patches.
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for module, name, value in [
            (runs, "RUNS_DIR", root / "runs"),
            (storage, "PROFILES_DIR", root / "profiles"),
            (runs, "RUNS", {}),
            (runs, "RUN_CONTEXTS", {}),
        ]:
            item = patch.object(module, name, value)
            item.start()
            self.addCleanup(item.stop)
        self.run_id = "a" * 32
        directory = runs.RUNS_DIR / self.run_id
        directory.mkdir(parents=True)
        (directory / "resume.pdf").write_bytes(b"%PDF-1.4 synthetic")
        runs.RUNS[self.run_id] = dict(
            id=self.run_id,
            created_at=time.time(),
            status="complete",
            profile={"name": "Example Candidate", "career_level": "graduate"},
            preferences={"queries": ["Developer"], "seniority": "auto"},
        )

    def test_completed_search_is_saved_and_reused_without_duplicates(self):
        profiles_service.save_completed_search_profile(self.run_id)
        profile_id = runs.RUNS[self.run_id]["saved_profile_id"]
        saved = storage.read_profile(profile_id)
        # Check the expected behavior: completed search is saved and reused without duplicates.
        self.assertTrue(saved["resume_available"])
        self.assertEqual(saved["preferences"]["seniority"], "auto")
        self.assertEqual(saved["source_run_id"], self.run_id)
        runs.RUNS[self.run_id]["profile"]["tech_skills"] = ["Python"]
        profiles_service.save_completed_search_profile(self.run_id)
        self.assertEqual(len(storage.list_profiles()), 1)
        self.assertEqual(
            storage.read_profile(profile_id)["profile"]["tech_skills"], ["Python"]
        )

    def test_successful_empty_search_triggers_autosave(self):
        runs.RUNS[self.run_id]["status"] = "running"
        runs.RUN_CONTEXTS[self.run_id] = "Example graduate"
        with patch.object(collection, "fetch_job_vacancies", return_value=[]):
            search_service.execute_job_search(
                self.run_id,
                None,
                dict(
                    queries=["Developer"],
                    locations=[],
                    platforms=["linkedin"],
                    remote=False,
                    posted_days_old=7,
                    top_k=15,
                    persist_dir=str(runs.RUNS_DIR / self.run_id / "vectors"),
                ),
            )
        # Check the expected behavior: successful empty search triggers autosave.
        self.assertEqual(runs.RUNS[self.run_id]["status"], "complete")
        self.assertEqual(len(storage.list_profiles()), 1)
        self.assertTrue(runs.RUNS[self.run_id]["saved_profile_id"])

    def test_failed_save_retains_results_and_can_be_retried(self):
        runs.RUNS[self.run_id]["recommendations"] = [{"title": "Developer"}]
        with patch.object(
            storage, "create_profile", side_effect=OSError("Disk unavailable")
        ):
            profiles_service.save_completed_search_profile(self.run_id)
        # Check the expected behavior: failed save retains results and can be retried.
        self.assertEqual(runs.RUNS[self.run_id]["status"], "complete")
        self.assertEqual(len(runs.RUNS[self.run_id]["recommendations"]), 1)
        self.assertTrue(runs.RUNS[self.run_id]["profile_save_error"])
        profiles_service.save_completed_search_profile(self.run_id)
        self.assertIsNone(runs.RUNS[self.run_id]["profile_save_error"])

    def test_profile_only_workspace_and_cancelled_search(self):
        (runs.RUNS_DIR / self.run_id / "resume.pdf").unlink()
        profiles_service.save_completed_search_profile(self.run_id)
        # Check the expected behavior: profile only workspace and cancelled search.
        self.assertFalse(storage.list_profiles()[0]["resume_available"])
        runs.RUNS[self.run_id].update(
            status="cancelled", profile={"name": "Do not save"}
        )
        profiles_service.save_completed_search_profile(self.run_id)
        self.assertEqual(
            storage.list_profiles()[0]["profile"]["name"], "Example Candidate"
        )
