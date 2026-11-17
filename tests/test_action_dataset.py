"""Job actions build a labeled dataset in the review-dataset format; synthetic data only."""

import hashlib
import json
import tempfile
import unittest
from collections import defaultdict, deque
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend import app, runs
from backend.evaluation import action_dataset
from backend.schemas.resume import ResumeProfile
from backend.search.preferences import action_key


def job(n, title="Developer"):
    return {
        "title": title,
        "company": "Example",
        "location": "Sydney",
        "apply_url": f"https://example.test/job/{n}",
        "job_description": f"Build Python APIs for team {n}.",
        "fit_category": "strong_match",
        "model_evaluations": {"claude": {"status": "complete", "fit_category": "review", "score": 61}},
    }


class ActionDatasetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.datasets = root / "datasets"
        for patcher in (
            patch.object(action_dataset, "REVIEW_DATASETS_DIR", self.datasets),
            patch("backend.profiles.storage.PROFILES_DIR", root / "profiles"),
            patch.object(runs, "RUNS_DIR", root / "runs"),
            patch.object(runs, "RUNS", {}),
            patch.object(runs, "RUN_CONTEXTS", {}),
            patch.object(runs, "RATE_WINDOWS", defaultdict(deque)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app.app)
        profile = ResumeProfile(name="Synthetic", headline="Developer", profile="Builds APIs")
        self.profile_id = self.client.post(
            "/api/profiles", json={"name": "Synthetic", "profile": profile.model_dump()}
        ).json()["id"]
        self.run = self.client.post(f"/api/profiles/{self.profile_id}/searches").json()["id"]
        self.jobs = [job(1), job(2, "Senior Developer"), job(3)]
        runs.RUNS[self.run]["recommendations"] = self.jobs

    def act(self, row, action, value=True, dismissal=None):
        body = {"key": action_key(row), "action": action, "value": value}
        if dismissal:
            body["dismissal"] = dismissal
        response = self.client.put(f"/api/searches/{self.run}/actions", json=body)
        self.assertEqual(response.status_code, 200, response.text)

    def files(self):
        directory = self.datasets / action_dataset.dataset_id(self.profile_id)
        return (
            json.loads((directory / "dataset.json").read_text()),
            json.loads((directory / "reviews.json").read_text()),
        )

    def test_actions_label_jobs_in_the_review_dataset_format(self):
        self.act(self.jobs[0], "applied")
        self.act(self.jobs[1], "dismissed", dismissal={"reason": "seniority"})
        self.act(self.jobs[2], "dismissed", dismissal={"reason": "location"})
        self.act(self.jobs[0], "saved")  # Saving alone is not a label.
        dataset, reviews = self.files()
        ids = [action_dataset.posting_id(j["apply_url"], j["title"], j["company"], j["job_description"]) for j in self.jobs]
        self.assertEqual(
            {key: review["fit"] for key, review in reviews["jobs"].items()},
            {ids[0]: "strong_match", ids[1]: "not_suitable", ids[2]: None},
        )
        self.assertEqual(reviews["jobs"][ids[2]]["notes"], "Dismissed: location")
        self.assertEqual(set(reviews["reviewers"].values()), {"job action"})
        # Same top-level and per-job fields as the earlier review datasets.
        pilot_fields = {"id", "created_at", "source_id", "fingerprint", "scope", "split", "profile",
                        "profile_text", "target_roles", "jobs", "verdicts_added_at"}
        self.assertLessEqual(pilot_fields, dataset.keys())
        self.assertEqual(dataset["split"], "pilot")
        by_id = {item["id"]: item for item in dataset["jobs"]}
        self.assertIn("explicit_seniority_title", by_id[ids[1]]["tags"])
        self.assertEqual(by_id[ids[0]]["model_verdicts"]["claude"]["fit_category"], "review")
        self.assertEqual(by_id[ids[0]]["app_verdict"], "strong_match")
        self.assertEqual(set(reviews["jobs"][ids[0]]), {
            "fit", "ai_assisted", "notes", "extraction_complete", "criteria",
            "missing_requirements", "evidence",
        })

    def test_undo_removes_the_label_but_keeps_the_posting(self):
        self.act(self.jobs[0], "applied")
        self.act(self.jobs[0], "applied", value=False)
        dataset, reviews = self.files()
        self.assertEqual(reviews["jobs"], {})
        self.assertNotIn("applied", dataset["jobs"][0]["tags"])

    def test_a_later_dismissal_overrides_applied_and_hand_labels_are_kept(self):
        self.act(self.jobs[0], "applied")
        self.act(self.jobs[0], "dismissed", dismissal={"reason": "role"})
        _, reviews = self.files()
        (only,) = reviews["jobs"].values()
        self.assertEqual(only["fit"], "not_suitable")
        # A label someone made by hand is never replaced by an action.
        directory = self.datasets / action_dataset.dataset_id(self.profile_id)
        job_id = next(iter(reviews["jobs"]))
        reviews["reviewers"][job_id] = "Alex"
        reviews["jobs"][job_id]["fit"] = "review"
        (directory / "reviews.json").write_text(json.dumps(reviews))
        self.act(self.jobs[0], "dismissed", value=False)
        self.assertEqual(self.files()[1]["jobs"][job_id]["fit"], "review")

    def test_posting_ids_match_the_earlier_datasets(self):
        url = "https://example.test/job/1"
        self.assertEqual(
            action_dataset.posting_id(url, "Dev", "Acme", "text"),
            hashlib.sha256(url.encode()).hexdigest()[:24],
        )
        self.assertEqual(
            action_dataset.posting_id("No URL provided", "Dev", "Acme", "text"),
            hashlib.sha256(b"DevAcmetext").hexdigest()[:24],
        )


if __name__ == "__main__":
    unittest.main()
