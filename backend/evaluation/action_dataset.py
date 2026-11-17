"""Keep a labeled dataset of the jobs a user applied to or dismissed.

One dataset per saved profile (or per workspace without one), in the same layout and
format as the earlier review datasets: data/evaluation_datasets/<id>/dataset.json holds
the postings and reviews.json the labels. Applying is a strong match; dismissing for role
or seniority is not suitable; location, salary and other dismissals are preferences, so
they keep their action and reason but get no fit label. Undoing an action removes its label.
"""

import hashlib
import json
import os
import time
import uuid

from backend.paths import REVIEW_DATASETS_DIR

REVIEWER = "job action"
FIT_REASONS = {"role", "seniority"}
SENIORITY_WORDS = {"senior", "lead", "principal", "graduate", "junior"}


def posting_id(url, title, company, description):
    """The same posting ID the earlier review datasets used, so the two can be joined."""
    identity_url = url if url.startswith(("https://", "http://")) else ""
    return hashlib.sha256(
        (identity_url or (title + company + description)).encode()
    ).hexdigest()[:24]


def dataset_id(owner):
    return hashlib.sha256(f"job-actions:{owner}".encode()).hexdigest()[:32]


def _write(path, value):
    temporary = path.with_name("." + uuid.uuid4().hex + ".tmp")
    try:
        with os.fdopen(
            os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
        ) as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def label(flags, dismissal):
    """(fit, notes, tags) for the current action flags, or None when no action applies."""
    if flags.get("dismissed"):
        reason = (dismissal or {}).get("reason")
        fit = "not_suitable" if reason in FIT_REASONS else None
        return fit, f"Dismissed: {reason or 'no reason given'}", [
            "dismissed",
            f"dismissed_{reason or 'no_reason'}",
        ]
    if flags.get("applied"):
        return "strong_match", "Applied", ["applied"]
    return None


def _verdicts(assessments):
    complete = lambda item: item.get("status") == "complete"
    return {
        provider: dict(
            model=item.get("evaluation_model_id", ""),
            status=item.get("status", "unknown"),
            fit_category=item.get("fit_category") if complete(item) else None,
            score=item.get("score") if complete(item) else None,
        )
        for provider, item in (assessments or {}).items()
    }


def _job(row, action_tags):
    description = row.get("job_description") or ""
    title, url = row.get("title", ""), row.get("apply_url") or row.get("url") or ""
    assessments = row.get("model_evaluations") or {}
    tags = ["job_action", "previously_shortlisted", *action_tags]
    if any(word in title.lower().split() for word in SENIORITY_WORDS):
        tags.append("explicit_seniority_title")
    if len({a.get("fit_category") for a in assessments.values() if a.get("status") == "complete"}) > 1:
        tags.append("provider_disagreement")
    return dict(
        id=posting_id(url, title, row.get("company", ""), description),
        title=title,
        company=row.get("company", ""),
        url=url,
        description=description,
        previously_shortlisted=True,
        tags=tags,
        criteria=[],
        evidence=[],
        extraction_available=False,
        model_verdicts=_verdicts(assessments),
        app_verdict=row.get("fit_category"),
    )


def sync(run, owner, actions, feedback, rows_for_key):
    """Bring the owner's dataset in line with the current actions on this workspace's jobs.

    rows_for_key(key) returns the saved result row for an action key, or None for a job
    that is not in this workspace; such entries are left as they are.
    """
    from backend.cli import profile_to_context
    from backend.schemas.resume import ResumeProfile

    directory = REVIEW_DATASETS_DIR / dataset_id(owner)
    dataset = _read(directory / "dataset.json", None)
    reviews = _read(
        directory / "reviews.json",
        dict(revision=0, jobs={}, reviewers={}, updated_at=None),
    )
    jobs = {job["id"]: job for job in (dataset or {}).get("jobs", [])}
    changed = False
    for key, flags in actions.items():
        row = rows_for_key(key)
        if row is None or not (row.get("job_description") or "").strip():
            continue
        result = label(flags, feedback.get(key))
        job_id = _job(row, []).get("id")
        # Never overwrite a label someone made by hand.
        if reviews["reviewers"].get(job_id, REVIEWER) != REVIEWER:
            continue
        if result is None:
            if job_id in reviews["jobs"]:
                reviews["jobs"].pop(job_id)
                reviews["reviewers"].pop(job_id, None)
                if job_id in jobs:
                    jobs[job_id]["tags"] = [
                        tag for tag in jobs[job_id]["tags"]
                        if tag not in {"applied", "dismissed"} and not tag.startswith("dismissed_")
                    ]
                changed = True
            continue
        fit, notes, action_tags = result
        review = dict(
            fit=fit, ai_assisted=False, notes=notes, extraction_complete=False,
            criteria={}, missing_requirements=[], evidence={},
        )
        job = _job(row, action_tags)
        if reviews["jobs"].get(job_id) != review or jobs.get(job_id) != job:
            reviews["jobs"][job_id] = review
            reviews["reviewers"][job_id] = REVIEWER
            jobs[job_id] = job
            changed = True
    if not changed:
        return False
    profile = run.get("profile") or {}
    now = time.time()
    dataset = dict(
        id=dataset_id(owner),
        created_at=(dataset or {}).get("created_at", now),
        source_id=owner,
        # Not a frozen pool: the jobs change as actions do, so there is nothing to fingerprint.
        fingerprint="",
        scope="Jobs you applied to or dismissed",
        source="job_actions",
        split="pilot",
        profile=profile,
        profile_text=profile_to_context(ResumeProfile.model_validate(profile)) if profile else "",
        target_roles=list((run.get("preferences") or {}).get("queries") or []),
        jobs=list(jobs.values()),
        verdicts_added_at=None,
        ingestion=None,
        dropped_jobs=[],
    )
    reviews.update(revision=reviews["revision"] + 1, updated_at=now)
    directory.mkdir(parents=True, exist_ok=True)
    _write(directory / "dataset.json", dataset)
    _write(directory / "reviews.json", reviews)
    return True
