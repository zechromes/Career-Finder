# The playground runs one stage on its own and never creates a run or writes files.
import io
from collections import defaultdict, deque
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend import app as web, runs
from backend.profiles import extraction, upload
from backend.schemas.resume import ResumeProfile
from backend.search import collection, ingestion_log


def pdf():
    data = io.BytesIO()
    Image.new("RGB", (200, 200), "white").save(data, format="PDF")
    return data.getvalue()


class PlaygroundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Retrieval requests default to the hyde builder; never write ads with a live model call.
        no_ads = patch("backend.search.hyde.job_ads", return_value=[])
        no_ads.start()
        self.addCleanup(no_ads.stop)
        # A fresh rate-limit window keeps these requests from counting against other tests.
        for name, value in (
            ("RUNS_DIR", Path(self.temp.name)),
            ("RUNS", {}),
            ("RATE_WINDOWS", defaultdict(deque)),
        ):
            patcher = patch.object(runs, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(web.app)

    def test_upload_returns_profile_and_check_without_a_run(self):
        profile = ResumeProfile(
            name="Candidate",
            tech_skills=["Python", "Kubernetes"],
            source_text="Candidate. Skills: Python",
        )
        with patch.object(
            extraction, "extract_text_from_resume", return_value="Candidate. Skills: Python"
        ), patch.object(upload, "classify_and_extract_resume", return_value=profile):
            response = self.client.post(
                "/api/playground/upload",
                files={"resume": ("resume.pdf", pdf(), "application/pdf")},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["profile"]["name"], "Candidate")
        self.assertEqual(response.json()["check"]["skills_not_in_resume"], ["Kubernetes"])
        self.assertEqual((runs.RUNS, list(runs.RUNS_DIR.iterdir())), ({}, []))

    def test_upload_reports_a_non_resume(self):
        with patch.object(extraction, "extract_text_from_resume", return_value="Invoice"), patch.object(
            upload, "classify_and_extract_resume", side_effect=ValueError("Not a resume.")
        ):
            response = self.client.post(
                "/api/playground/upload",
                files={"resume": ("resume.pdf", pdf(), "application/pdf")},
            )
        self.assertEqual((response.status_code, response.json()["detail"]), (422, "Not a resume."))

    def test_ingestion_reports_kept_and_dropped_jobs_live(self):
        def collect(*args, **kwargs):
            self.assertTrue(kwargs["force_refresh"])
            ingestion_log.collected("linkedin", 2)
            stale = dict(title="Old role", company="A", source_platform="linkedin")
            ingestion_log.drop(stale, "filter", "posted too long ago")
            kwargs["on_status"]("Adaptive collection finished: 1 eligible postings")
            kwargs["on_error"]("LinkedIn rate-limited the request (HTTP 429).")
            return [dict(title="Analyst", company="B", source_platform="linkedin", description="Text")]

        with patch.object(collection, "fetch_job_vacancies", side_effect=collect):
            response = self.client.post(
                "/api/playground/ingestion",
                json={"queries": ["Analyst"], "locations": ["Sydney"], "platforms": ["linkedin"]},
            )
        body = response.json()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(body["collected"], {"linkedin": 2})
        self.assertEqual(body["jobs"][0]["description_chars"], 4)
        self.assertEqual(body["dropped"][0]["reason"], "posted too long ago")
        self.assertIn("1 eligible", body["status"])
        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(list(runs.RUNS_DIR.iterdir()), [])

    def test_no_location_searches_worldwide_like_a_real_search(self):
        with patch.object(collection, "fetch_job_vacancies", return_value=[]) as collect:
            response = self.client.post(
                "/api/playground/ingestion", json={"queries": ["Analyst"], "platforms": ["linkedin"]}
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(collect.call_args.args[1], ["Worldwide"])

    def job(self, number, description="Build data pipelines in Python."):
        return dict(
            title=f"Data Engineer {number}",
            company="Example Co",
            location="Sydney",
            board="seek",
            posted_at="",
            url=f"https://example.test/{number}",
            description_chars=len(description),
            description=description,
        )

    def test_retrieval_ranks_jobs_like_a_real_search_without_a_run(self):
        from langchain_core.documents import Document
        from backend.search import retrieval

        profile = ResumeProfile(name="Candidate", tech_skills=["Python"])
        ranked = [
            Document(
                page_content="Full posting",
                metadata=dict(title="Data Engineer 2", company="Example Co",
                              location="Sydney", source="seek", url="https://example.test/2"),
            )
        ]
        # The default builder is hyde; no ads means the role titles stay, with no model call.
        with patch.object(collection, "vectorize_jobs_to_db") as index, patch.object(
            retrieval, "retrieve_relevant_jobs", return_value=ranked
        ) as retrieve, patch("backend.search.hyde.job_ads", return_value=[]) as ads:
            response = self.client.post(
                "/api/playground/retrieval",
                json=dict(
                    profile=profile.model_dump(),
                    queries=["Data Engineer"],
                    jobs=[self.job(1, description=" "), self.job(2)],
                ),
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        # Jobs without a description are left out, as in a real search.
        self.assertEqual([job["url"] for job in index.call_args.args[0]], ["https://example.test/2"])
        self.assertEqual(index.call_args.args[0][0]["source_platform"], "seek")
        self.assertEqual(retrieve.call_args.kwargs["top_k"], -1)
        ads.assert_called()
        self.assertIn("Data Engineer", [query["text"] for query in body["queries"]])
        self.assertEqual(
            (body["total_jobs"], body["ranked"][0]["rank"], body["ranked"][0]["url"]),
            (1, 1, "https://example.test/2"),
        )
        self.assertEqual((runs.RUNS, list(runs.RUNS_DIR.iterdir())), ({}, []))

    def test_retrieval_uses_the_query_builder_chosen_in_the_request(self):
        from backend.search import retrieval

        entry = "Built Python APIs 2025-Present"
        profile = ResumeProfile(name="Candidate", tech_skills=["Python"], work_history=[entry])
        texts = {}
        for builder in ("evidence", "skills", "hyde"):
            with patch.object(collection, "vectorize_jobs_to_db"), patch.object(
                retrieval, "retrieve_relevant_jobs", return_value=[]
            ), patch("backend.search.hyde.job_ads", return_value=["Python API Developer ad"]):
                response = self.client.post(
                    "/api/playground/retrieval",
                    json=dict(
                        profile=profile.model_dump(),
                        queries=["Data Engineer"],
                        jobs=[self.job(1)],
                        query_builder=builder,
                    ),
                )
            self.assertEqual(response.status_code, 200, response.text)
            texts[builder] = [query["text"] for query in response.json()["queries"]]
        # No environment setting needed: the request picks the builder.
        self.assertIn(entry, texts["evidence"])
        self.assertNotIn(entry, texts["skills"])
        self.assertIn("Python", texts["skills"])
        self.assertIn("Job ad: Python API Developer ad", texts["hyde"])
        self.assertNotIn("Data Engineer", texts["hyde"])

    def test_retrieval_needs_a_job_with_a_description(self):
        response = self.client.post(
            "/api/playground/retrieval",
            json=dict(
                profile=ResumeProfile(name="Candidate").model_dump(),
                queries=["Data Engineer"],
                jobs=[self.job(1, description="")],
            ),
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
