"""Web contract, lifecycle and OCR regression tests; no external API calls."""

from backend.profiles import upload as profiles_upload
from backend.search import service as search_service
from backend.search import retrieval
from backend.search import collection
from backend.schemas import resume as resume_schema
from backend import runs_api
from backend import runs
from backend.profiles import extraction
from backend.evaluation import service as evaluation_service
from backend.evaluation import orchestration
from backend import configuration


import io
import json
import shutil
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from langchain_core.documents import Document
from backend import app as api
from backend.profiles.extraction import extract_text_from_resume


class WebContractTests(unittest.TestCase):
    # Initialize per-test state; individual cases supply additional fixtures and patches.
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        profiles = patch(
            "backend.profiles.storage.PROFILES_DIR", Path(self.temp.name) / "profiles"
        )
        profiles.start()
        self.addCleanup(profiles.stop)
        for name, value in [
            ("RUNS_DIR", Path(self.temp.name)),
            ("RUNS", {}),
            ("RUN_CONTEXTS", {}),
            ("ACTIVE_WORKERS", set()),
            ("DELETING", set()),
        ]:
            patcher = patch.object(runs, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        runs.RATE_WINDOWS.clear()
        self.client = TestClient(api.app)
        validator = patch.object(
            profiles_upload,
            "classify_and_extract_resume",
            return_value=resume_schema.ResumeProfile(name="Example"),
        )
        self.validator = validator.start()
        self.addCleanup(validator.stop)
        self.worker = MagicMock()
        patcher = patch.object(runs, "threading", SimpleNamespace(Thread=self.worker))
        patcher.start()
        self.addCleanup(patcher.stop)

    def seed(self, status="awaiting_search"):
        path = runs.RUNS_DIR / "test"
        path.mkdir(exist_ok=True)
        runs.RUNS["test"] = {
            "id": "test",
            "status": status,
            "phase": 1,
            "created_at": time.time(),
            "profile": {"name": "Original", "tech_skills": ["Python"]},
        }
        runs.RUN_CONTEXTS["test"] = "Original profile"
        runs.persist_run("test")
        return path

    def test_search_router_delegates_to_backend_handler(self):
        self.seed()
        result = runs.snapshot("test")
        with patch.object(
            runs_api, "get_search", new=AsyncMock(return_value=result)
        ) as handler:
            response = self.client.get("/api/searches/test")
        self.assertEqual(response.status_code, 200)
        handler.assert_awaited_once_with(run_id="test")
        from backend.routers.searches import build_router

        route = next(
            route
            for route in build_router(search_service).routes
            if route.path == "/api/searches/{run_id}" and "GET" in route.methods
        )
        self.assertEqual(route.endpoint.__module__, "backend.routers.searches")

    def test_search_handlers_have_readable_operation_ids_and_legacy_urls(self):
        schema = api.app.openapi()
        expected = {
            ("/api/resumes/upload", "post"): "upload_resume",
            ("/api/searches/{run_id}", "get"): "get_search",
            ("/api/searches/{run_id}", "delete"): "delete_search",
            ("/api/searches/{run_id}/confirm-profile", "put"): "confirm_search_profile",
            ("/api/searches/{run_id}/progress", "get"): "stream_search_progress",
            (
                "/api/searches/{run_id}/retry-evaluations",
                "post",
            ): "retry_search_evaluations",
        }
        for (path, method), operation in expected.items():
            self.assertEqual(schema["paths"][path][method]["operationId"], operation)
        aliases = {
            "/api/runs": "/api/resumes/upload",
            "/api/searches": "/api/resumes/upload",
            "/api/runs/{run_id}": "/api/searches/{run_id}",
            "/api/runs/{run_id}/profile": "/api/searches/{run_id}/confirm-profile",
            "/api/runs/{run_id}/cancel": "/api/searches/{run_id}/cancel",
            "/api/runs/{run_id}/events": "/api/searches/{run_id}/progress",
            "/api/runs/{run_id}/retry-evaluation": "/api/searches/{run_id}/retry-evaluations",
        }
        from backend.routers import searches, uploads

        routes = {
            (route.path, method): route
            for router in (
                searches.build_router(search_service),
                uploads.build_router(profiles_upload),
            )
            for route in router.routes
            for method in getattr(route, "methods", [])
        }
        for legacy, canonical in aliases.items():
            self.assertNotIn(legacy, schema["paths"])
            self.assertTrue(any(path == legacy for path, method in routes))
            for method in ("GET", "POST", "PUT", "DELETE"):
                if (legacy, method) in routes:
                    self.assertIs(
                        routes[(legacy, method)].endpoint,
                        routes[(canonical, method)].endpoint,
                    )
        self.seed()
        # Check the expected behavior: search handlers have readable operation ids and legacy urls.
        self.assertEqual(
            self.client.get("/api/runs/test").json(),
            self.client.get("/api/searches/test").json(),
        )

    def test_all_model_retry_preserves_successful_assessments(self):
        from backend.evaluation import orchestration as multi_evaluation
        from backend.evaluation.runtime import EvaluationFailure

        path = self.seed("running")
        doc = Document(
            page_content="Python required",
            metadata={
                "title": "Developer",
                "company": "Example",
                "url": "https://example.test/job",
                "job_description": "Python required",
            },
        )

        def evaluate(context, jobs, **kw):
            if kw["provider"] == "gpt":
                kw["on_error"](jobs[0], EvaluationFailure("quota", "Quota unavailable"))
            else:
                kw["on_result"](
                    {
                        "apply_url": doc.metadata["url"],
                        "title": "Developer",
                        "company": "Example",
                        "score": 85,
                        "fit_category": "strong_match",
                        "is_strong_fit": True,
                    }
                )

        with patch.object(
            collection, "fetch_job_vacancies", return_value=[doc.metadata]
        ), patch.object(collection, "vectorize_jobs_to_db"), patch.object(
            retrieval, "retrieve_relevant_jobs", return_value=[doc]
        ), patch.object(
            multi_evaluation, "evaluate_provider", side_effect=evaluate
        ):
            search_service.execute_job_search(
                "test",
                None,
                {
                    "queries": ["Developer"],
                    "locations": [],
                    "platforms": ["linkedin"],
                    "remote": False,
                    "posted_days_old": 7,
                    "top_k": 0,
                    "persist_dir": str(path / "vectors"),
                },
            )
        snapshot = self.client.get("/api/searches/test").json()
        # Check the expected behavior: all model retry preserves successful assessments.
        self.assertEqual(len(snapshot["recommendations"]), 1)
        self.assertEqual(
            snapshot["recommendations"][0]["model_evaluations"]["gpt"]["status"],
            "failed",
        )
        failures = json.loads((path / "failed_jobs.json").read_text())
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["metadata"]["_evaluation_provider"], "gpt")

        def retry(context, jobs, **kw):
            self.assertEqual(kw["provider"], "gpt")
            kw["on_result"](
                {
                    "apply_url": doc.metadata["url"],
                    "title": "Developer",
                    "company": "Example",
                    "score": 85,
                    "fit_category": "strong_match",
                    "is_strong_fit": True,
                }
            )

        with patch.object(
            multi_evaluation, "evaluate_provider", side_effect=retry
        ) as provider:
            evaluation_service.retry_failed_evaluations("test")
        self.assertEqual(provider.call_count, 1)
        snapshot = self.client.get("/api/searches/test").json()
        self.assertEqual(len(snapshot["recommendations"]), 1)
        self.assertEqual(snapshot["recommendations"][0]["fit_category"], "strong_match")
        self.assertEqual(snapshot["recommendations"][0]["score"], 85)
        self.assertEqual(json.loads((path / "failed_jobs.json").read_text()), [])

    def test_search_api_names_and_legacy_urls_share_the_same_state(self):
        self.seed("complete")
        current = self.client.get("/api/searches/test")
        legacy = self.client.get("/api/runs/test")
        # Check the expected behavior: search api names and legacy urls share the same state.
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json(), legacy.json())
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/api/searches/{run_id}/confirm-profile", paths)
        self.assertIn("/api/searches/{run_id}/retry-evaluations", paths)
        self.assertNotIn("/api/runs", paths)
        models = self.client.get("/api/models/evaluation").json()
        self.assertTrue(any(item["label"].startswith("OpenAI GPT") for item in models))

    def test_location_suggestions_use_outbound_http_request(self):
        configuration.LOCATION_CACHE.clear()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "features": [
                    {
                        "properties": {
                            "name": "Sydney",
                            "state": "New South Wales",
                            "country": "Australia",
                        }
                    }
                ]
            }
        ).encode()
        with patch.object(configuration, "urlopen", return_value=response) as request:
            result = self.client.get("/api/locations/suggest", params={"q": "Sydney"})
        # Check the expected behavior: location suggestions use outbound http request.
        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            result.json()[0]["value"], "Sydney, New South Wales, Australia"
        )
        self.assertTrue(
            request.call_args.args[0].full_url.startswith(
                "https://photon.komoot.io/api/?"
            )
        )
        configuration.LOCATION_CACHE.clear()

    def test_upload_validates_signature_empty_and_size_before_worker(self):
        for data, expected in [
            (b"", 422),
            (b"not-pdf", 422),
            (b"%PDF-" + bytes(5 * 1024 * 1024), 413),
        ]:
            response = self.client.post(
                "/api/resumes/upload",
                files={"resume": ("resume.pdf", data, "application/pdf")},
            )
            self.assertEqual(response.status_code, expected)
        # Check the expected behavior: upload validates signature empty and size before worker.
        self.worker.assert_not_called()
        self.assertEqual(list(runs.RUNS_DIR.iterdir()), [])

    def test_upload_returns_run_url_id_and_validates_page_limit(self):
        image = Image.new("RGB", (200, 200), "white")
        data = io.BytesIO()
        image.save(data, format="PDF")
        with patch.object(
            extraction, "extract_text_from_resume", return_value="Synthetic resume"
        ), patch.object(
            extraction,
            "extract_context",
            return_value=resume_schema.ResumeProfile(name="Example"),
        ) as extract:
            response = self.client.post(
                "/api/resumes/upload",
                files={"resume": ("resume.pdf", data.getvalue(), "application/pdf")},
            )
        self.validator.assert_called_once_with("Synthetic resume")
        extract.assert_not_called()
        # Check the expected behavior: upload returns run url id and validates page limit.
        self.assertEqual(response.status_code, 201)
        run_id = response.json()["runId"]
        self.assertEqual(runs.RUNS[run_id]["status"], "awaiting_search")
        self.assertEqual(runs.RUNS[run_id]["profile"]["name"], "Example")
        self.assertNotIn(run_id, runs.ACTIVE_WORKERS)
        self.worker.assert_not_called()
        self.assertEqual(response.json()["runId"], response.json()["id"])
        long_pdf = io.BytesIO()
        image.save(long_pdf, format="PDF", save_all=True, append_images=[image] * 20)
        response = self.client.post(
            "/api/resumes/upload",
            files={"resume": ("long.pdf", long_pdf.getvalue(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 422)

    def test_upload_validates_in_memory_before_allocating_and_saving_run(self):
        image = Image.new("RGB", (200, 200), "white")
        data = io.BytesIO()
        image.save(data, format="PDF")
        pdf_bytes = data.getvalue()
        events = []

        def read_text(source):
            self.assertIsInstance(source, io.BytesIO)
            self.assertEqual(source.getvalue(), pdf_bytes)
            self.assertEqual(list(runs.RUNS_DIR.iterdir()), [])
            events.append("read")
            return "Synthetic resume"

        def validate(text):
            self.assertEqual(text, "Synthetic resume")
            self.assertEqual(list(runs.RUNS_DIR.iterdir()), [])
            self.assertFalse(runs.RUNS)
            events.append("validate")
            return resume_schema.ResumeProfile(name="Example")

        def allocate():
            self.assertEqual(events, ["read", "validate"])
            events.append("allocate")
            return SimpleNamespace(hex="accepted")

        self.validator.side_effect = validate
        with patch.object(
            extraction, "extract_text_from_resume", side_effect=read_text
        ), patch.object(
            profiles_upload.uuid, "uuid4", side_effect=allocate
        ), patch.object(
            extraction,
            "extract_context",
            return_value=resume_schema.ResumeProfile(name="Example"),
        ):
            response = self.client.post(
                "/api/resumes/upload",
                files={"resume": ("resume.pdf", pdf_bytes, "application/pdf")},
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(events, ["read", "validate", "allocate"])
        self.assertEqual(
            (runs.RUNS_DIR / "accepted" / "resume.pdf").read_bytes(), pdf_bytes
        )

    def test_upload_rejects_unreadable_text_before_creating_workspace(self):
        self._assert_upload_rejected(
            422, "Synthetic extraction failure", text_error=True
        )

    def test_non_resume_upload_returns_visible_error_without_profile_extraction(self):
        self._assert_upload_rejected(
            422, "This file does not appear to be a resume/CV."
        )

    def test_detection_failure_returns_service_error_without_workspace(self):
        self._assert_upload_rejected(
            503, "We could not verify whether this file is a resume/CV."
        )

    def _assert_upload_rejected(self, status, message, text_error=False):
        image = Image.new("RGB", (200, 200), "white")
        data = io.BytesIO()
        image.save(data, format="PDF")
        if not text_error:
            error = (
                profiles_upload.ResumeVerificationError if status == 503 else ValueError
            )
            self.validator.side_effect = error(message)
        with patch.object(
            extraction,
            "extract_text_from_resume",
            return_value="Synthetic document",
            side_effect=ValueError(message) if text_error else None,
        ), patch.object(extraction, "extract_context") as extract, patch.object(
            profiles_upload.uuid, "uuid4"
        ) as generate_id:
            response = self.client.post(
                "/api/resumes/upload",
                files={"resume": ("document.pdf", data.getvalue(), "application/pdf")},
            )
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.json()["detail"], message)
        generate_id.assert_not_called()
        extract.assert_not_called()
        self.assertFalse(runs.RUNS)
        self.assertFalse(runs.RUN_CONTEXTS)
        self.assertFalse(runs.ACTIVE_WORKERS)
        self.assertEqual(list(runs.RUNS_DIR.iterdir()), [])

    def test_profile_confirmation_rebuilds_context_and_passes_preferences(self):
        path = self.seed()
        payload = {
            "profile": {
                "name": "Edited",
                "years_of_experience": 3.5,
                "work_history": ["Engineer at Example"],
                "tech_skills": ["SQL"],
            },
            "preferences": {
                "queries": ["Analyst"],
                "locations": ["Sydney"],
                "work_type": "hybrid",
                "exclusions": ["Agency"],
                "evaluation_model": "gpt",
            },
        }
        response = self.client.put("/api/runs/test/profile", json=payload)
        # Check the expected behavior: profile confirmation rebuilds context and passes preferences.
        self.assertEqual(response.status_code, 202, response.text)
        self.assertIn("Edited", runs.RUN_CONTEXTS["test"])
        self.assertIn("Engineer at Example", (path / "resume_context.txt").read_text())
        options = self.worker.call_args.kwargs["args"][3]
        self.assertEqual(options["work_type"], "hybrid")
        self.assertEqual(options["exclusions"], ["Agency"])
        self.assertEqual(options["evaluation_model"], "gpt")
        self.assertEqual(
            self.client.put("/api/runs/test/profile", json=payload).status_code, 409
        )

    def test_empty_location_searches_worldwide(self):
        self.seed()
        response = self.client.put(
            "/api/runs/test/profile",
            json={
                "profile": {},
                "preferences": {"queries": ["Analyst"], "locations": []},
            },
        )
        # Check the expected behavior: empty location searches worldwide.
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(
            self.worker.call_args.kwargs["args"][3]["locations"], ["Worldwide"]
        )

    def test_empty_preferences_do_not_start_worker(self):
        self.seed()
        response = self.client.put(
            "/api/runs/test/profile",
            json={
                "profile": {},
                "preferences": {"queries": [" "], "locations": ["Sydney"]},
            },
        )
        # Check the expected behavior: empty preferences do not start worker.
        self.assertEqual(response.status_code, 422)
        self.worker.assert_not_called()

    def test_cancel_blocks_late_updates_and_delete_waits_for_worker(self):
        path = self.seed("running")
        runs.ACTIVE_WORKERS.add("test")
        response = self.client.post("/api/runs/test/cancel")
        # Check the expected behavior: cancel blocks late updates and delete waits for worker.
        self.assertEqual(response.json()["status"], "cancelled")
        with self.assertRaises(runs.RunStopped):
            runs.update_run("test", status="complete")
        response = self.client.delete("/api/runs/test")
        self.assertTrue(response.json()["deletion_pending"])
        self.assertEqual(self.client.get("/api/runs/test").status_code, 404)
        runs.run_worker("test", lambda run_id: None)
        self.assertFalse(path.exists())
        self.assertNotIn("test", runs.DELETING)

    def test_sse_contains_profile_phase_and_final_job_events(self):
        self.seed("complete")
        runs.RUNS["test"]["recommendations"] = [{"title": "Developer", "jobId": "one"}]
        response = self.client.get("/api/runs/test/events")
        # Check the expected behavior: sse contains profile phase and final job events.
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: phase_update", response.text)
        self.assertIn("event: job_evaluated", response.text)
        self.assertIn("event: run_completed", response.text)
        self.assertIn("text/event-stream", response.headers["content-type"])

    def test_expired_run_removed_and_rate_limit_is_explicit(self):
        path = self.seed()
        runs.RUNS["test"]["created_at"] = time.time() - runs.RETENTION_SECONDS - 1
        # Check the expected behavior: expired run removed and rate limit is explicit.
        self.assertEqual(self.client.get("/api/runs/test").status_code, 404)
        self.assertFalse(path.exists())
        for _ in range(30):
            self.client.post("/api/runs/missing/cancel")
        response = self.client.post("/api/runs/missing/cancel")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")

    def test_incremental_results_are_visible_before_evaluation_finishes(self):
        path = self.seed("running")
        job = Document(
            page_content="Junior Python developer",
            metadata={
                "title": "Developer",
                "company": "Example",
                "url": "https://example.com/job",
            },
        )
        result = {
            "title": "Developer",
            "company": "Example",
            "apply_url": "https://example.com/job",
            "fit_category": "review",
            "is_strong_fit": False,
        }

        def evaluate(*args, **kwargs):
            kwargs["on_result"](result)
            self.assertEqual(
                runs.snapshot("test")["recommendations"][0]["title"], "Developer"
            )
            self.assertEqual(runs.RUNS["test"]["status"], "running")
            kwargs["on_progress"](1, 0, 1)
            return [result]

        with patch.object(
            collection, "fetch_job_vacancies", return_value=[job.metadata]
        ), patch.object(collection, "vectorize_jobs_to_db"), patch.object(
            retrieval, "retrieve_relevant_jobs", return_value=[job]
        ), patch.object(
            orchestration, "evaluate_jobs", side_effect=evaluate
        ):
            search_service.execute_job_search(
                "test",
                None,
                {
                    "queries": ["Developer"],
                    "locations": ["Sydney"],
                    "platforms": ["linkedin"],
                    "remote": False,
                    "posted_days_old": 7,
                    "top_k": 0,
                    "persist_dir": str(path / "vectors"),
                },
            )
        # Check the expected behavior: incremental results are visible before evaluation finishes.
        self.assertEqual(runs.RUNS["test"]["status"], "complete")
        self.assertTrue((path / "job_assessments.jsonl").exists())

    def test_retry_only_evaluates_failed_documents(self):
        path = self.seed("complete")
        runs.RUNS["test"].update(
            recommendations=[
                {"title": "Prior success", "apply_url": "https://example.com/old"}
            ],
            evaluated_jobs=1,
            evaluation_model="gpt",
        )
        (path / "failed_jobs.json").write_text(
            json.dumps(
                [
                    {
                        "page_content": "failed posting",
                        "metadata": {
                            "title": "Retry me",
                            "url": "https://example.com/new",
                        },
                    }
                ]
            )
        )

        def evaluate(context, docs, **kwargs):
            self.assertEqual(len(docs), 1)
            kwargs["on_result"](
                {
                    "title": "Retry me",
                    "apply_url": "https://example.com/new",
                    "fit_category": "review",
                }
            )

        with patch.object(orchestration, "evaluate_jobs", side_effect=evaluate):
            evaluation_service.retry_failed_evaluations("test")
        # Check the expected behavior: retry only evaluates failed documents.
        self.assertEqual(len(runs.RUNS["test"]["recommendations"]), 2)
        self.assertEqual(json.loads((path / "failed_jobs.json").read_text()), [])

    def test_delete_tombstone_survives_a_server_restart(self):
        path = self.seed("running")
        runs.ACTIVE_WORKERS.add("test")
        self.client.delete("/api/runs/test")
        # Check the expected behavior: delete tombstone survives a server restart.
        self.assertTrue((path / ".delete-requested").exists())
        runs.load_persisted_runs()
        self.assertNotIn("test", runs.RUNS)
        self.assertFalse(path.exists())

    def test_profile_extraction_only_accepts_openai(self):
        options = self.client.get("/api/models/resume").json()
        self.assertEqual([option["value"] for option in options], ["openai"])
        for provider in ("gemini", "anthropic", "mistral"):
            with self.subTest(provider=provider):
                response = self.client.post(
                    "/api/resumes/upload",
                    data={"model": provider},
                    files={
                        "resume": ("resume.pdf", b"%PDF-synthetic", "application/pdf")
                    },
                )
                self.assertEqual(response.status_code, 422)
                self.assertIn("only supports OpenAI", response.json()["detail"])

    def test_profile_model_labels_match_backend_overrides(self):
        with patch.dict("os.environ", {"OPENAI_PROFILE_MODEL": "custom-profile-model"}):
            response = self.client.get("/api/profile-models")
        # Check the expected behavior: profile model labels match backend overrides.
        self.assertIn(
            {
                "value": "openai",
                "label": "OpenAI GPT · custom-profile-model",
                "model_id": "custom-profile-model",
            },
            response.json(),
        )

    def test_partial_scrape_failure_keeps_other_sources_results(self):
        path = self.seed("running")
        job = Document(
            page_content="Junior developer",
            metadata={"title": "Developer", "url": "https://example.com"},
        )

        def fetch(*args, **kwargs):
            kwargs["on_error"]("One source timed out")
            return [job.metadata]

        with patch.object(
            collection, "fetch_job_vacancies", side_effect=fetch
        ), patch.object(collection, "vectorize_jobs_to_db"), patch.object(
            retrieval, "retrieve_relevant_jobs", return_value=[job]
        ), patch.object(
            orchestration,
            "evaluate_jobs",
            return_value=[
                {"title": "Developer", "is_strong_fit": False, "fit_category": "review"}
            ],
        ):
            search_service.execute_job_search(
                "test",
                None,
                {
                    "queries": ["Developer"],
                    "locations": ["Sydney"],
                    "platforms": ["linkedin"],
                    "remote": False,
                    "posted_days_old": 7,
                    "top_k": 0,
                    "persist_dir": str(path / "vectors"),
                },
            )
        # Check the expected behavior: partial scrape failure keeps other sources results.
        self.assertEqual(runs.RUNS["test"]["status"], "complete")
        self.assertEqual(len(runs.RUNS["test"]["recommendations"]), 1)
        self.assertEqual(runs.RUNS["test"]["scrape_errors"], ["One source timed out"])

    @unittest.skipUnless(
        shutil.which("tesseract"), "Tesseract is an optional system dependency"
    )
    def test_real_ocr_reads_image_only_resume(self):
        image = Image.new("RGB", (1600, 1000), "white")
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 50)
        except OSError:
            font = ImageFont.truetype("DejaVuSans.ttf", 50)
        draw.text(
            (100, 100),
            "Alex Example\nPython Developer\nThree years of experience",
            fill="black",
            font=font,
            spacing=20,
        )
        path = runs.RUNS_DIR / "scan.pdf"
        image.save(path, "PDF")
        text = extract_text_from_resume(io.BytesIO(path.read_bytes()))
        # Check the expected behavior: real ocr reads image only resume.
        self.assertIn("Python", text)
        self.assertIn("Developer", text)


if __name__ == "__main__":
    unittest.main()
