# Regression coverage for description capture; fixtures and assertions document the expected behavior.
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from backend.search.collection import _description_value, fetch_job_vacancies
from backend.schemas.evaluation import JobEvaluation, RequirementSet
from backend.evaluation.providers import evaluate_jobs


class DescriptionCaptureTests(unittest.TestCase):
    def setUp(self):
        cache_setting = patch.dict(
            "os.environ", {"JOB_COLLECTION_CACHE_TTL_SECONDS": "0"}
        )
        cache_setting.start()
        self.addCleanup(cache_setting.stop)

    def test_prefers_full_description_over_empty_or_short_alias(self):
        # Check the expected behavior: prefers full description over empty or short alias.
        self.assertEqual(
            _description_value(
                {"description": "", "job_description": "Build APIs with Python."}
            ),
            "Build APIs with Python.",
        )
        self.assertEqual(
            _description_value(
                {
                    "description": "Short",
                    "descriptionHtml": "<p>Full description with requirements</p>",
                }
            ),
            "<p>Full description with requirements</p>",
        )

    def test_linkedin_requests_full_description_with_search(self):
        import pandas as pd

        frame = pd.DataFrame(
            [
                {
                    "title": "Engineer",
                    "company": "Example",
                    "location": "Sydney",
                    "description": "Python required.",
                    "job_url": "https://example.test/job",
                }
            ]
        )
        with patch("jobspy.scrape_jobs", return_value=frame) as scrape, patch.dict(
            "os.environ", {"JOB_SEARCH_PROVIDER": "jobspy", "APIFY_API_KEY": ""}
        ):
            jobs = fetch_job_vacancies(
                ["Engineer"], ["Sydney"], ["linkedin"], posted_days_old=0
            )
        supplied = scrape.call_args.kwargs
        # Search cards are collected without per-job page requests; descriptions
        # are hydrated afterwards for screened jobs and must still be preserved.
        self.assertTrue(supplied["fetch_description"])
        self.assertEqual(supplied["description_format"], "markdown")
        self.assertEqual(jobs[0]["description"], "Python required.")

    def test_absent_description_cannot_produce_invented_analysis(self):
        evaluation = JobEvaluation(
            score=95,
            fit_category="strong_match",
            experience_alignment="meets",
            about_company="Invented company facts",
            candidate_requirements=["Invented skill"],
            missing_skills=["Invented skill"],
            match_rationale="Optimistic",
            apply_url="https://example.test",
        )
        client = SimpleNamespace(
            with_structured_output=lambda *args, **kwargs: RunnableLambda(
                lambda prompt: evaluation
            )
        )
        job = Document(
            page_content="Job Title: Engineer\nDescription:",
            metadata={"job_description": "", "title": "Engineer"},
        )
        with patch(
            "backend.evaluation.providers.create_evaluation_llm", return_value=client
        ):
            result = evaluate_jobs(
                "Python developer",
                [job],
                include_all=True,
                provider="gpt",
                requirement_loader=lambda job: RequirementSet(
                    posting_hash="test",
                    extraction_model="test",
                    extraction_version="test",
                    requirements=[],
                ),
            )[0]
        # Check the expected behavior: absent description cannot produce invented analysis.
        self.assertIsNone(result["score"])
        self.assertEqual(result["fit_category"], "review")
        self.assertEqual(result["candidate_requirements"], [])
        self.assertEqual(result["about_company"], "")
        self.assertEqual(result["missing_skills"], [])
