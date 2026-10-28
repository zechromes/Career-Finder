"""Provider-facing schemas with predictable compilation complexity."""

from copy import deepcopy
from pydantic import ValidationError
from backend.evaluation.runtime import EvaluationFailure


def validate_assessment_response(response, model):
    """Validate output without including response text or private input in errors."""
    if isinstance(response, dict) and "raw" in response and "parsed" in response:
        raw = response["raw"]
        metadata = getattr(raw, "response_metadata", {}) or {}
        if metadata.get("stop_reason") == "max_tokens":
            raise EvaluationFailure(
                "invalid_output",
                "Claude assessment was truncated at its output token limit. Retry failed evaluations.",
            )
        if response.get("parsing_error"):
            raise EvaluationFailure(
                "invalid_output",
                "Claude response could not be parsed as the assessment schema. Retry failed evaluations.",
            )
        response = response["parsed"]
    try:
        return (
            response if isinstance(response, model) else model.model_validate(response)
        )
    except ValidationError as exc:
        # Walk only schema-defined properties: model-supplied extra keys and
        # validation messages can contain private content and must never be echoed.
        schema = model.model_json_schema()
        details = []
        reasons = {
            "missing": "required field missing",
            "int_type": "expected integer",
            "int_parsing": "expected integer",
            "string_type": "expected string",
            "list_type": "expected list",
            "literal_error": "value outside allowed choices",
            "greater_than_equal": "value below allowed minimum",
            "extra_forbidden": "unexpected field",
        }
        for error in exc.errors(include_input=False, include_context=False)[:8]:
            node = schema
            path = ""
            for part in error["loc"]:
                if "$ref" in node:
                    node = schema.get("$defs", {}).get(
                        node["$ref"].rsplit("/", 1)[-1], {}
                    )
                if isinstance(part, int) and node.get("type") == "array":
                    path += f"[{part}]"
                    node = node.get("items", {})
                elif isinstance(part, str) and part in node.get("properties", {}):
                    path += ("." if path else "") + part
                    node = node["properties"][part]
                else:
                    break
            reason = reasons.get(error["type"], "invalid value")
            details.append((path or "response") + " (" + reason + ")")
        suffix = ": " + "; ".join(dict.fromkeys(details)) if details else ""
        raise EvaluationFailure(
            "invalid_output",
            "Assessment failed schema validation"
            + suffix
            + ". Retry failed evaluations.",
        ) from None


def required_output_schema(model):
    """Require explicit empty/null values instead of optional-property branches.

    Local Pydantic models retain their defaults and numeric validation for old
    saved data; only the provider-facing schema is simplified.
    """
    schema = deepcopy(model.model_json_schema())

    # Simplify nested schema nodes without modifying the local validation model.
    def visit(node):
        if isinstance(node, list):
            for value in node:
                visit(value)
        elif isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object" or "properties" in node:
                node["required"] = list(node.get("properties", {}))
                node["additionalProperties"] = False
            for key in (
                "minimum",
                "maximum",
                "exclusiveMinimum",
                "exclusiveMaximum",
                "multipleOf",
            ):
                node.pop(key, None)
            for value in node.values():
                visit(value)

    visit(schema)
    return schema
