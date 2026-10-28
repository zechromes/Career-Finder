"""Profiles service operations, separate from HTTP route declarations."""

import json
import copy
import shutil
import time
import uuid
from backend.schemas.resume import ResumeProfile
from backend.search.history import missing_journal_assessments
from backend.exports import export_jobs_excel
from backend.cli import profile_to_context
import backend.evaluation.service as evaluation_service
import backend.runs as runs
import backend.profiles.storage as storage


def save_completed_search_profile(run_id):
    """Save a reusable workspace after successful completion; keep results on failure."""
    from backend.schemas.saved_profiles import SavedProfileInput
    from backend.profiles.storage import create_profile, update_profile

    # Take a copy of the completed run for profile saving.
    # The slower profile-save work below happens after releasing this lock.
    with runs.RUNS_LOCK:
        if run_id not in runs.RUNS or runs.RUNS[run_id].get("status") != "complete":
            return
        run = copy.deepcopy(runs.RUNS[run_id])
    try:
        profile_id = run.get("saved_profile_id")
        existing = storage.read_profile(profile_id) if profile_id else None
        profile = ResumeProfile.model_validate(run["profile"])
        preferences = run.get("preferences") or run.get("search_inputs") or None
        source_id = (
            run_id if (runs.RUNS_DIR / run_id / "resume.pdf").is_file() else None
        )
        body = SavedProfileInput(
            name=(
                existing["name"] if existing else (profile.name or "Saved resume")[:100]
            ),
            profile=profile,
            preferences=preferences,
            source_run_id=source_id,
        )
        saved = update_profile(profile_id, body) if existing else create_profile(body)
        with storage.LOCK, runs.RUNS_LOCK:
            runs.check_running(run_id)
            # Older profile-only workspaces have no PDF-copy step. Transfer their
            # private state at the same time as attaching the new saved owner.
            if not existing and source_id is None:
                saved["job_actions"] = copy.deepcopy(
                    runs.RUNS[run_id].get("job_actions", {})
                )
                saved["dismissal_feedback"] = copy.deepcopy(
                    runs.RUNS[run_id].get("dismissal_feedback", {})
                )
                cached = runs.RUNS_DIR / run_id / "evaluations"
                if cached.is_dir():
                    shutil.copytree(
                        cached,
                        storage.profile_path(saved["id"]).with_suffix("")
                        / "evaluations",
                        dirs_exist_ok=True,
                    )
                storage.write_profile(saved)
            runs.update_run(
                run_id,
                saved_profile_id=saved["id"],
                saved_profile_name=saved["name"],
                profile_save_error=None,
            )
    except Exception:
        if not runs.stopped(run_id):
            runs.update_run(
                run_id,
                profile_save_error="Results are ready, but your profile could not be saved automatically. Use Save resume to try again.",
            )


async def create_search_from_profile(profile_id: str, fresh: bool = False):
    """Resume the latest linked search, or explicitly create a new search."""
    saved = storage.read_profile(profile_id)
    if not fresh:
        # Select and reopen a linked workspace while protecting it from concurrent changes.
        # History recovery and saving the selected run remain inside the same lock.
        with runs.RUNS_LOCK:
            candidates = [
                run
                for run in runs.RUNS.values()
                if (
                    run.get("saved_profile_id") == profile_id
                    or run["id"] == saved.get("source_run_id")
                )
                and run["id"] not in runs.DELETING
            ]
            if candidates:
                # Prefer an actual search over an unused profile-review workspace.
                existing = max(
                    candidates,
                    key=lambda run: (
                        run.get("phase", 0) >= 2,
                        run.get("created_at", 0),
                    ),
                )
                if existing["id"] not in runs.ACTIVE_WORKERS:
                    rows = existing.get("recommendations", []) + existing.get(
                        "excluded_recommendations", []
                    )
                    recovered = missing_journal_assessments(
                        runs.RUNS_DIR / existing["id"] / "job_assessments.jsonl", rows
                    )
                    if recovered:
                        # Snapshot backup allows rollback of legacy recovery.
                        backup = (
                            runs.RUNS_DIR
                            / existing["id"]
                            / "state.before-history-recovery.json"
                        )
                        if not backup.exists():
                            backup.write_text(json.dumps(existing), encoding="utf-8")
                        for row in recovered:
                            evaluation_service.upsert_assessment(existing["id"], row)
                        existing.update(
                            displayed_jobs=len(existing.get("recommendations", [])),
                            excluded_jobs=len(
                                existing.get("excluded_recommendations", [])
                            ),
                            excluded_reasons=evaluation_service.group_exclusion_reasons(
                                existing.get("excluded_recommendations", [])
                            ),
                            recommendations_found=sum(
                                bool(row.get("is_strong_fit"))
                                for row in existing.get("recommendations", [])
                            ),
                            evaluated_jobs=len(rows) + len(recovered),
                            evaluation_total=len(rows) + len(recovered),
                            message=f"Recovered {len(recovered)} previous jobs from this search history.",
                        )
                        export_jobs_excel(
                            existing.get("recommendations", []),
                            runs.RUNS_DIR / existing["id"] / "relevant_jobs.xlsx",
                        )
                existing.update(
                    saved_profile_id=profile_id, saved_profile_name=saved["name"]
                )
                runs.persist_run(existing["id"])
                return {"id": existing["id"], "runId": existing["id"]}
    run_id = uuid.uuid4().hex
    context = profile_to_context(ResumeProfile.model_validate(saved["profile"]))
    (runs.RUNS_DIR / run_id).mkdir(parents=True)
    try:
        storage.restore_resume(profile_id, runs.RUNS_DIR / run_id)
    except Exception:
        shutil.rmtree(runs.RUNS_DIR / run_id, ignore_errors=True)
        raise
    # Create the saved-profile workspace, its context, and its snapshot together.
    # Other lock-using requests wait until the new workspace is ready.
    with runs.RUNS_LOCK:
        runs.RUNS[run_id] = {
            "id": run_id,
            "created_at": time.time(),
            "status": "awaiting_search",
            "phase": 1,
            "phase_label": "Review saved profile",
            "profile": saved["profile"],
            "saved_profile_id": profile_id,
            "saved_profile_name": saved["name"],
            "preferences": saved["preferences"] or {},
            "recommendations": [],
            "excluded_recommendations": [],
            "message": "Review your profile and search preferences.",
        }
        runs.RUN_CONTEXTS[run_id] = context
        runs.run_context_path(run_id).write_text(context, encoding="utf-8")
        runs.persist_run(run_id)
    return {"id": run_id, "runId": run_id}


def evaluation_cache_directory(run_id):
    """Cache under the owning saved profile, or under the temporary run before saving."""
    with runs.RUNS_LOCK:
        profile_id = runs.RUNS.get(run_id, {}).get("saved_profile_id")
    if profile_id:
        with storage.LOCK:
            path = storage.profile_path(profile_id)
            if path.is_file():
                directory = path.with_suffix("")
                directory.mkdir(exist_ok=True)
                return directory / "evaluations"
    return runs.RUNS_DIR / run_id / "evaluations"
