# Regression coverage for embedding text; fixtures and assertions document the expected behavior.
import unittest
from backend.search.embedding_text import (
    profile_embedding_text,
    job_embedding_text,
    clean_job_description,
)


class EmbeddingTextTests(unittest.TestCase):
    def test_profile_omits_noise_and_favors_recent_roles(self):
        text = profile_embedding_text(
            {
                "name": "Private Name",
                "headline": "Developer",
                "profile": "Builds APIs",
                "tech_skills": ["Python"],
                "soft_skills": ["Teamwork"],
                "education": ["Private University"],
                "years_of_experience": 15,
                "career_level": "senior",
                "experience_evidence": ["private tenure"],
                "preferred_domains": ["Healthcare"],
                "work_history": [
                    "Old retail role 2001-2003",
                    "Engineer 2020-2022",
                    "Developer 2023-Present",
                    "Analyst 2018-2019",
                ],
            }
        )
        for omitted in [
            "Private Name",
            "Teamwork",
            "Private University",
            "senior",
            "private tenure",
            "Old retail",
        ]:
            self.assertNotIn(omitted, text)
        for kept in ["Developer", "Builds APIs", "Python", "Healthcare", "Analyst"]:
            self.assertIn(kept, text)
        # Check the expected behavior: profile omits noise and favors recent roles.
        self.assertLess(text.index("Developer 2023"), text.index("Engineer 2020"))

    def test_job_strips_boilerplate_but_resumes_at_requirements(self):
        text = job_embedding_text(
            {
                "title": "Engineer",
                "company": "PrivateCo",
                "location": "Sydney",
                "description": "<h2>About us</h2><p>We sell widgets.</p><h2>Responsibilities</h2><p>Build Python APIs.</p>"
                "<h2>Benefits</h2><p>Free lunch.</p><h2>Requirements</h2><p>SQL and a degree required.</p>"
                "<h2>How to apply</h2><p>Email HR.</p>",
            }
        )
        for omitted in ["PrivateCo", "Sydney", "widgets", "lunch", "Email HR"]:
            self.assertNotIn(omitted, text)
        # Check the expected behavior: job strips boilerplate but resumes at requirements.
        self.assertIn("Build Python APIs.", text)
        self.assertIn("SQL and a degree required.", text)

    def test_unstructured_description_and_inline_sections(self):
        # Check the expected behavior: unstructured description and inline sections.
        self.assertEqual(
            clean_job_description("Build APIs and use SQL."), "Build APIs and use SQL."
        )
        self.assertEqual(
            clean_job_description(
                "Benefits: Lunch\nRequirements: Python\nResponsibilities: Build APIs"
            ),
            "Python\nBuild APIs",
        )

    def test_missing_fields_are_safe(self):
        # Check the expected behavior: missing fields are safe.
        self.assertEqual(profile_embedding_text({}), "")
        self.assertIn("Job title:", job_embedding_text({}))


class EmbeddingBoundaryTests(unittest.TestCase):
    def test_only_focused_text_is_stored_and_full_text_is_restored(self):
        from unittest.mock import patch, MagicMock
        from types import SimpleNamespace
        from backend.search.collection import vectorize_jobs_to_db
        from backend.search.retrieval import retrieve_relevant_jobs

        job = {
            "title": "Engineer",
            "company": "ExampleCo",
            "location": "Sydney",
            "url": "https://example.test/job",
            "source_platform": "test",
            "description": "Responsibilities:\nPython APIs\nBenefits:\nFree lunch",
        }
        chroma = MagicMock()
        create = chroma.from_documents
        modules = {
            "langchain_openai": SimpleNamespace(OpenAIEmbeddings=MagicMock()),
            "langchain_chroma": SimpleNamespace(Chroma=chroma),
        }
        with patch.dict("sys.modules", modules):
            vectorize_jobs_to_db([job], "/unused")
        document = create.call_args.kwargs["documents"][0]
        # Check the expected behavior: only focused text is stored and full text is restored.
        self.assertNotIn("ExampleCo", document.page_content)
        self.assertNotIn("Free lunch", document.page_content)
        self.assertIn("Free lunch", document.metadata["original_content"])
        store = MagicMock()
        store._collection.count.return_value = 1
        store.similarity_search.return_value = [document]
        chroma.return_value = store
        with patch.dict("sys.modules", modules):
            result = retrieve_relevant_jobs("Technical skills: Python", "/unused")
        self.assertIn("ExampleCo", result[0].page_content)
        self.assertIn("Free lunch", result[0].page_content)


if __name__ == "__main__":
    unittest.main()
