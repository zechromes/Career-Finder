"""Tailored resumes come from the candidate's own resume; synthetic data, no provider calls."""

import tempfile
import unittest
from collections import defaultdict, deque
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from backend import app, runs
from backend.profiles import tailoring
from backend.schemas.resume import ResumeProfile
from backend.schemas.tailored_resume import TailoredResumeDraft

RESUME = (
    "Sam Example | sam@example.test\n"
    "Data Engineer, Acme, 2023 - Present\n"
    "Built Python ETL pipelines on Airflow processing 40 million rows a day.\n"
    "Skills: Python, Airflow, SQL"
)
DRAFT = {
    "name": "Sam Example",
    "headline": "Data Engineer",
    "contact": ["sam@example.test"],
    "profile_points": ["Built Python ETL pipelines on Airflow at Acme"],
    "skills": ["Python", "Airflow", "Kubernetes"],
    "sections": [
        {
            "title": "Relevant Experience",
            "entries": [
                {
                    "heading": "Data Engineer, Acme",
                    "dates": "2023 - Present",
                    "bullets": [
                        "Built Python ETL pipelines on Airflow processing 40 million rows a day.",
                        "Cut pipeline costs by 30%.",
                    ],
                }
            ],
        }
    ],
    "gaps": ["Kubernetes"],
}
JOB = {
    "title": "Data Engineer",
    "company": "Example Co",
    "apply_url": "https://example.test/job/1",
    "job_description": "Python, Airflow and Kubernetes required.",
    "model_evaluations": {
        "claude": {
            "status": "complete",
            "requirement_verdicts": [
                {"requirement": "Python", "verdict": "met", "importance": "must_have", "job_quote": "Python"},
                {"requirement": "Kubernetes", "verdict": "not_met", "importance": "must_have", "job_quote": "Kubernetes"},
            ],
        }
    },
}


def fake_llm(output):
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = output
    return llm


class TailoredResumeTests(unittest.TestCase):
    def test_flags_skills_and_figures_the_resume_does_not_contain(self):
        flagged = tailoring.unverified(TailoredResumeDraft.model_validate(DRAFT), RESUME)
        self.assertEqual(flagged, ["Kubernetes", "Cut pipeline costs by 30%."])

    def test_prompt_uses_the_original_resume_and_assessed_requirements(self):
        llm = fake_llm(DRAFT)
        with patch("backend.evaluation.providers.create_evaluation_llm", return_value=llm) as create:
            resume = tailoring.generate({"source_text": RESUME}, JOB)
        create.assert_called_once_with("claude")
        prompt = llm.with_structured_output.return_value.invoke.call_args.args[0]
        self.assertIn("40 million rows", prompt)
        self.assertIn("- [not_met] Kubernetes", prompt)
        self.assertIn("Never add, estimate or inflate", prompt)
        # The guide's structure: career profile, achievement statements, early-career Education.
        self.assertIn("profile_points: the career profile, 3 to 5", prompt)
        self.assertIn("active verb + task + outcome or purpose", prompt)
        self.assertIn("this candidate is not early-career", prompt)
        self.assertEqual(resume["gaps"], ["Kubernetes"])
        self.assertIn("Cut pipeline costs by 30%", resume["unverified"])

    def test_tidy_strips_markup_symbols_repeats_and_empty_items(self):
        messy = TailoredResumeDraft.model_validate(
            {
                "name": "  Sam   Example ",
                "skills": ["**Python**", "python", "", "SQL"],
                "contact": ["", "sam@example.test"],
                "sections": [
                    {
                        "title": "Experience",
                        "entries": [
                            {
                                "heading": "**Data Engineer**",
                                "organization": "Acme",
                                "bullets": ["• Built `ETL` pipelines.", "- ", "Led reviews"],
                            },
                            {"heading": "", "bullets": []},
                        ],
                    },
                    {"title": "Empty", "entries": []},
                ],
            }
        )
        clean = tailoring.tidy(messy)
        self.assertEqual(clean.name, "Sam Example")
        self.assertEqual(clean.skills, ["Python", "SQL"])
        self.assertEqual(clean.contact, ["sam@example.test"])
        self.assertEqual([section.title for section in clean.sections], ["Relevant Experience"])
        (entry,) = clean.sections[0].entries
        self.assertEqual((entry.heading, entry.organization), ("Data Engineer", "Acme"))
        self.assertEqual(entry.bullets, ["Built ETL pipelines", "Led reviews"])

    def test_sections_use_the_guide_titles_and_order_by_career_stage(self):
        entry = {"heading": "Item", "bullets": ["Did work"]}
        draft = TailoredResumeDraft.model_validate(
            {
                "sections": [
                    {"title": "Referees", "entries": [entry]},
                    {"title": "Interests", "entries": [entry]},
                    {"title": "Volunteering", "entries": [entry]},
                    {"title": "Academic Background", "entries": [entry]},
                    {"title": "Work History", "entries": [entry]},
                    {"title": "Professional Experience", "entries": [entry]},
                    {"title": "Employment", "entries": [{**entry, "heading": "Later"}]},
                ]
            }
        )
        experienced = [s.title for s in tailoring.tidy(draft).sections]
        self.assertEqual(
            experienced,
            [
                "Additional Experience",
                "Relevant Experience",
                "Education",
                "Volunteer Experience",
                "Interests",
                "Referees",
            ],
        )
        early = [s.title for s in tailoring.tidy(draft, early=True).sections]
        self.assertEqual(early[0], "Education")
        # Work History and Employment merge into one Additional Experience section.
        merged = tailoring.tidy(draft).sections[0]
        self.assertEqual([e.heading for e in merged.entries], ["Item", "Later"])

    def test_contact_and_name_follow_the_guide(self):
        draft = TailoredResumeDraft.model_validate(
            {
                "name": "Sam Example Resume",
                "contact": ["0400 123 123", "Date of birth: 1 Jan 2000", "Gender: female", "Sydney NSW"],
                "profile_points": ["o Built pipelines.", "o", "operated Airflow"],
            }
        )
        clean = tailoring.tidy(draft)
        self.assertEqual(clean.name, "Sam Example")
        self.assertEqual(clean.contact, ["0400 123 123", "Sydney NSW"])
        # An "o " bullet is stripped, but a word starting with "o" is kept.
        self.assertEqual(clean.profile_points, ["Built pipelines", "o", "operated Airflow"])

    def test_early_career_from_level_or_years(self):
        self.assertTrue(tailoring.early_career({"career_level": "graduate"}))
        self.assertTrue(tailoring.early_career({"years_of_experience": 1.5}))
        self.assertFalse(tailoring.early_career({"career_level": "mid", "years_of_experience": 4}))

    def api(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for patcher in (
            patch("backend.profiles.storage.PROFILES_DIR", root / "profiles"),
            patch.object(runs, "RUNS_DIR", root / "runs"),
            patch.object(runs, "RUNS", {}),
            patch.object(runs, "RUN_CONTEXTS", {}),
            patch.object(runs, "RATE_WINDOWS", defaultdict(deque)),
            patch("backend.evaluation.action_dataset.REVIEW_DATASETS_DIR", root / "datasets"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        client = TestClient(app.app)
        profile = ResumeProfile(name="Sam", headline="Data Engineer", source_text=RESUME)
        saved = client.post(
            "/api/profiles", json={"name": "Sam", "profile": profile.model_dump()}
        ).json()
        run_id = client.post(f"/api/profiles/{saved['id']}/searches").json()["id"]
        runs.RUNS[run_id]["recommendations"] = [dict(JOB)]
        return client, run_id

    def test_api_saves_the_resume_with_the_job(self):
        client, run_id = self.api()
        with patch("backend.evaluation.providers.create_evaluation_llm", return_value=fake_llm(DRAFT)):
            response = client.post(
                f"/api/searches/{run_id}/tailored-resume", json={"key": JOB["apply_url"]}
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "Sam Example")
        saved = runs.RUNS[run_id]["recommendations"][0]["tailored_resume"]
        self.assertEqual(saved["skills"], ["Python", "Airflow", "Kubernetes"])
        snapshot = client.get(f"/api/searches/{run_id}").json()
        self.assertEqual(snapshot["recommendations"][0]["tailored_resume"]["gaps"], ["Kubernetes"])

    def test_api_reports_failures_and_unknown_jobs_without_saving(self):
        client, run_id = self.api()
        missing = client.post(f"/api/searches/{run_id}/tailored-resume", json={"key": "https://x.test"})
        self.assertEqual(missing.status_code, 404)
        broken = MagicMock()
        broken.with_structured_output.return_value.invoke.side_effect = RuntimeError("401 authentication")
        with patch("backend.evaluation.providers.create_evaluation_llm", return_value=broken):
            failed = client.post(
                f"/api/searches/{run_id}/tailored-resume", json={"key": JOB["apply_url"]}
            )
        self.assertEqual(failed.status_code, 503)
        self.assertIn("credentials", failed.json()["detail"])
        self.assertNotIn("tailored_resume", runs.RUNS[run_id]["recommendations"][0])


if __name__ == "__main__":
    unittest.main()
