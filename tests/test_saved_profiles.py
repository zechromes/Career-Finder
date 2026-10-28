from backend import runs

# Regression coverage for saved profiles; fixtures and assertions document the expected behavior.
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import app as web
from backend.schemas.resume import ResumeProfile


class SavedProfileTests(unittest.TestCase):
    def test_save_edit_continue_delete_and_reload(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "backend.profiles.storage.PROFILES_DIR", Path(directory) / "profiles"
        ), patch.object(runs, "RUNS_DIR", Path(directory) / "runs"), patch.object(
            runs, "RUNS", {}
        ), patch.object(
            runs, "RUN_CONTEXTS", {}
        ):
            client = TestClient(web.app)
            body = {
                "name": "Engineering",
                "profile": ResumeProfile(
                    name="Candidate", headline="Engineer", profile="Builds APIs"
                ).model_dump(),
            }
            saved = client.post("/api/profiles", json=body)
            self.assertEqual(saved.status_code, 201, saved.text)
            profile_id = saved.json()["id"]
            self.assertEqual(
                client.get("/api/profiles").json()[0]["name"], "Engineering"
            )
            body["name"] = "Updated profile"
            body["profile"]["tech_skills"] = ["Python"]
            self.assertEqual(
                client.put(f"/api/profiles/{profile_id}", json=body).status_code, 200
            )
            created = client.post(f"/api/profiles/{profile_id}/searches")
            self.assertEqual(created.status_code, 201, created.text)
            run_id = created.json()["runId"]
            response = client.get(f"/api/searches/{run_id}")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["status"], "awaiting_search")
            self.assertEqual(response.json()["profile"]["tech_skills"], ["Python"])
            self.assertIn("Python", runs.RUN_CONTEXTS[run_id])
            self.assertFalse(
                (Path(directory) / "runs" / run_id / "resume.pdf").exists()
            )
            self.assertEqual(
                client.delete(f"/api/profiles/{profile_id}").status_code, 200
            )
            self.assertEqual(client.get("/api/profiles").json(), [])
            self.assertEqual(client.get(f"/api/searches/{run_id}").status_code, 200)
            self.assertEqual(
                client.post(f"/api/profiles/{profile_id}/searches").status_code, 404
            )

    def test_rejects_blank_names_and_invalid_ids(self):
        client = TestClient(web.app)
        # Check the expected behavior: rejects blank names and invalid ids.
        self.assertEqual(client.delete("/api/profiles/invalid").status_code, 404)
        body = {
            "name": "   ",
            "profile": ResumeProfile(
                name="Candidate", headline="", profile=""
            ).model_dump(),
        }
        self.assertEqual(client.post("/api/profiles", json=body).status_code, 422)

    def test_resume_survives_source_deletion_and_is_restored(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "backend.profiles.storage.PROFILES_DIR", Path(directory) / "profiles"
        ), patch.object(runs, "RUNS_DIR", Path(directory) / "runs"), patch.object(
            runs, "RUNS", {}
        ), patch.object(
            runs, "RUN_CONTEXTS", {}
        ):
            import shutil

            client = TestClient(web.app)
            source_id = "a" * 32
            source = runs.RUNS_DIR / source_id
            source.mkdir(parents=True)
            pdf = b"%PDF-1.4 original resume"
            (source / "resume.pdf").write_bytes(pdf)
            body = {
                "name": "Resume",
                "source_run_id": source_id,
                "profile": ResumeProfile(
                    name="Candidate", headline="Engineer", profile="Builds APIs"
                ).model_dump(),
            }
            response = client.post("/api/profiles", json=body)
            self.assertEqual(response.status_code, 201, response.text)
            saved = response.json()
            self.assertTrue(saved["resume_available"])
            profile_id = saved["id"]
            shutil.rmtree(source)
            self.assertEqual(
                client.get(f"/api/profiles/{profile_id}/resume").content, pdf
            )
            body.pop("source_run_id")
            body["profile"]["profile"] = "Updated experience"
            self.assertTrue(
                client.put(f"/api/profiles/{profile_id}", json=body).json()[
                    "resume_available"
                ]
            )
            continued = client.post(f"/api/profiles/{profile_id}/searches").json()[
                "runId"
            ]
            self.assertEqual(
                (runs.RUNS_DIR / continued / "resume.pdf").read_bytes(), pdf
            )
            self.assertIn("Updated experience", runs.RUN_CONTEXTS[continued])
            client.delete(f"/api/profiles/{profile_id}")
            self.assertFalse((Path(directory) / "profiles" / profile_id).exists())
            self.assertEqual(
                (runs.RUNS_DIR / continued / "resume.pdf").read_bytes(), pdf
            )
            body["source_run_id"] = source_id
            self.assertEqual(client.post("/api/profiles", json=body).status_code, 409)

    def test_continue_retains_results_and_fresh_search_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "backend.profiles.storage.PROFILES_DIR", Path(directory) / "profiles"
        ), patch.object(runs, "RUNS_DIR", Path(directory) / "runs"), patch.object(
            runs, "RUNS", {}
        ), patch.object(
            runs, "RUN_CONTEXTS", {}
        ):
            client = TestClient(web.app)
            body = {
                "name": "Engineering",
                "profile": ResumeProfile(
                    name="Candidate", headline="Engineer", profile="Builds APIs"
                ).model_dump(),
            }
            profile_id = client.post("/api/profiles", json=body).json()["id"]
            endpoint = f"/api/profiles/{profile_id}/searches"
            first = client.post(endpoint).json()["runId"]
            runs.RUNS[first].update(
                status="complete",
                phase=4,
                recommendations=[{"title": "Existing match"}],
                excluded_recommendations=[{"title": "Existing exclusion"}],
            )
            restored = client.post(endpoint).json()["runId"]
            self.assertEqual(restored, first)
            self.assertEqual(
                runs.RUNS[restored]["recommendations"][0]["title"], "Existing match"
            )
            self.assertEqual(len(runs.RUNS[restored]["excluded_recommendations"]), 1)
            fresh = client.post(endpoint + "?fresh=true").json()["runId"]
            self.assertNotEqual(fresh, first)
            self.assertEqual(runs.RUNS[fresh]["recommendations"], [])
            self.assertEqual(client.post(endpoint).json()["runId"], first)
            runs.RUNS[fresh].update(phase=2, status="running")
            self.assertEqual(client.post(endpoint).json()["runId"], fresh)
