# Label-free upload checks compare the extracted profile with its own resume text.
import unittest

from backend.evaluation.upload_check import check
from backend.schemas.resume import ResumeProfile

RESUME = """Data Analyst | Example Co | March 2024 – Present
Built SQL dashboards in Tableau.
Bachelor of Computing | Example University | 2020 – 2023
Projects: Job tracker built with Python
Skills: Python, SQL"""


class UploadCheckTests(unittest.TestCase):
    def profile(self, **values):
        fields = dict(
            name="Candidate",
            work_history=["Data Analyst | Example Co | March 2024 – Present | Built SQL dashboards in Tableau"],
            education=["Bachelor of Computing | Example University | 2020 – 2023"],
            tech_skills=["Python", "SQL"],
            years_of_experience=1.5,
            preferred_domains=["Junior Data Analyst"],
            section_headings=["Experience", "Education", "Projects", "Certifications"],
            sections=[{"heading": "Projects", "entries": ["Job tracker | Personal | Built with Python"]}],
            source_text=RESUME,
        )
        return ResumeProfile(**(fields | values))

    def test_a_faithful_profile_only_reports_the_empty_section(self):
        report = check(self.profile())
        self.assertTrue(report["source_text_available"])
        self.assertEqual(report["missing_fields"], [])
        self.assertEqual(report["empty_sections"], ["Certifications"])
        self.assertEqual(report["unsupported_entries"], [])
        self.assertEqual(report["skills_not_in_resume"], [])
        self.assertEqual(report["years_check"], "")
        self.assertEqual(report["entries_checked"], 3)

    def test_invented_entries_skills_and_years_are_flagged(self):
        report = check(
            self.profile(
                work_history=["Senior Architect | Imaginary Corp | 2015 – 2019 | Led platform teams"],
                tech_skills=["Python", "Kubernetes"],
                years_of_experience=20,
                preferred_domains=[],
            )
        )
        self.assertEqual(report["missing_fields"], ["Target roles"])
        self.assertEqual(report["unsupported_entries"][0]["field"], "Work history")
        self.assertEqual(report["skills_not_in_resume"], ["Kubernetes"])
        self.assertIn("20 years recorded", report["years_check"])

    def test_older_profiles_without_resume_text_skip_text_checks(self):
        report = check(self.profile(source_text=""))
        self.assertFalse(report["source_text_available"])
        self.assertEqual((report["entries_checked"], report["skills_not_in_resume"]), (0, []))


if __name__ == "__main__":
    unittest.main()
