"""Evaluation service operations, separate from HTTP route declarations."""

from backend.observability import stage, mark
import json
import copy
from fastapi import HTTPException
from backend.evaluation.orchestration import merge_result, identity
from backend.exports import export_jobs_excel
import backend.configuration as configuration
import backend.runs as runs
import backend.evaluation.orchestration as orchestration


def group_exclusion_reasons(excluded_jobs):
    """Return a small, UI-ready tally of candidate-fit exclusion reasons."""
    grouped = {}
    for job in excluded_jobs:
        reason = str(job.get("reason") or "candidate-fit mismatch").strip()
        grouped[reason] = grouped.get(reason, 0) + 1
    return grouped


def candidate_fit_category(recommendation):
    """Read a new category or safely infer it from an older recommendation."""
    return recommendation.get("fit_category") or (
        "strong_match" if recommendation.get("is_strong_fit") else "review"
    )


def upsert_assessment(run_id, result):
    """Replace one job across categories as new model results arrive."""
    run = runs.RUNS[run_id]
    key = identity(result)
    previous = next(
        (
            item
            for field in ("recommendations", "excluded_recommendations")
            for item in run.get(field, [])
            if identity(item) == key
        ),
        {},
    )
    merged = merge_result(previous, result)
    if previous:
        merged["added_at"] = previous.get("added_at")
    for field in ("recommendations", "excluded_recommendations"):
        run[field] = [item for item in run.get(field, []) if identity(item) != key]
    field = (
        "excluded_recommendations"
        if candidate_fit_category(merged) == "not_suitable"
        else "recommendations"
    )
    run.setdefault(field, []).append(merged)
    return merged


# Replay checkpointed provider failures while preserving successful assessments.
@stage("evaluation.retry")
def retry_failed_evaluations(run_id):
    from langchain_core.documents import Document

    run_dir = runs.RUNS_DIR / run_id
    try:
        entries = json.loads((run_dir / "failed_jobs.json").read_text())
        # Copy the run and read its candidate context before retrying failed assessments.
        # Provider calls happen outside this lock.
        with runs.RUNS_LOCK:
            context = runs.RUN_CONTEXTS[run_id]
            run = copy.deepcopy(runs.RUNS[run_id])
        successes = []
        failures = []
        remaining = []

        # Persist retry progress without repeating providers that already succeeded.
        def save(result):
            # Merge a successful retry and update its saved checkpoints together.
            # This keeps completed provider results consistent with the remaining retry work.
            with runs.RUNS_LOCK:
                runs.check_running(run_id)
                successes.append(result)
                merged = upsert_assessment(run_id, result)
                completed = {
                    (item.get("apply_url"), provider)
                    for item in successes
                    for provider, assessment in item.get(
                        "model_evaluations", {}
                    ).items()
                    if assessment.get("status") == "complete"
                }
                pending_entries = [
                    entry
                    for entry in entries
                    if (
                        entry.get("metadata", {}).get("url"),
                        entry.get("metadata", {}).get("_evaluation_provider"),
                    )
                    not in completed
                ]
                if not result.get("model_evaluations"):
                    pending_entries = [
                        entry
                        for entry in pending_entries
                        if entry.get("metadata", {}).get("url")
                        != result.get("apply_url")
                    ]
                with (run_dir / "job_assessments.jsonl").open("a") as output:
                    output.write(json.dumps(result) + "\n")
                runs.update_run(
                    run_id,
                    evaluated_jobs=len(runs.RUNS[run_id].get("recommendations", []))
                    + len(runs.RUNS[run_id].get("excluded_recommendations", [])),
                )
                (run_dir / "failed_jobs.json").write_text(json.dumps(pending_entries))

        # Record a failed assessment while retaining other providers’ completed work.
        def failure(job, error):
            mark("partial")
            runs.check_running(run_id)
            remaining.append(
                {"page_content": job.page_content, "metadata": job.metadata}
            )
            failures.append(
                {
                    "title": job.metadata.get("title", ""),
                    "company": job.metadata.get("company", ""),
                    "apply_url": job.metadata.get("url", ""),
                    "provider": job.metadata.get("_evaluation_provider", ""),
                    "category": error.category,
                    "message": str(error),
                    "skipped": error.skipped,
                }
            )

        groups = {}
        for entry in entries:
            roles = tuple(
                entry.get("metadata", {}).get(
                    "_evaluation_target_roles",
                    run.get("search_inputs", {}).get("queries", []),
                )
            )
            groups.setdefault(roles, []).append(Document(**entry))
        from backend.profiles.service import evaluation_cache_directory

        for roles, documents in groups.items():
            runs.check_running(run_id)
            orchestration.evaluate_jobs(
                context,
                documents,
                include_all=True,
                cache_directory=evaluation_cache_directory(run_id),
                provider=run.get(
                    "evaluation_model", configuration.DEFAULT_EVALUATION_PROVIDER
                ),
                candidate_profile=run["profile"],
                target_roles=list(roles),
                on_result=save,
                on_error=failure,
                should_cancel=lambda: runs.stopped(run_id),
            )
        # Save remaining failures, refresh the export, and finalize retry status together.
        # Check cancellation before writing the final state.
        with runs.RUNS_LOCK:
            runs.check_running(run_id)
            (run_dir / "failed_jobs.json").write_text(json.dumps(remaining))
            recommendations = runs.RUNS[run_id].get("recommendations", [])
            export_jobs_excel(recommendations, run_dir / "relevant_jobs.xlsx")
            runs.update_run(
                run_id,
                status="complete",
                evaluation_errors=failures,
                evaluation_failed=len(failures),
                displayed_jobs=len(recommendations),
                excluded_jobs=len(
                    runs.RUNS[run_id].get("excluded_recommendations", [])
                ),
                message="Evaluation retry finished.",
                error=None,
            )
    except runs.RunStopped:
        mark("cancelled")
        return
    except Exception as exc:
        mark("failed")
        if not runs.stopped(run_id):
            runs.update_run(run_id, status="error", error=str(exc))


# Admit a targeted retry only when the run has no competing worker.
async def retry_search_evaluations(run_id: str):
    # Check for pending failures and reserve the run before launching its retry worker.
    # Another lock-using request cannot claim the same run during this sequence.
    with runs.RUNS_LOCK:
        run = runs.snapshot(run_id)
        if run_id in runs.ACTIVE_WORKERS or run["status"] == "running":
            raise HTTPException(409, "A worker is still active.")
        path = runs.RUNS_DIR / run_id / "failed_jobs.json"
        if not path.exists() or not json.loads(path.read_text()):
            raise HTTPException(
                409,
                "There are no saved failed jobs to retry. Start a new search instead.",
            )
        runs.RUNS[run_id].update(
            status="running",
            phase=4,
            error=None,
            message="Retrying failed evaluations only",
        )
        runs.persist_run(run_id)
        runs.ACTIVE_WORKERS.add(run_id)
        runs.threading.Thread(
            target=runs.run_worker, args=(run_id, retry_failed_evaluations), daemon=True
        ).start()
    return {"id": run_id, "runId": run_id}
