"""Runs operations, separate from HTTP route declarations."""

import json
import copy
from collections import defaultdict, deque
import shutil
import threading
import time
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from backend.paths import RUNS_DIR
from backend.schemas.contracts import RunSnapshot

RUNS = {}
RUN_CONTEXTS = {}
# One process owns these dictionaries; all cooperating workers share this lock.
RUNS_LOCK = threading.RLock()
ACTIVE_WORKERS = set()
DELETING = set()
# Uploads not yet searched or saved stay in memory only: run ID -> resume PDF bytes.
UNSAVED = {}
RATE_WINDOWS = defaultdict(deque)
RETENTION_SECONDS = 7 * 24 * 3600


# Signal cooperative cancellation without reporting it as a provider failure.
class RunStopped(Exception):
    pass


# Treat cancellation, deletion, and missing runs as signals to stop publishing work.
def stopped(run_id):
    # Read cancellation and deletion flags together so the worker sees a consistent stop decision.
    with RUNS_LOCK:
        return (
            run_id not in RUNS
            or RUNS[run_id].get("status") == "cancelled"
            or run_id in DELETING
        )


# Raise the internal stop signal before mutating a cancelled or deleted run.
def check_running(run_id):
    if stopped(run_id):
        raise RunStopped()


# Release worker ownership and finish deferred deletion when background work exits.
def run_worker(run_id, function, *args):
    try:
        function(run_id, *args)
    finally:
        # Mark this worker finished and handle any pending deletion as one protected update.
        # Another request must not delete or reopen these files halfway through cleanup.
        with RUNS_LOCK:
            ACTIVE_WORKERS.discard(run_id)
            if run_id in DELETING:
                shutil.rmtree(RUNS_DIR / run_id, ignore_errors=True)
                DELETING.discard(run_id)
            elif run_id in RUNS:
                RUNS[run_id]["worker_active"] = False
                persist_run(run_id)


# Increment the snapshot revision and replace its file atomically.
def persist_run(run_id):
    if run_id in UNSAVED:
        return
    state = RUNS[run_id]
    state["revision"] = state.get("revision", 0) + 1
    temporary = run_state_path(run_id).with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temporary.replace(run_state_path(run_id))


# Translate backend progress into the phase sequence shown by the interface.
def phases_for(run):
    phase = run.get("phase", 0)
    status_value = run.get("status")
    return {
        str(number): (
            "failed"
            if status_value == "error" and number == phase
            else (
                "done"
                if number < phase
                or status_value == "complete"
                or (number == 1 and status_value == "awaiting_search")
                else (
                    "active"
                    if number == phase and status_value == "running"
                    else "pending"
                )
            )
        )
        for number in range(1, 5)
    }


# Return a detached run snapshot with the current worker lifecycle state.
def snapshot(run_id):
    # Copy the run and its worker status while other lock-using updates wait.
    # The response then uses this copy instead of exposing the shared dictionary.
    with RUNS_LOCK:
        if run_id not in RUNS:
            raise HTTPException(404, "Run not found.")
        data = copy.deepcopy(RUNS[run_id])
        data["runId"] = run_id
        data["phases"] = phases_for(data)
        data["worker_active"] = run_id in ACTIVE_WORKERS
        # Rate limits are handled behind the scenes, including in older saved runs.
        from backend.search.board_cooldown import saved_rate_limit

        data["scrape_errors"] = [
            message
            for message in data.get("scrape_errors") or []
            if not saved_rate_limit(message)
        ]
        return RunSnapshot.model_validate(data).model_dump()


# Remove public run state immediately and defer file deletion while a worker is active.
def remove_run(run_id):
    # Remove the run from shared memory and decide whether its files can be deleted.
    # An active worker keeps the files until its cleanup step finishes.
    with RUNS_LOCK:
        RUNS.pop(run_id, None)
        RUN_CONTEXTS.pop(run_id, None)
        unsaved = UNSAVED.pop(run_id, None) is not None
        if run_id in ACTIVE_WORKERS:
            # An unsaved upload has no folder to mark; nothing reaches disk.
            if not unsaved:
                (RUNS_DIR / run_id / ".delete-requested").touch()
            DELETING.add(run_id)
        else:
            shutil.rmtree(RUNS_DIR / run_id, ignore_errors=True)


# Apply run retention without deleting independently saved profiles.
def expire_runs():
    # Find and remove expired runs without another lock-using request changing the run list.
    with RUNS_LOCK:
        expired = [
            key
            for key, run in RUNS.items()
            if time.time() - run.get("created_at", time.time()) > RETENTION_SECONDS
        ]
        for key in expired:
            remove_run(key)


async def limits(request: Request, call_next):
    expire_runs()
    if request.method in {"POST", "PUT"}:
        try:
            if int(request.headers.get("content-length", "0")) > 6 * 1024 * 1024:
                return JSONResponse(
                    {"detail": "Request exceeds the 5 MB resume upload limit."}, 413
                )
        except ValueError:
            return JSONResponse({"detail": "Invalid content length."}, 400)
    if request.method in {"POST", "PUT"}:
        key = request.client.host if request.client else "local"
        now = time.monotonic()
        # Update this client’s request counter as one operation.
        # Concurrent requests must not both pass the limit using the same old count.
        with RUNS_LOCK:
            window = RATE_WINDOWS[key]
            while window and window[0] < now - 60:
                window.popleft()
            if len(window) >= 30:
                return JSONResponse(
                    {"detail": "Too many requests. Please wait a minute and retry."},
                    429,
                    headers={"Retry-After": "60"},
                )
            window.append(now)
    return await call_next(request)


def run_state_path(run_id):
    """Return the durable status file for a pipeline run."""
    return RUNS_DIR / run_id / "state.json"


def write_context(run_id, context):
    """Store the evaluation context in memory, and on disk once the run is saved."""
    RUN_CONTEXTS[run_id] = context
    if run_id not in UNSAVED:
        run_context_path(run_id).write_text(context, encoding="utf-8")


def commit_upload(run_id):
    """Write an in-memory upload to disk when it is first searched or saved."""
    with RUNS_LOCK:
        data = UNSAVED.pop(run_id, None)
        if data is None:
            return
        (RUNS_DIR / run_id).mkdir(parents=True, exist_ok=True)
        (RUNS_DIR / run_id / "resume.pdf").write_bytes(data)
        if run_id in RUN_CONTEXTS:
            write_context(run_id, RUN_CONTEXTS[run_id])
        if run_id in RUNS:
            persist_run(run_id)


def run_context_path(run_id):
    """Return the durable profile-context file used by the search phase."""
    return RUNS_DIR / run_id / "resume_context.txt"


def load_persisted_runs():
    """Restore completed or waiting runs after an API restart or wake-up."""
    for state_file in RUNS_DIR.glob("*/state.json"):
        try:
            if (state_file.parent / ".delete-requested").exists():
                shutil.rmtree(state_file.parent, ignore_errors=True)
                continue
            state = json.loads(state_file.read_text(encoding="utf-8"))
            # Older snapshots predate candidate-fit counters and categories.
            # Fill those fields safely so a refresh or API restart remains
            # compatible with results generated by earlier versions.
            recommendations = state.get("recommendations", [])
            state.setdefault("jobs_found", 0)
            state.setdefault("jobs_screened", state["jobs_found"])
            state.setdefault("evaluated_jobs", len(recommendations))
            state.setdefault("displayed_jobs", len(recommendations))
            state.setdefault("excluded_jobs", 0)
            state.setdefault("excluded_reasons", {})
            # Older snapshots retained only exclusion counts, not job details.
            state.setdefault("excluded_recommendations", [])
            state.setdefault("evaluation_total", state["evaluated_jobs"])
            state.setdefault("evaluation_failed", 0)
            state.setdefault("evaluation_errors", [])
            state.setdefault("evaluation_skipped", 0)
            # Completed historical runs were evaluated with Claude.
            state.setdefault("evaluation_model", "claude")
            for recommendation in recommendations:
                recommendation.setdefault(
                    "fit_category",
                    "strong_match" if recommendation.get("is_strong_fit") else "review",
                )
                recommendation.setdefault("mismatch_reason", "")
            if state["id"] != state_file.parent.name:
                continue
            state.setdefault("created_at", state_file.stat().st_mtime)
            state["worker_active"] = False
            if time.time() - state["created_at"] > RETENTION_SECONDS:
                shutil.rmtree(state_file.parent, ignore_errors=True)
                continue
            if state.get("status") == "running":
                state.update(
                    status="error",
                    error="The server restarted during processing. Retry from your saved profile or upload again.",
                )
            RUNS[state["id"]] = state
            context_file = run_context_path(state["id"])
            if context_file.exists():
                RUN_CONTEXTS[state["id"]] = context_file.read_text(encoding="utf-8")
        except (OSError, json.JSONDecodeError, KeyError):
            # Ignore incomplete snapshots; a new run can still be created.
            continue


def update_run(run_id, **changes):
    """Update a run safely while the background pipeline is working."""
    # Check that the run is still allowed to change, then update and save its state.
    # Cancellation or deletion cannot interrupt this protected sequence.
    with RUNS_LOCK:
        check_running(run_id)
        RUNS[run_id].update(changes)
        persist_run(run_id)
