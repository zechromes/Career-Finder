"""Shared criteria invariants with synthetic postings and no provider traffic."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch, Mock
from langchain_core.documents import Document
from backend.evaluation.requirements import (
    RequirementLoader,
    validate_requirements,
    align_assessment,
    extract_requirements,
    resolve_source_references,
)
from backend.evaluation.runtime import EvaluationFailure
from backend.evaluation.evidence import score_requirements
from backend.schemas.evaluation import JobEvaluation, RequirementVerdict

POSTING = "Qualifications\nPython or Java required.\nNice to have\nSQL preferred."


def criteria():
    return validate_requirements(
        {
            "requirements": [
                dict(
                    requirement="Python or Java",
                    importance="must_have",
                    job_quote="Python or Java required.",
                    section="Qualifications",
                    type="skill",
                ),
                dict(
                    requirement="SQL",
                    importance="nice_to_have",
                    job_quote="SQL preferred.",
                    section="Nice to have",
                    type="skill",
                ),
            ]
        },
        POSTING,
    )


def referenced_rows():
    return [
        dict(
            row.model_dump(exclude={"requirement_id", "job_quote"}),
            source_start=line,
            source_end=line,
        )
        for row, line in zip(criteria().requirements, (2, 4))
    ]


def assessment(shared):
    return JobEvaluation(
        match_rationale="Synthetic",
        missing_skills=[],
        apply_url="https://example.test",
        requirement_verdicts=[
            dict(
                row.model_dump(),
                verdict="met",
                resume_quote="Python and SQL",
                explanation="Supported",
            )
            for row in shared.requirements
        ],
    )


class SharedRequirementsTests(unittest.TestCase):
    def test_stable_ids_and_alternative_remains_one_criterion(self):
        rows = criteria().requirements
        self.assertEqual([r.requirement_id for r in rows], ["req_001", "req_002"])
        self.assertEqual(rows[0].requirement, "Python or Java")

    def test_invalid_quotes_sections_and_duplicates_are_rejected(self):
        rows = [
            r.model_dump(exclude={"requirement_id"}) for r in criteria().requirements
        ]
        for field, value in [
            ("job_quote", "Invented"),
            ("section", "Invented"),
            ("requirement", ""),
        ]:
            with self.subTest(field=field), self.assertRaises(EvaluationFailure):
                validate_requirements(
                    {"requirements": [{**rows[0], field: value}]}, POSTING
                )
        with self.assertRaises(EvaluationFailure):
            validate_requirements({"requirements": [rows[0], rows[0]]}, POSTING)

    def test_source_references_copy_exact_formatting_and_multiline_evidence(self):
        posting = "Qualifications\r\n- **Python** or Java — required.\r\n  No degree required.\r\n"
        row = {**referenced_rows()[0], "source_start": 2, "source_end": 3}
        result = resolve_source_references({"requirements": [row]}, posting)
        self.assertEqual(
            result.requirements[0].job_quote,
            "- **Python** or Java — required.\r\n  No degree required.",
        )
        self.assertIn(result.requirements[0].job_quote, posting)
        self.assertEqual(result.requirements[0].requirement, row["requirement"])

    def test_invalid_source_ranges_cannot_create_evidence(self):
        for start, end in [(0, 1), (2, 1), (1, 999), (True, 2), (1.5, 2), ("1", 2)]:
            with self.subTest(start=start, end=end), self.assertRaises(
                EvaluationFailure
            ):
                resolve_source_references(
                    {
                        "requirements": [
                            {
                                **referenced_rows()[0],
                                "source_start": start,
                                "source_end": end,
                            }
                        ]
                    },
                    POSTING,
                )
        with self.assertRaises(EvaluationFailure):
            resolve_source_references(
                {
                    "requirements": [
                        {**referenced_rows()[0], "source_start": 1, "source_end": 1}
                    ]
                },
                "   \nPython required.",
            )

    def test_single_line_posting_preserves_alternatives_and_negation(self):
        posting = "Python OR Java required; a degree is not required."
        row = {**referenced_rows()[0], "source_start": 1, "source_end": 1}
        result = resolve_source_references({"requirements": [row]}, posting)
        self.assertEqual(result.requirements[0].job_quote, posting)
        self.assertEqual(result.requirements[0].section, "")

    def test_all_ids_required_once_and_canonical_fields_cannot_change(self):
        shared = criteria()
        for variant in [
            "missing",
            "duplicate",
            "extra",
            "importance",
            "job_quote",
            "section",
            "type",
            "requirement",
        ]:
            value = assessment(shared)
            if variant == "missing":
                value.requirement_verdicts.pop()
            elif variant == "duplicate":
                value.requirement_verdicts.append(value.requirement_verdicts[0])
            elif variant == "extra":
                value.requirement_verdicts[0].requirement_id = "invented"
            else:
                setattr(value.requirement_verdicts[0], variant, "changed")
            with self.subTest(variant=variant), self.assertRaises(EvaluationFailure):
                align_assessment(value, shared)
        value = assessment(shared)
        value.requirement_verdicts.reverse()
        self.assertEqual(
            align_assessment(value, shared).requirement_verdicts[0].requirement_id,
            "req_001",
        )

    def test_concurrent_providers_share_extraction_and_retry_checkpoint(self):
        docs = [Document(page_content=POSTING) for _ in range(3)]
        loader = RequirementLoader()
        with patch(
            "backend.evaluation.requirements.extract_requirements",
            return_value=criteria(),
        ) as extract:
            with ThreadPoolExecutor(3) as pool:
                values = list(pool.map(loader, docs))
            self.assertEqual(extract.call_count, 1)
            self.assertEqual(values[0], values[2])
            self.assertIn("_requirement_set", docs[0].metadata)
            self.assertEqual(RequirementLoader()(docs[0]), values[0])
            self.assertEqual(extract.call_count, 1)

    def test_failures_shared_and_changed_postings_reject_checkpoint(self):
        loader = RequirementLoader()
        with patch(
            "backend.evaluation.requirements.extract_requirements",
            side_effect=EvaluationFailure(
                "quota", "Requirement extraction quota exhausted"
            ),
        ) as extract:
            for _ in range(3):
                with self.assertRaises(EvaluationFailure):
                    loader(Document(page_content=POSTING))
            self.assertEqual(extract.call_count, 1)
        doc = Document(
            page_content="Different",
            metadata={"_requirement_set": criteria().model_dump()},
        )
        with self.assertRaises(EvaluationFailure):
            RequirementLoader()(doc)

    def test_shared_cache_reuses_without_candidate_and_invalidates_content(self):
        from langchain_core.runnables import RunnableLambda

        result = {"requirements": referenced_rows()}
        invoke = Mock(return_value=result)
        client = Mock()
        client.with_structured_output.return_value = RunnableLambda(invoke)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.evaluation.requirements.JOB_REQUIREMENT_CACHE_DIR",
            Path(tmp) / "requirements",
        ), patch("langchain_openai.ChatOpenAI", return_value=client):
            self.assertEqual(
                extract_requirements(POSTING), extract_requirements(POSTING)
            )
            self.assertEqual(invoke.call_count, 1)
            extract_requirements(POSTING + "\nExtra context")
            self.assertEqual(invoke.call_count, 2)
            prompt = str(invoke.call_args.args[0])
            self.assertNotIn("candidate_evidence", prompt)
            source_message = invoke.call_args.args[0].to_messages()[1].content
            lines = json.loads(
                source_message.removeprefix("<job_posting>\n").removesuffix(
                    "\n</job_posting>"
                )
            )
            self.assertEqual(
                "".join(line["text"] for line in lines), POSTING + "\nExtra context"
            )
            self.assertEqual([line["line_id"] for line in lines], [1, 2, 3, 4, 5])
            self.assertTrue(client.with_structured_output.call_args.kwargs["strict"])
            schema = client.with_structured_output.call_args.args[0]
            self.assertNotIn("job_quote", json.dumps(schema))

    def test_invalid_extraction_retry_receives_specific_correction(self):
        from langchain_core.runnables import RunnableLambda

        valid = {"requirements": referenced_rows()}
        for field, value in [
            ("source_end", 999),
            ("requirement", ""),
        ]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                invalid = {"requirements": [{**valid["requirements"][0], field: value}]}
                invoke = Mock(side_effect=[invalid, valid])
                client = Mock()
                client.with_structured_output.return_value = RunnableLambda(invoke)
                with patch(
                    "backend.evaluation.requirements.JOB_REQUIREMENT_CACHE_DIR",
                    Path(tmp) / "requirements",
                ), patch("langchain_openai.ChatOpenAI", return_value=client):
                    result = extract_requirements(POSTING)
                    self.assertEqual(len(result.requirements), 2)
                    feedback = invoke.call_args.args[0].to_messages()[-1].content
                    self.assertIn("criterion 1", feedback)
                    self.assertIn(field, feedback)
                    if isinstance(value, str) and value:
                        self.assertNotIn(value, feedback)
                    self.assertEqual(extract_requirements(POSTING), result)
                    self.assertEqual(invoke.call_count, 2)

    def test_fresh_extraction_clears_unverified_optional_section(self):
        from langchain_core.runnables import RunnableLambda

        rows = referenced_rows()
        rows[0]["section"] = "Invented heading"
        invoke = Mock(return_value={"requirements": rows})
        client = Mock()
        client.with_structured_output.return_value = RunnableLambda(invoke)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.evaluation.requirements.JOB_REQUIREMENT_CACHE_DIR",
            Path(tmp) / "requirements",
        ), patch("langchain_openai.ChatOpenAI", return_value=client):
            result = extract_requirements(POSTING)
            self.assertEqual(result.requirements[0].section, "")
            self.assertEqual(
                result.requirements[0].job_quote, "Python or Java required."
            )
            self.assertEqual(result.requirements[1].section, "Nice to have")
            self.assertEqual(len(result.requirements), 2)
            self.assertEqual(extract_requirements(POSTING), result)
            self.assertEqual(invoke.call_count, 1)
            self.assertIsInstance(client.with_structured_output.call_args.args[0], dict)

    def test_persistent_invalid_extraction_is_not_cached(self):
        from langchain_core.runnables import RunnableLambda

        row = referenced_rows()[0]
        invoke = Mock(return_value={"requirements": [{**row, "source_end": 999}]})
        client = Mock()
        client.with_structured_output.return_value = RunnableLambda(invoke)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.evaluation.requirements.JOB_REQUIREMENT_CACHE_DIR",
            Path(tmp) / "requirements",
        ), patch("langchain_openai.ChatOpenAI", return_value=client):
            with self.assertRaises(EvaluationFailure):
                extract_requirements(POSTING)
            self.assertEqual(invoke.call_count, 2)
            self.assertFalse(list(Path(tmp).rglob("*.json")))

    def test_cancelled_extraction_does_not_write_cache(self):
        from langchain_core.runnables import RunnableLambda

        cancelled = [False]

        def invoke(_):
            cancelled[0] = True
            return {"requirements": []}

        client = Mock()
        client.with_structured_output.return_value = RunnableLambda(invoke)
        with tempfile.TemporaryDirectory() as tmp, patch(
            "backend.evaluation.requirements.JOB_REQUIREMENT_CACHE_DIR",
            Path(tmp) / "requirements",
        ), patch("langchain_openai.ChatOpenAI", return_value=client):
            with self.assertRaises(RuntimeError):
                extract_requirements(POSTING, lambda: cancelled[0])
            self.assertFalse(list(Path(tmp).rglob("*.json")))

    def test_unclear_cannot_hard_reject_or_allow_strong_match(self):
        rows = [
            RequirementVerdict(
                requirement="Build APIs",
                importance="unclear",
                verdict="not_met",
                job_quote="Build APIs",
                resume_quote="No API experience",
            )
        ]
        score, category, _, _ = score_requirements(
            rows, "No API experience", "Build APIs"
        )
        self.assertEqual(category, "review")
        rows[0].verdict = "met"
        self.assertEqual(
            score_requirements(rows, "No API experience", "Build APIs")[1], "review"
        )

    def test_mixed_legacy_and_shared_assessments_are_not_averaged(self):
        from backend.evaluation.orchestration import summarize

        base = dict(status="complete", score=90, fit_category="strong_match")
        result = summarize(
            {
                "model_evaluations": {
                    "claude": dict(base),
                    "gpt": dict(base, requirement_set_id="new"),
                    "gemini": dict(base, requirement_set_id="new"),
                }
            }
        )
        self.assertIsNone(result["score"])
        self.assertIsNone(result["provisional_score"])
        self.assertEqual(result["fit_category"], "review")
        self.assertIn("different requirement lists", result["assessment_summary"])

    def test_extraction_failure_does_not_invoke_evaluation_models(self):
        from backend.evaluation.providers import evaluate_jobs

        client = Mock()
        errors = []
        with patch(
            "backend.evaluation.providers.create_evaluation_llm", return_value=client
        ):
            result = evaluate_jobs(
                "Synthetic profile",
                [Document(page_content=POSTING)],
                provider="gpt",
                requirement_loader=Mock(
                    side_effect=EvaluationFailure(
                        "invalid_output", "Invalid shared criteria"
                    )
                ),
                on_error=lambda doc, error: errors.append(error),
                include_all=True,
            )
        self.assertEqual(result, [])
        self.assertEqual(len(errors), 1)
        client.with_structured_output.return_value.invoke.assert_not_called()

    def test_three_models_get_identical_criteria_and_failed_provider_retry_reuses_them(
        self,
    ):
        import json
        from types import SimpleNamespace
        from langchain_core.runnables import RunnableLambda
        from backend.evaluation.orchestration import evaluate_jobs, merge_result

        received = []
        failures = []
        failing = [True]
        shared = criteria()
        doc = Document(
            page_content=POSTING,
            metadata={"url": "https://example.test/shared", "job_description": POSTING},
        )

        def factory(provider):
            def invoke(prompt):
                text = prompt.messages[-1].content
                payload = json.loads(
                    text.split("<shared_requirements>\n")[1].split(
                        "\n</shared_requirements>"
                    )[0]
                )
                received.append((provider, payload))
                value = assessment(shared)
                if provider == "gpt" and failing[0]:
                    value.requirement_verdicts.pop()
                return value

            return SimpleNamespace(
                model=provider,
                with_structured_output=lambda *a, **kw: RunnableLambda(invoke),
            )

        with patch(
            "backend.evaluation.requirements.extract_requirements", return_value=shared
        ) as extract, patch(
            "backend.evaluation.providers.create_evaluation_llm", side_effect=factory
        ), patch.dict(
            "os.environ", {"GEMINI_EVALUATION_RPM": "0"}
        ):
            first = evaluate_jobs(
                "Python and SQL",
                [doc],
                include_all=True,
                on_error=lambda job, error: failures.append(job),
            )[0]
            self.assertEqual(extract.call_count, 1)
            self.assertEqual(
                {name for name, _ in received}, {"gpt", "gemini", "claude"}
            )
            self.assertTrue(
                all(payload == shared.model_dump() for _, payload in received)
            )
            self.assertEqual(first["model_evaluations"]["gpt"]["status"], "failed")
            self.assertEqual(len(failures), 1)
            self.assertIn("_requirement_set", failures[0].metadata)
            received.clear()
            failing[0] = False
            retry = evaluate_jobs("Python and SQL", failures, include_all=True)[0]
            self.assertEqual({name for name, _ in received}, {"gpt"})
            self.assertEqual(extract.call_count, 1)
            merged = merge_result(first, retry)
            self.assertEqual(merged["completed_models"], 3)
            sets = {
                row["requirement_set_id"]
                for row in merged["model_evaluations"].values()
            }
            self.assertEqual(len(sets), 1)

    def test_mandatory_experience_retry_gets_correction_without_changing_criteria(self):
        from langchain_core.runnables import RunnableLambda
        from backend.evaluation.providers import evaluate_jobs

        shared = criteria()
        shared.requirements[0].importance = "nice_to_have"
        invalid = assessment(shared)
        invalid.minimum_professional_years = 5
        invalid.required_experience_evidence = shared.requirements[0].job_quote
        corrected = assessment(shared)
        invoke = Mock(side_effect=[invalid, corrected])
        client = Mock()
        client.with_structured_output.return_value = RunnableLambda(invoke)
        failures = []
        with patch(
            "backend.evaluation.providers.create_evaluation_llm", return_value=client
        ):
            results = evaluate_jobs(
                "Python and SQL",
                [Document(page_content=POSTING)],
                provider="gpt",
                include_all=True,
                requirement_loader=lambda job: shared,
                on_error=lambda job, error: failures.append(error),
            )
        self.assertEqual(failures, [])
        self.assertEqual(len(results), 1)
        self.assertEqual(invoke.call_count, 2)
        self.assertTrue(client.with_structured_output.call_args.kwargs["strict"])
        feedback = invoke.call_args.args[0].to_messages()[-1].content
        self.assertIn("previous assessment failed validation", feedback)
        self.assertIn("use null and an empty string", feedback)
        self.assertEqual(shared.requirements[0].importance, "nice_to_have")

    def test_unclear_experience_cannot_bypass_shared_importance_via_years_guard(self):
        shared = criteria()
        shared.requirements[0].importance = "unclear"
        value = assessment(shared)
        value.minimum_professional_years = 5
        value.required_experience_evidence = shared.requirements[0].job_quote
        with self.assertRaises(EvaluationFailure):
            align_assessment(value, shared)
