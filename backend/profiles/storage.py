"""Persistent, explicitly saved profiles, independent of temporary search runs."""

import shutil
import json
import threading
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse
from backend.paths import PROJECT_ROOT
from backend.schemas.resume import ResumeProfile
from backend.schemas.contracts import Preferences

PROFILES_DIR = PROJECT_ROOT / "data" / "profiles"
LOCK = threading.RLock()


# Validate editable profile fields separately from storage metadata.
from backend.schemas.saved_profiles import SavedProfileInput  # Compatibility export.


# Add persisted identity, timestamps, and attachment availability to a saved profile.
from backend.schemas.saved_profiles import SavedProfile  # Compatibility export.


# Validate the opaque profile identifier before constructing a storage path.
def profile_path(profile_id: str) -> Path:
    if len(profile_id) != 32 or any(c not in "0123456789abcdef" for c in profile_id):
        raise HTTPException(404, "Profile not found.")
    return PROFILES_DIR / f"{profile_id}.json"


# Load and validate saved profile data while holding the profile storage lock.
def read_profile(profile_id: str):
    path = profile_path(profile_id)
    with LOCK:
        if not path.is_file():
            raise HTTPException(404, "Profile not found.")
        return SavedProfile.model_validate_json(
            path.read_text(encoding="utf-8")
        ).model_dump()


# Atomically replace profile metadata and refresh the saved resume context when available.
def write_profile(data):
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = profile_path(data["id"])
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temporary.replace(path)
    if data.get("resume_available"):
        from backend.cli import profile_to_context

        (path.with_suffix("") / "resume_context.txt").write_text(
            profile_to_context(ResumeProfile.model_validate(data["profile"])),
            encoding="utf-8",
        )
    return data


# Return saved profiles in most recently updated order for the profile picker.
def list_profiles():
    with LOCK:
        return sorted(
            [read_profile(path.stem) for path in PROFILES_DIR.glob("*.json")],
            key=lambda item: item["updated_at"],
            reverse=True,
        )


# Persist an independent profile, copying the source PDF when a source run is supplied.
def create_profile(body: SavedProfileInput):
    with LOCK:
        now = time.time()
        profile_id = uuid.uuid4().hex
        data = dict(
            body.model_dump(),
            id=profile_id,
            created_at=now,
            updated_at=now,
            resume_available=False,
        )
        if body.source_run_id:
            from backend import runs

            # Protect the source run while copying its PDF and linking the saved profile.
            # Run deletion using this lock must wait until that work has finished.
            with runs.RUNS_LOCK:
                source = runs.RUNS_DIR / body.source_run_id / "resume.pdf"
                if not source.is_file():
                    raise HTTPException(
                        409,
                        "The original resume is unavailable. Upload it again to save a complete resume workspace.",
                    )
                destination = profile_path(profile_id).with_suffix("")
                destination.mkdir(parents=True)
                try:
                    shutil.copy2(source, destination / "resume.pdf")
                    from backend.cli import profile_to_context

                    (destination / "resume_context.txt").write_text(
                        profile_to_context(body.profile), encoding="utf-8"
                    )
                    data["resume_available"] = True
                    cached = runs.RUNS_DIR / body.source_run_id / "evaluations"
                    if cached.is_dir():
                        shutil.copytree(
                            cached, destination / "evaluations", dirs_exist_ok=True
                        )
                    data["job_actions"] = runs.RUNS.get(body.source_run_id, {}).get(
                        "job_actions", {}
                    )
                    data["dismissal_feedback"] = runs.RUNS.get(
                        body.source_run_id, {}
                    ).get("dismissal_feedback", {})
                    saved = write_profile(data)
                    if body.source_run_id in runs.RUNS:
                        runs.RUNS[body.source_run_id].update(
                            saved_profile_id=profile_id, saved_profile_name=body.name
                        )
                        runs.persist_run(body.source_run_id)
                    return saved
                except Exception:
                    shutil.rmtree(destination, ignore_errors=True)
                    raise
        return write_profile(data)


# Keep the original resume attachment and creation date when saving profile edits.
def update_profile(profile_id: str, body: SavedProfileInput):
    with LOCK:
        previous = read_profile(profile_id)
        return write_profile(
            dict(
                body.model_dump(),
                job_actions=previous.get("job_actions", {}),
                dismissal_feedback=previous.get("dismissal_feedback", {}),
                source_run_id=previous.get("source_run_id"),
                resume_available=previous["resume_available"],
                id=profile_id,
                created_at=previous["created_at"],
                updated_at=time.time(),
            )
        )


# Remove this saved profile and its attachment without deleting search runs.
def delete_profile(profile_id: str):
    with LOCK:
        read_profile(profile_id)
        profile_path(profile_id).unlink()
        shutil.rmtree(profile_path(profile_id).with_suffix(""), ignore_errors=True)
    return {"deleted": True}


# Serve the saved PDF only when its independent attachment still exists.
def download_resume(profile_id: str):
    read_profile(profile_id)
    path = profile_path(profile_id).with_suffix("") / "resume.pdf"
    if not path.is_file():
        raise HTTPException(404, "This older saved profile has no original resume.")
    return FileResponse(path, filename="resume.pdf", media_type="application/pdf")


# Copy an available saved PDF into a new search workspace.
def restore_resume(profile_id: str, destination: Path):
    with LOCK:
        saved = read_profile(profile_id)
        source = profile_path(profile_id).with_suffix("") / "resume.pdf"
        if saved["resume_available"]:
            if not source.is_file():
                raise HTTPException(
                    409, "The saved resume file is missing. Upload the resume again."
                )
            shutil.copy2(source, destination / "resume.pdf")


# Preserve legacy imports; route declarations live in backend.routers.profiles.
from backend.routers.profiles import build_router
import sys

router = build_router(sys.modules[__name__])
