# Regression coverage for structured output; fixtures and assertions document the expected behavior.
import unittest
from pydantic import ValidationError
from backend.schemas.evaluation import JobEvaluation, ReferencedRequirements
from backend.evaluation.structured_output import (
    required_output_schema,
    validate_assessment_response,
)
from backend.evaluation.runtime import EvaluationFailure
from types import SimpleNamespace
from backend.evaluation.runtime import classify_failure


class StructuredOutputTests(unittest.TestCase):
    def test_claude_truncation_is_explicit_and_does_not_expose_raw_text(self):
        response = dict(
            raw=SimpleNamespace(
                response_metadata={"stop_reason": "max_tokens"}, content="private"
            ),
            parsed=None,
            parsing_error=ValueError("private"),
        )
        with self.assertRaises(EvaluationFailure) as error:
            validate_assessment_response(response, JobEvaluation)
        # Check the expected behavior: claude truncation is explicit and does not expose raw text.
        self.assertIn("truncated", str(error.exception))
        self.assertNotIn("private", str(error.exception))

    def test_invalid_fields_are_reported_without_values_or_extra_keys(self):
        with self.assertRaises(EvaluationFailure) as error:
            validate_assessment_response(
                {"work_type": "private", "private-key": "private"}, JobEvaluation
            )
        # Check the expected behavior: invalid fields are reported without values or extra keys.
        self.assertIn("work_type", str(error.exception))
        self.assertNotIn("private", str(error.exception))

    def test_nested_schema_errors_identify_field_without_private_values(self):
        with self.assertRaises(EvaluationFailure) as error:
            validate_assessment_response(
                {
                    "requirements": [
                        {
                            "requirement": "private input",
                            "importance": "private importance",
                            "type": "skill",
                            "source_start": "private coordinate",
                            "source_end": 2,
                            "private-key": "private extra",
                        }
                    ]
                },
                ReferencedRequirements,
            )
        message = str(error.exception)
        self.assertIn("requirements[0].source_start (expected integer)", message)
        self.assertIn(
            "requirements[0].importance (value outside allowed choices)", message
        )
        self.assertIn("requirements[0].section (required field missing)", message)
        self.assertNotIn("private", message)

    def test_valid_claude_envelope_is_locally_validated(self):
        result = validate_assessment_response(
            dict(
                raw=SimpleNamespace(response_metadata={"stop_reason": "end_turn"}),
                parsing_error=None,
                parsed=dict(
                    match_rationale="Synthetic",
                    missing_skills=[],
                    apply_url="https://example.test",
                ),
            ),
            JobEvaluation,
        )
        # Check the expected behavior: valid claude envelope is locally validated.
        self.assertEqual(result.match_rationale, "Synthetic")

    def test_all_nested_fields_required_without_mutating_local_schema(self):
        original = JobEvaluation.model_json_schema()
        schema = required_output_schema(JobEvaluation)

        def check(node):
            if isinstance(node, list):
                for child in node:
                    check(child)
            elif isinstance(node, dict):
                self.assertNotIn("default", node)
                self.assertNotIn("minimum", node)
                self.assertNotIn("maximum", node)
                if node.get("type") == "object":
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                    self.assertFalse(node["additionalProperties"])
                for child in node.values():
                    check(child)

        check(schema)
        # Check the expected behavior: all nested fields required without mutating local schema.
        self.assertEqual(original, JobEvaluation.model_json_schema())

    def test_local_validation_still_enforces_score_range(self):
        with self.assertRaises(ValidationError):
            JobEvaluation.model_validate(
                dict(score=200, match_rationale="", missing_skills=[], apply_url="")
            )

    def test_complexity_error_is_actionable_without_raw_payload(self):
        failure = classify_failure(ValueError("Schema is too complex. private data"))
        # Check the expected behavior: complexity error is actionable without raw payload.
        self.assertIn("too complex", str(failure))
        self.assertNotIn("private data", str(failure))
