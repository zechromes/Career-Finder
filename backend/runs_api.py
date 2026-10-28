"""Run status, progress, cancellation, deletion, and export handlers."""

import json
import asyncio
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
import backend.runs as runs


# Return the authoritative persisted-search snapshot for polling clients.
async def get_search(run_id: str):
    return runs.snapshot(run_id)


async def delete_search(run_id: str):
    """Flush the active run and all generated files when starting over."""
    runs.snapshot(run_id)
    runs.remove_run(run_id)
    return {
        "deleted": run_id not in runs.DELETING,
        "deletion_pending": run_id in runs.DELETING,
    }


# Restrict downloads to supported export names within this run’s directory.
async def download_search_export(run_id: str, file_name: str):
    runs.snapshot(run_id)
    allowed = {"retrieved_jobs.csv", "relevant_jobs.xlsx"}
    result_file = runs.RUNS_DIR / run_id / file_name
    if (
        (runs.RUNS_DIR / run_id).resolve().parent != runs.RUNS_DIR.resolve()
        or file_name not in allowed
        or not result_file.is_file()
    ):
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(
        result_file, filename=file_name, media_type="application/octet-stream"
    )


# Mark the run cancelled while allowing in-flight calls to finish safely.
async def cancel_search(run_id: str):
    # Record cancellation and save it before another locked result update can proceed.
    # Calls already sent to a provider may finish, but later updates check this flag.
    with runs.RUNS_LOCK:
        runs.snapshot(run_id)
        if runs.RUNS[run_id]["status"] == "running":
            runs.RUNS[run_id].update(
                status="cancelled",
                message="Cancelled. In-flight provider requests may still finish; no further results will be saved.",
            )
            runs.persist_run(run_id)
    return runs.snapshot(run_id)


# Stream snapshot updates until completion, deletion, or client disconnect.
async def stream_search_progress(run_id: str, request: Request):
    runs.snapshot(run_id)

    # Emit progress events from changing snapshots rather than starting new pipeline work.
    async def events():
        previous = None
        seen_jobs = set()
        while not await request.is_disconnected():
            try:
                current = runs.snapshot(run_id)
            except HTTPException:
                yield "event: run_deleted\ndata: {}\n\n"
                return
            revision = current.get("revision", 0)
            if previous != revision:
                yield f"id: {revision}\nevent: phase_update\ndata: {json.dumps(current)}\n\n"
                if current["status"] == "awaiting_search":
                    yield f"event: profile_extracted\ndata: {json.dumps(current)}\n\n"
                if current.get("phase") == 2:
                    yield f"event: scrape_progress\ndata: {json.dumps(current)}\n\n"
                for job in current.get("recommendations", []) + current.get(
                    "excluded_recommendations", []
                ):
                    key = (
                        job.get("jobId")
                        or job.get("apply_url")
                        or (job.get("title", "") + job.get("company", ""))
                    )
                    if key not in seen_jobs:
                        seen_jobs.add(key)
                        yield f"event: job_evaluated\ndata: {json.dumps(job)}\n\n"
                if current["status"] in {"complete", "error", "cancelled"}:
                    event = (
                        "run_completed"
                        if current["status"] == "complete"
                        else "run_failed"
                    )
                    yield f"event: {event}\ndata: {json.dumps(current)}\n\n"
                previous = revision
            if current["status"] != "running" and not current.get("worker_active"):
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def job_actions(run_id, update=None):
    """Serialize edits with profile saves so action updates survive new runs and expiry."""
    from backend.profiles import storage

    with storage.LOCK, runs.RUNS_LOCK:
        runs.snapshot(run_id)
        run = runs.RUNS[run_id]
        profile_id = run.get("saved_profile_id")
        profile = None
        if profile_id:
            try:
                profile = storage.read_profile(profile_id)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
        actions = dict((profile or run).get("job_actions", {}))
        feedback = dict((profile or run).get("dismissal_feedback", {}))
        if update is not None:
            if len(actions) >= 10000 and update.key not in actions:
                raise HTTPException(422, "Saved job action limit reached.")
            if update.action == "dismissed":
                if not update.value or (
                    "dismissal" in update.model_fields_set and update.dismissal is None
                ):
                    feedback.pop(update.key, None)
                elif update.dismissal is not None:
                    from backend.search.preferences import action_key, make_preference

                    job = next(
                        (
                            item
                            for field in ("recommendations", "excluded_recommendations")
                            for item in run.get(field, [])
                            if action_key(item) == action_key({"apply_url": update.key})
                            or item.get("jobId") == update.key
                        ),
                        None,
                    )
                    if job is None:
                        raise HTTPException(
                            422,
                            "Choose a job in this workspace to record a dismissal reason.",
                        )
                    feedback[update.key] = make_preference(update.dismissal, job)
            actions[update.key] = {
                **actions.get(update.key, {}),
                update.action: update.value,
            }
            if profile is not None:
                profile["job_actions"] = actions
                profile["dismissal_feedback"] = feedback
                storage.write_profile(profile)
            run["job_actions"] = actions
            run["dismissal_feedback"] = feedback
            runs.persist_run(run_id)
        return {"actions": actions, "dismissal_feedback": feedback}
