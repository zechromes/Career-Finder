"""All providers share a contract; checks run without any model API calls."""

from backend import runs


from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from backend import app as api
from backend.schemas.evaluation import JobEvaluation, RequirementSet
from backend.evaluation.providers import (
    create_evaluation_llm,
    evaluate_jobs,
    evaluate_jobs_with_claude,
)


class EvaluationModelTests(unittest.TestCase):
    # Initialize per-test state; individual cases supply additional fixtures and patches.
    def setUp(self):
        patcher = patch.object(runs, "ACTIVE_WORKERS", set())
        patcher.start()
        self.addCleanup(patcher.stop)
        runs.RATE_WINDOWS.clear()

    def test_default_model_tiers_and_api_labels(self):
        from backend.evaluation.providers import evaluation_model_options

        with patch.dict(
            "os.environ",
            {
                "GPT_EVALUATION_MODEL": "",
                "GEMINI_EVALUATION_MODEL": "",
                "CLAUDE_EVALUATION_MODEL": "",
            },
        ):
            options = {
                row["value"]: row["model_id"] for row in evaluation_model_options()
            }
            self.assertEqual(
                options,
                {
                    "gpt": "gpt-6.1-sol",
                    "gemini": "gemini-4-argon",
                    "claude": "claude-sonnet-5-5",
                },
            )
            with (
                patch("langchain_openai.ChatOpenAI") as gpt,
                patch("langchain_google_genai.ChatGoogleGenerativeAI") as gemini,
            ):
                create_evaluation_llm("gpt")
                create_evaluation_llm("gemini")
                self.assertEqual(gpt.call_args.kwargs["model"], options["gpt"])
                self.assertEqual(gemini.call_args.kwargs["model"], options["gemini"])
                self.assertEqual(gpt.call_args.kwargs["reasoning_effort"], "low")
                self.assertEqual(gemini.call_args.kwargs["thinking_level"], "low")

    def test_low_reasoning_reaches_sdk_request_configuration(self):
        from langchain_openai import ChatOpenAI
        from langchain_google_genai import ChatGoogleGenerativeAI
        from backend.evaluation.providers import evaluation_reasoning_options

        with patch.dict(
            "os.environ",
            {"GPT_EVALUATION_MODEL": "", "GEMINI_EVALUATION_MODEL": ""},
        ):
            gpt = ChatOpenAI(
                model="gpt-6.1-sol",
                api_key="synthetic-test-key",
                **evaluation_reasoning_options("gpt"),
            )
            self.assertEqual(gpt._default_params["reasoning_effort"], "low")
            gemini = ChatGoogleGenerativeAI(
                model="gemini-4-argon",
                api_key="synthetic-test-key",
                vertexai=False,
                **evaluation_reasoning_options("gemini"),
            )
            self.assertEqual(
                gemini._prepare_params(stop=None).thinking_config.thinking_level.value,
                "LOW",
            )

    def test_legacy_model_overrides_do_not_receive_reasoning_options(self):
        from backend.evaluation.providers import evaluation_reasoning_options

        with patch.dict(
            "os.environ",
            {
                "GPT_EVALUATION_MODEL": "gpt-4o-mini",
                "GEMINI_EVALUATION_MODEL": "gemini-2.0-flash",
            },
        ):
            for provider in ("gpt", "gemini", "claude"):
                self.assertEqual(evaluation_reasoning_options(provider), {})

    def test_provider_clients_keep_timeouts_and_individual_retries(self):
        with patch("langchain_google_genai.ChatGoogleGenerativeAI") as gemini:
            create_evaluation_llm("gemini")
            self.assertEqual(gemini.call_args.kwargs["timeout"], 90.0)
            self.assertEqual(gemini.call_args.kwargs["max_retries"], 0)
            self.assertNotIn("temperature", gemini.call_args.kwargs)
        with patch("langchain_anthropic.ChatAnthropic") as claude:
            create_evaluation_llm("claude")
            self.assertEqual(claude.call_args.kwargs["default_request_timeout"], 90.0)
            self.assertEqual(claude.call_args.kwargs["max_retries"], 1)
            self.assertEqual(claude.call_args.kwargs["max_tokens"], 8192)
            self.assertNotIn("temperature", claude.call_args.kwargs)

    def test_gpt_client_and_configured_model_options(self):
        with patch.dict("os.environ", {"GPT_EVALUATION_MODEL": "gpt-custom"}):
            with patch("langchain_openai.ChatOpenAI") as gpt:
                create_evaluation_llm("gpt")
                self.assertEqual(gpt.call_args.kwargs["model"], "gpt-custom")
                self.assertEqual(gpt.call_args.kwargs["timeout"], 180.0)
                self.assertEqual(gpt.call_args.kwargs["max_retries"], 1)
            response = TestClient(api.app).get("/api/evaluation-models")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                {item["value"] for item in response.json()}, {"gemini", "claude", "gpt"}
            )
            self.assertIn(
                {
                    "value": "gpt",
                    "label": "OpenAI GPT · gpt-custom",
                    "model_id": "gpt-custom",
                },
                response.json(),
            )

    def test_gpt_timeout_override_is_bounded_and_invalid_values_use_default(self):
        for configured, expected in [
            ("240", 240.0),
            ("0", 30.0),
            ("9999", 600.0),
            ("invalid", 180.0),
        ]:
            with (
                self.subTest(configured=configured),
                patch.dict(
                    "os.environ", {"GPT_EVALUATION_TIMEOUT_SECONDS": configured}
                ),
                patch("langchain_openai.ChatOpenAI") as client,
            ):
                create_evaluation_llm("gpt")
                self.assertEqual(client.call_args.kwargs["timeout"], expected)
                self.assertEqual(client.call_args.kwargs["max_retries"], 1)

    def test_missing_assessment_details_have_safe_defaults(self):
        result = JobEvaluation(
            match_rationale="Review", missing_skills=[], apply_url="https://example.com"
        )
        # Check the expected behavior: missing assessment details have safe defaults.
        self.assertEqual(result.about_company, "")
        self.assertEqual(result.candidate_requirements, [])
        self.assertIsNone(result.salary)

    def test_both_providers_return_same_fields_and_preserve_exclusion(self):
        evaluation = JobEvaluation(
            fit_category="not_suitable",
            is_strong_fit=True,
            mismatch_reason="Experience gap",
            match_rationale="Requires more experience.",
            missing_skills=["SQL"],
            apply_url="https://incorrect.example",
            about_company="Builds software.",
            candidate_requirements=["SQL required"],
            salary="AUD 100,000–120,000 per year",
            requirement_verdicts=[
                dict(
                    requirement_id="req_001",
                    requirement="8 years experience",
                    importance="must_have",
                    verdict="not_met",
                    job_quote="Requires 8 years.",
                    resume_quote="2 years experience",
                    explanation="Experience gap",
                )
            ],
        )
        client = SimpleNamespace(
            model="test-model",
            with_structured_output=MagicMock(
                return_value=RunnableLambda(lambda prompt: evaluation.model_dump())
            ),
        )
        document = Document(
            page_content="Requires 8 years.",
            metadata={
                "title": "Engineer",
                "company": "Example",
                "url": "https://example.com/job",
                "location": "Sydney",
                "source": "linkedin",
                "posted_at": "2026-09-15",
            },
        )
        for provider in ["gemini", "claude", "gpt"]:
            with (
                self.subTest(provider=provider),
                patch(
                    "backend.evaluation.providers.create_evaluation_llm",
                    return_value=client,
                ) as factory,
            ):
                saved = []
                results = evaluate_jobs(
                    "2 years experience",
                    [document],
                    include_all=True,
                    provider=provider,
                    on_result=saved.append,
                    requirement_loader=lambda job: RequirementSet(
                        posting_hash="synthetic",
                        extraction_model="synthetic",
                        extraction_version="test",
                        requirements=[
                            {
                                key: value
                                for key, value in evaluation.requirement_verdicts[0]
                                .model_dump()
                                .items()
                                if key
                                in {
                                    "requirement_id",
                                    "requirement",
                                    "importance",
                                    "job_quote",
                                    "section",
                                    "type",
                                }
                            }
                        ],
                    ),
                )
                factory.assert_called_once_with(provider)
                if provider == "gpt":
                    self.assertIsInstance(
                        client.with_structured_output.call_args.args[0], dict
                    )
                    self.assertEqual(
                        client.with_structured_output.call_args.kwargs["method"],
                        "json_schema",
                    )
                self.assertEqual(results[0]["evaluation_provider"], provider)
                self.assertEqual(results[0]["fit_category"], "not_suitable")
                self.assertFalse(results[0]["is_strong_fit"])
                self.assertEqual(results[0]["apply_url"], "https://example.com/job")
                self.assertEqual(
                    results[0]["mismatch_reason"],
                    "A mandatory requirement has an evidenced mismatch.",
                )
                self.assertEqual(results[0]["about_company"], "Builds software.")
                self.assertEqual(
                    results[0]["candidate_requirements"], ["8 years experience"]
                )
                self.assertEqual(results[0]["salary"], "AUD 100,000–120,000 per year")
                self.assertEqual(saved, results)

    def test_legacy_entry_point_still_selects_claude(self):
        with patch(
            "backend.evaluation.providers.evaluate_jobs", return_value=[]
        ) as evaluate:
            evaluate_jobs_with_claude("resume", [])
            self.assertEqual(evaluate.call_args.kwargs["provider"], "claude")

    def test_search_rejects_unknown_provider_before_starting_work(self):
        response = TestClient(api.app).post(
            "/api/runs/test/search",
            data={
                "queries": '["Engineer"]',
                "locations": '["Australia"]',
                "evaluation_model": "unknown",
            },
        )
        # Check the expected behavior: search rejects unknown provider before starting work.
        self.assertEqual(response.status_code, 422)

    def test_failed_search_can_retry_and_clears_previous_error(self):
        with (
            patch.object(
                runs,
                "RUNS",
                {
                    "test": {
                        "status": "error",
                        "phase": 3,
                        "profile": {"years_of_experience": 0},
                        "error": "Quota exhausted",
                    }
                },
            ),
            patch.object(runs, "RUN_CONTEXTS", {"test": "Graduate profile"}),
            patch.object(runs, "update_run") as update,
            patch.object(
                runs, "threading", SimpleNamespace(Thread=MagicMock())
            ) as threads,
        ):
            response = TestClient(api.app).post(
                "/api/runs/test/search",
                data={"queries": '["Engineer"]', "locations": '["Australia"]'},
            )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(update.call_args.kwargs["status"], "running")
            self.assertIsNone(update.call_args.kwargs["error"])
            threads.Thread.return_value.start.assert_called_once()

    def test_retry_rejects_busy_runs_or_failed_extraction(self):
        for run, context in [
            ({"status": "running", "profile": {"years_of_experience": 0}}, "Resume"),
            ({"status": "error"}, "Resume"),
            ({"status": "error", "profile": {"years_of_experience": 0}}, ""),
        ]:
            with (
                self.subTest(run=run, context=context),
                patch.object(runs, "RUNS", {"test": run}),
                patch.object(runs, "RUN_CONTEXTS", {"test": context}),
                patch.object(
                    runs, "threading", SimpleNamespace(Thread=MagicMock())
                ) as threads,
            ):
                response = TestClient(api.app).post(
                    "/api/runs/test/search",
                    data={"queries": '["Engineer"]', "locations": '["Australia"]'},
                )
                self.assertEqual(response.status_code, 409)
                threads.Thread.assert_not_called()

    def test_search_passes_selected_provider_to_worker_and_saved_settings(self):
        for provider in ["gemini", "claude", "gpt"]:
            with (
                self.subTest(provider=provider),
                patch.object(runs, "ACTIVE_WORKERS", set()),
                patch.object(runs, "RUNS", {"test": {"status": "awaiting_search"}}),
                patch.object(runs, "update_run") as update,
                patch.object(
                    runs, "threading", SimpleNamespace(Thread=MagicMock())
                ) as threads,
            ):
                response = TestClient(api.app).post(
                    "/api/runs/test/search",
                    data={
                        "queries": '["Engineer"]',
                        "locations": '["Australia"]',
                        "evaluation_model": provider,
                    },
                )
                self.assertEqual(response.status_code, 202)
                self.assertEqual(
                    update.call_args.kwargs["search_inputs"]["evaluation_model"],
                    provider,
                )
                self.assertEqual(
                    threads.Thread.call_args.kwargs["args"][3]["evaluation_model"],
                    provider,
                )


if __name__ == "__main__":
    unittest.main()
