"""Synthetic preference persistence and shortlist behavior; no provider requests."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from collections import defaultdict, deque
from langchain_core.documents import Document
from fastapi.testclient import TestClient
from backend import runs, app
from backend.schemas.resume import ResumeProfile
from backend.schemas.contracts import DismissalInput
from backend.search.preferences import (
    make_preference,
    prioritize_preferences,
    stated_pay,
    action_key,
    load_feedback,
)


class PreferenceTests(unittest.TestCase):
    def doc(self, title="Developer", location="Sydney", text=""):
        return Document(
            page_content=text,
            metadata={"title": title, "location": location, "job_description": text},
        )

    def feedback(self, reason, title="Developer", location="Sydney", **kwargs):
        return {
            "example": make_preference(
                DismissalInput(reason=reason, **kwargs),
                {"title": title, "location": location},
            )
        }

    def test_role_and_location_demote_only_explicit_matches_without_dropping_jobs(self):
        docs = [
            self.doc(),
            self.doc("Analyst", "Melbourne"),
            self.doc("Developer", "Unknown Location"),
        ]
        self.assertEqual(
            prioritize_preferences(docs, self.feedback("role")),
            [docs[1], docs[0], docs[2]],
        )
        self.assertEqual(
            prioritize_preferences(docs, self.feedback("location")),
            [docs[1], docs[2], docs[0]],
        )
        self.assertEqual(prioritize_preferences(docs, {}), docs)
        self.assertEqual(prioritize_preferences(docs, self.feedback("other")), docs)
        self.assertEqual(
            prioritize_preferences(
                docs, self.feedback("location", location="Unknown Location")
            ),
            docs,
        )

    def test_seniority_never_infers_level_for_unmarked_or_mixed_titles(self):
        docs = [
            self.doc("Senior Developer"),
            self.doc("Developer"),
            self.doc("Junior/Senior Developer"),
            self.doc("Lead Analyst"),
        ]
        ordered = prioritize_preferences(
            docs, self.feedback("seniority", title="Senior Analyst")
        )
        self.assertEqual(ordered, [docs[1], docs[2], docs[0], docs[3]])
        self.assertEqual(
            prioritize_preferences(docs, self.feedback("seniority", title="Developer")),
            docs,
        )

    def test_salary_requires_comparable_explicit_closed_range(self):
        feedback = self.feedback(
            "salary", minimum_salary=100000, currency="AUD", period="year"
        )
        texts = [
            "Salary AUD 70k–90k per year",
            "Salary AUD 90k–110k per year",
            "Salary USD 70k–90k per year",
            "Salary AUD 70–90 per hour",
            "Salary $70k–90k per year",
            "No salary stated",
            "Salary from AUD 80k per year",
            "Salary AUD 80k+ per year",
            "Salary AUD 100k per year",
            "Budget AUD 70k per year",
        ]
        docs = [self.doc(text=text) for text in texts]
        self.assertEqual(prioritize_preferences(docs, feedback), docs[1:] + docs[:1])
        self.assertIsNone(stated_pay("Salary AUD 80k per year and above"))
        self.assertIsNone(stated_pay("Salary AUD 80k per year plus commission"))
        self.assertIsNone(stated_pay("Salary AUD 70k–USD 90k per year"))
        self.assertIsNone(stated_pay("Salary AUD 90k–70k per year"))
        self.assertIsNone(stated_pay("Salary AUD 80k/year or salary AUD 120k/year"))
        with self.assertRaises(ValueError):
            DismissalInput(reason="salary")

    def test_api_feedback_survives_profile_edit_new_run_and_can_be_removed(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.profiles.storage.PROFILES_DIR", Path(tmp) / "profiles"
        ), patch.object(runs, "RUNS_DIR", Path(tmp) / "runs"), patch.object(
            runs, "RUNS", {}
        ), patch.object(
            runs, "RUN_CONTEXTS", {}
        ), patch.object(
            runs, "RATE_WINDOWS", defaultdict(deque)
        ):
            client = TestClient(app.app)
            body = {
                "name": "Synthetic",
                "profile": ResumeProfile(
                    name="Synthetic", headline="Developer", profile="Builds APIs"
                ).model_dump(),
            }
            saved = client.post("/api/profiles", json=body).json()
            first = client.post(f"/api/profiles/{saved['id']}/searches").json()["id"]
            job = {
                "title": "Senior Developer",
                "company": "Example",
                "location": "Sydney",
                "apply_url": "https://example.test/job?utm_source=board#detail",
            }
            runs.RUNS[first]["recommendations"] = [job]
            key = action_key(job)
            update = {
                "key": key,
                "action": "dismissed",
                "value": True,
                "dismissal": {"reason": "seniority"},
            }
            response = client.put(f"/api/searches/{first}/actions", json=update)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(
                response.json()["dismissal_feedback"][key]["seniority"], "senior"
            )
            # Legacy clients toggling another flag cannot erase learned preferences.
            client.put(
                f"/api/searches/{first}/actions",
                json={"key": key, "action": "saved", "value": True},
            )
            client.put(f"/api/profiles/{saved['id']}", json=body)
            second = client.post(
                f"/api/profiles/{saved['id']}/searches?fresh=true"
            ).json()["id"]
            state = client.get(f"/api/searches/{second}/actions").json()
            self.assertIn(key, state["dismissal_feedback"])
            self.assertEqual(load_feedback(second), state["dismissal_feedback"])
            # Another profile does not inherit this preference.
            other = client.post("/api/profiles", json={**body, "name": "Other"}).json()
            third = client.post(f"/api/profiles/{other['id']}/searches").json()["id"]
            self.assertEqual(
                client.get(f"/api/searches/{third}/actions").json()[
                    "dismissal_feedback"
                ],
                {},
            )
            response = client.put(
                f"/api/searches/{second}/actions",
                json={
                    "key": key,
                    "action": "dismissed",
                    "value": True,
                    "dismissal": None,
                },
            )
            self.assertEqual(response.json()["dismissal_feedback"], {})
            self.assertTrue(response.json()["actions"][key]["dismissed"])
            # Re-add through the original job, then restore through a fresh workspace.
            client.put(f"/api/searches/{first}/actions", json=update)
            response = client.put(
                f"/api/searches/{second}/actions",
                json={"key": key, "action": "dismissed", "value": False},
            )
            self.assertEqual(response.json()["dismissal_feedback"], {})
            self.assertTrue(response.json()["actions"][key]["saved"])
            bad = client.put(
                f"/api/searches/{second}/actions",
                json={**update, "key": "https://example.test/foreign"},
            )
            self.assertEqual(bad.status_code, 422)
            self.assertNotIn(
                "https://example.test/foreign",
                client.get(f"/api/searches/{second}/actions").json()["actions"],
            )
            self.assertEqual(
                client.put(
                    f"/api/searches/{first}/actions",
                    json={**update, "dismissal": {"reason": "salary"}},
                ).status_code,
                422,
            )
