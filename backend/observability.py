"""Opt-in, payload-free LangSmith stage tracing. Never trace function arguments."""

from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from datetime import datetime, timezone
from functools import lru_cache, wraps
import inspect
import logging
import os
import uuid

from langsmith import Client, tracing_context
from urllib3.util.retry import Retry

_CURRENT = ContextVar("career_trace", default=None)
_LOG = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _client():
    return Client(
        api_key=os.environ["LANGSMITH_API_KEY"],
        api_url=os.getenv("LANGSMITH_ENDPOINT") or "https://api.smith.langchain.com",
        timeout_ms=1500,
        retry_config=Retry(total=0),
        omit_traced_runtime_info=True,
    )


def _send(operation, *args, **kwargs):
    try:
        operation(*args, **kwargs)
    except Exception:
        # Telemetry must never fail, retry or alter application work.
        _LOG.warning("LangSmith trace delivery failed; application work continues.")


def mark(outcome):
    """Record only predefined outcomes, including failures handled by the pipeline."""
    if outcome not in {"failed", "partial", "cancelled"}:
        return
    state = _CURRENT.get()
    while state is not None:
        if state["outcome"] not in {"failed", "cancelled"}:
            state["outcome"] = outcome
        state = state.get("parent")


@contextmanager
def _span(name, labels=None, run_type="chain"):
    # Disable implicit LangChain tracing: it can include prompts and private inputs.
    with tracing_context(enabled=False):
        enabled = os.getenv("CAREER_LANGSMITH_TRACING", "false").lower() == "true"
        if not enabled or not os.getenv("LANGSMITH_API_KEY"):
            yield None
            return
        try:
            client = _client()
        except Exception:
            _LOG.warning("LangSmith is unavailable; application work continues.")
            yield None
            return
        parent = _CURRENT.get()
        identifier = uuid.uuid4()
        started = datetime.now(timezone.utc)
        order = started.strftime("%Y%m%dT%H%M%S%fZ") + str(identifier)
        state = {
            "id": identifier,
            "trace_id": parent["trace_id"] if parent else identifier,
            "dotted_order": parent["dotted_order"] + "." + order if parent else order,
            "outcome": "completed",
            "parent": parent,
        }
        token = _CURRENT.set(state)
        _send(
            client.create_run,
            name=name,
            inputs={},
            run_type=run_type,
            id=identifier,
            start_time=started,
            trace_id=state["trace_id"],
            dotted_order=state["dotted_order"],
            parent_run_id=parent["id"] if parent else None,
            project_name=os.getenv("LANGSMITH_PROJECT") or "career-tracker",
            extra={"metadata": {"payload_policy": "counts-only", **(labels or {})}},
        )
        if parent is None:
            _LOG.info("LangSmith trace started: %s", identifier)
        error = None
        try:
            yield state
        except BaseException as exc:
            error = type(
                exc
            ).__name__  # No exception text or traceback leaves the process.
            state["outcome"] = "failed" if isinstance(exc, Exception) else "cancelled"
            raise
        finally:
            _CURRENT.reset(token)
            outputs = {"outcome": state["outcome"], **state.get("metrics", {})}
            if "result_count" in state:
                outputs["result_count"] = state["result_count"]
            _send(
                client.update_run,
                identifier,
                end_time=datetime.now(timezone.utc),
                outputs=outputs,
                error=error
                or ("Stage failed" if state["outcome"] == "failed" else None),
                trace_id=state["trace_id"],
                dotted_order=state["dotted_order"],
                parent_run_id=parent["id"] if parent else None,
                **({"events": state["events"]} if "events" in state else {}),
            )


def stage(name):
    """Trace a synchronous or async stage without serializing its arguments/results."""

    def decorate(function):
        signature = inspect.signature(function)

        def labels(args, kwargs):
            bound = signature.bind_partial(*args, **kwargs).arguments
            allowed = {
                "linkedin",
                "indeed",
                "glassdoor",
                "seek",
                "adzuna",
                "claude",
                "gpt",
                "gemini",
                "openai",
            }
            return {
                key: value
                for key, value in bound.items()
                if key in {"provider", "board", "site", "model_type"}
                and isinstance(value, str)
                and value in allowed
            }

        def complete(state, result):
            if state is not None and isinstance(result, (list, tuple)):
                state["result_count"] = len(result)
            return result

        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def asynchronous(*args, **kwargs):
                with _span(name, labels(args, kwargs)) as state:
                    return complete(state, await function(*args, **kwargs))

            return asynchronous

        @wraps(function)
        def synchronous(*args, **kwargs):
            with _span(name, labels(args, kwargs)) as state:
                return complete(state, function(*args, **kwargs))

        return synchronous

    return decorate


def submit(executor, operation, *args):
    """Give each concurrent task its own copy of the current trace context."""
    return executor.submit(copy_context().run, operation, *args)


@contextmanager
def collection_batch(board, number, offset=0, deferred=False):
    """Group a collection round using only public source labels and numeric counters."""
    board = (
        board
        if board in {"linkedin", "indeed", "glassdoor", "seek", "adzuna", "google"}
        else "mixed"
    )
    name = f"jobs.{'deferred_batch' if deferred else 'batch'}.{board}"
    with _span(
        name, {"board": board, "batch_number": int(number), "offset": int(offset)}
    ) as state:
        yield state


@contextmanager
def collection_step(name):
    """Name the two deduplication passes and local filter stages explicitly."""
    if name not in {
        "filter_cards",
        "deduplicate_incoming",
        "filter_descriptions",
        "merge_unique_results",
    }:
        raise ValueError("Unknown collection step")
    with _span("jobs." + name) as state:
        yield state
