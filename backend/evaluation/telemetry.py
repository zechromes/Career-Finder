"""Payload-free metrics from streaming callbacks and provider usage reports."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from time import perf_counter

from langchain_core.callbacks import BaseCallbackHandler
from backend.observability import _span


def streaming_options(provider):
    # Keep ordinary execution unchanged when optional tracing is disabled.
    if os.getenv(
        "CAREER_LANGSMITH_TRACING", "false"
    ).lower() != "true" or not os.getenv("LANGSMITH_API_KEY"):
        return {}
    return {"streaming": True, **({"stream_usage": True} if provider == "gpt" else {})}


class ModelMetrics(BaseCallbackHandler):
    """Never retain prompts, chunks, messages, or exception contents."""

    def __init__(self, state):
        self.state = state
        self.started = None
        self.first = None
        self.last = None

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.started = perf_counter()

    def on_llm_new_token(self, token, *, chunk=None, **kwargs):
        message = getattr(chunk, "message", None)
        # Ignore empty metadata chunks; structured tool arguments count as output.
        arguments = any(
            part.get("args")
            for part in (getattr(message, "tool_call_chunks", None) or [])
        )
        if not token and not arguments:
            return
        now = perf_counter()
        if self.first is None:
            self.first = now
            self.state["events"] = [
                {"name": "new_token", "time": datetime.now(timezone.utc).isoformat()}
            ]
            if self.started is not None:
                self.state["metrics"]["ttft"] = now - self.started
        self.last = now

    def on_llm_end(self, response, **kwargs):
        usage = None
        for group in response.generations:
            for generation in group:
                usage = getattr(
                    getattr(generation, "message", None), "usage_metadata", None
                )
                if usage:
                    break
            if usage:
                break
        if not isinstance(usage, dict):
            return
        # Strict allowlist: metadata can otherwise contain arbitrary provider payloads.
        clean = {
            key: usage[key]
            for key in ("input_tokens", "output_tokens", "total_tokens")
            if type(usage.get(key)) is int and usage[key] >= 0
        }
        for key, allowed in (
            ("input_token_details", ("cache_read", "cache_creation")),
            ("output_token_details", ("reasoning",)),
        ):
            details = usage.get(key) or {}
            values = {
                k: details[k]
                for k in allowed
                if type(details.get(k)) is int and details[k] >= 0
            }
            if values:
                clean[key] = values
        self.state["metrics"]["usage_metadata"] = clean
        # Client-observed average, not the provider's internal decoding latency.
        # Hidden reasoning cannot be assigned arrival timestamps, so exclude it.
        count = clean.get("output_tokens", 0) - clean.get(
            "output_token_details", {}
        ).get("reasoning", 0)
        if self.first is not None and self.last > self.first and count > 1:
            self.state["metrics"]["tpot"] = (self.last - self.first) / (count - 1)


@contextmanager
def model_request(provider, model):
    labels = {
        "ls_provider": {
            "gpt": "openai",
            "claude": "anthropic",
            "gemini": "google_genai",
        }[provider],
        "ls_model_name": model,
        "timing_unit": "seconds",
        "timing_basis": "client-observed streamed chunks",
    }
    with _span("evaluation.model_request", labels, run_type="llm") as state:
        if state is None:
            yield []
        else:
            state["metrics"] = {}
            yield [ModelMetrics(state)]
