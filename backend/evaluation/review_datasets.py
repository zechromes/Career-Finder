"""Persistent review snapshots and human-only quality measurements. No provider calls."""

import copy
import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from backend import runs
from backend.paths import REVIEW_DATASETS_DIR
from backend.evaluation import experiments
from backend.evaluation.evidence import quoted
from backend.schemas.review_datasets import ReviewDataset, ReviewState, ReviewBundle

LOCK = threading.RLock()


def _path(identifier):
    if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
        raise HTTPException(404, "Review dataset not found.")
    return REVIEW_DATASETS_DIR / identifier


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


def read(identifier):
    with LOCK:
        path = _path(identifier)
        if not (path / "dataset.json").is_file():
            raise HTTPException(404, "Review dataset not found.")
        return ReviewBundle(
            dataset=ReviewDataset.model_validate_json(
                (path / "dataset.json").read_text()
            ),
            labels=ReviewState.model_validate_json((path / "reviews.json").read_text()),
        )


def summaries():
    with LOCK:
        result = []
        for path in REVIEW_DATASETS_DIR.glob("*/dataset.json"):
            value = read(path.parent.name)
            result.append(
                dict(
                    id=value.dataset.id,
                    created_at=value.dataset.created_at,
                    job_count=len(value.dataset.jobs),
                    outside_shortlist=sum(
                        not job.previously_shortlisted for job in value.dataset.jobs
                    ),
                    reviewed_jobs=sum(
                        job.fit is not None for job in value.labels.jobs.values()
                    ),
                )
            )
        return sorted(result, key=lambda row: row["created_at"], reverse=True)


def _identity(row):
    return (
        row.get("apply_url") or row.get("url") or "",
        row.get("title", ""),
        row.get("company", ""),
    )


def create(source_id):
    from backend.cli import profile_to_context
    from backend.schemas.resume import ResumeProfile

    # Freeze pool and assessments under the same workspace lock.
    with runs.RUNS_LOCK:
        public, profile, roles, docs = experiments.dataset(source_id)
        state = copy.deepcopy(runs.RUNS[source_id])
    resume_text = profile_to_context(ResumeProfile.model_validate(profile))
    saved_rows = state.get("recommendations", []) + state.get(
        "excluded_recommendations", []
    )
    saved = {_identity(row): row for row in saved_rows}
    jobs = []
    for key, doc in docs.items():
        row = saved.get(_identity(doc.metadata))
        # Do not attach an assessment to a newer posting version by URL alone.
        assessment_matches = (
            row
            and row.get("job_description", "").strip()
            == doc.metadata.get("job_description", "").strip()
        )
        assessments = row.get("model_evaluations", {}) if assessment_matches else {}
        criteria, evidence, seen = [], [], set()
        shared = False
        for provider, assessment in assessments.items():
            if assessment.get("status") != "complete":
                continue
            is_shared = bool(assessment.get("requirement_set_id"))
            shared |= is_shared
            for index, item in enumerate(assessment.get("requirement_verdicts", [])):
                canonical = {
                    field: item.get(field, "")
                    for field in ["requirement", "importance", "job_quote", "section"]
                }
                identity = json.dumps(
                    [assessment.get("requirement_set_id") or provider, canonical],
                    sort_keys=True,
                )
                criterion_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
                if criterion_id not in seen:
                    seen.add(criterion_id)
                    criteria.append(
                        dict(
                            id=criterion_id,
                            **canonical,
                            origin=(
                                "shared_extractor" if is_shared else "legacy_provider"
                            ),
                            extraction_model=assessment.get(
                                "requirement_extraction_model", ""
                            ),
                            extraction_version=assessment.get(
                                "requirement_extraction_version", ""
                            ),
                            set_id=assessment.get("requirement_set_id", ""),
                        )
                    )
                evidence.append(
                    dict(
                        id=f"{provider}-{index}",
                        provider=provider,
                        model=assessment.get("evaluation_model_id", ""),
                        requirement=item.get("requirement", ""),
                        verdict=item.get("verdict", "unknown"),
                        job_quote=item.get("job_quote", ""),
                        resume_quote=item.get("resume_quote", ""),
                        explanation=item.get("explanation", ""),
                        job_quote_found=quoted(
                            item.get("job_quote", ""), doc.page_content
                        ),
                        profile_quote_found=quoted(
                            item.get("resume_quote", ""), resume_text
                        ),
                    )
                )
        tags = ["previously_shortlisted" if row else "outside_shortlist"]
        if not evidence:
            tags.append(
                "no_saved_assessment"
                if not row
                else "assessment_unavailable_or_posting_changed"
            )
        if any(
            word in doc.metadata.get("title", "").lower().split()
            for word in ["senior", "lead", "principal", "graduate", "junior"]
        ):
            tags.append("explicit_seniority_title")
        if (
            len(
                {
                    assessment.get("fit_category")
                    for assessment in assessments.values()
                    if assessment.get("status") == "complete"
                }
            )
            > 1
        ):
            tags.append("provider_disagreement")
        jobs.append(
            dict(
                id=key,
                title=doc.metadata.get("title", ""),
                company=doc.metadata.get("company", ""),
                url=doc.metadata.get("url", ""),
                description=doc.page_content,
                previously_shortlisted=bool(row),
                tags=tags,
                criteria=criteria,
                evidence=evidence,
                extraction_available=shared,
            )
        )
    dataset = ReviewDataset(
        id=uuid.uuid4().hex,
        created_at=time.time(),
        source_id=source_id,
        fingerprint=public.fingerprint,
        scope=public.scope,
        profile=profile,
        profile_text=resume_text,
        target_roles=roles,
        jobs=jobs,
    )
    with LOCK:
        path = _path(dataset.id)
        path.mkdir(parents=True, mode=0o700)
        _write(path / "reviews.json", ReviewState().model_dump())
        _write(path / "dataset.json", dataset.model_dump())
    return read(dataset.id)


def save(identifier, job_id, body):
    with LOCK:
        bundle = read(identifier)
        if body.revision != bundle.labels.revision:
            raise HTTPException(
                409, "Reviews changed in another tab. Reload before saving."
            )
        job = next((job for job in bundle.dataset.jobs if job.id == job_id), None)
        if not job:
            raise HTTPException(404, "Job not in this dataset.")
        if not body.reviewer.strip():
            raise HTTPException(422, "Enter a reviewer name or initials.")
        review = body.review
        if set(review.criteria) - {row.id for row in job.criteria} or set(
            review.evidence
        ) - {row.id for row in job.evidence}:
            raise HTTPException(422, "Review refers to unknown criteria or evidence.")
        for item in review.missing_requirements:
            if not item.requirement.strip() or not quoted(
                item.job_quote, job.description
            ):
                raise HTTPException(
                    422, "Every added requirement needs an exact posting quote."
                )
        shared_rows = [row for row in job.criteria if row.origin == "shared_extractor"]
        if review.extraction_complete and (
            not shared_rows
            or any(
                review.criteria.get(row.id) is None
                or review.criteria[row.id].correct is None
                for row in shared_rows
            )
        ):
            raise HTTPException(
                422, "Review every shared criterion before marking extraction complete."
            )
        bundle.labels.jobs[job_id] = review
        bundle.labels.reviewers[job_id] = body.reviewer.strip()
        bundle.labels.revision += 1
        bundle.labels.updated_at = time.time()
        _write(_path(identifier) / "reviews.json", bundle.labels.model_dump())
        return bundle.labels


def delete(identifier):
    # Remove the frozen evidence and its reviews; source workspaces are unaffected.
    with LOCK:
        path = _path(identifier)
        if not (path / "dataset.json").is_file():
            raise HTTPException(404, "Review dataset not found.")
        shutil.rmtree(path)
        return {"deleted": True}


def measure(identifier):
    """Report only explicitly human-reviewed judgments; unknowns are not negatives."""
    bundle = read(identifier)
    data = bundle.dataset
    labels = {
        key: review
        for key, review in bundle.labels.jobs.items()
        if not review.ai_assisted
    }
    fit = {
        key: review.fit == "strong_match"
        for key, review in labels.items()
        if review.fit in {"strong_match", "not_suitable"}
    }
    shortlist = [job.id for job in data.jobs if job.previously_shortlisted]
    retrieval = experiments.metrics(fit, [job.id for job in data.jobs], shortlist)
    correct = incorrect = importance_right = importance_total = complete_correct = (
        missing
    ) = complete_jobs = 0
    extraction_total = extraction_reviewed = 0
    providers = {}
    for job in data.jobs:
        review = labels.get(job.id)
        shared_rows = [row for row in job.criteria if row.origin == "shared_extractor"]
        extraction_total += len(shared_rows)
        if review:
            for row in shared_rows:
                human = review.criteria.get(row.id)
                if human and human.correct is not None:
                    extraction_reviewed += 1
                    correct += int(human.correct)
                    incorrect += int(not human.correct)
                    if human.correct and human.importance:
                        importance_total += 1
                        importance_right += int(human.importance == row.importance)
            if review.extraction_complete and shared_rows:
                complete_jobs += 1
                complete_correct += sum(
                    review.criteria[row.id].correct is True for row in shared_rows
                )
                missing += len(review.missing_requirements)
        for row in job.evidence:
            key = row.provider + ":" + row.model
            counts = providers.setdefault(
                key,
                dict(
                    total=0,
                    reviewed=0,
                    supported=0,
                    unsupported=0,
                    uncertain=0,
                    verdict_reviewed=0,
                    verdict_correct=0,
                    quotes_found=0,
                ),
            )
            counts["total"] += 1
            counts["quotes_found"] += int(
                row.job_quote_found and row.profile_quote_found
            )
            human = review.evidence.get(row.id) if review else None
            if human and human.support:
                counts["reviewed"] += 1
                counts[human.support] += 1
            if human and human.verdict:
                counts["verdict_reviewed"] += 1
                counts["verdict_correct"] += int(human.verdict == row.verdict)
    ratio = lambda numerator, denominator: (
        numerator / denominator if denominator else None
    )
    for counts in providers.values():
        counts.update(
            review_coverage=ratio(counts["reviewed"], counts["total"]),
            support_rate=ratio(
                counts["supported"], counts["supported"] + counts["unsupported"]
            ),
            verdict_accuracy=ratio(
                counts["verdict_correct"], counts["verdict_reviewed"]
            ),
        )
    return dict(
        dataset_id=identifier,
        revision=bundle.labels.revision,
        split=data.split,
        pool_size=len(data.jobs),
        fit_reviewed=sum(review.fit is not None for review in labels.values()),
        ai_assisted_reviews=len(bundle.labels.jobs) - len(labels),
        retrieval=retrieval,
        extraction=dict(
            total=extraction_total,
            reviewed=extraction_reviewed,
            precision=ratio(correct, correct + incorrect),
            importance_accuracy=ratio(importance_right, importance_total),
            completeness_reviewed_jobs=complete_jobs,
            missed_requirements=missing,
            recall_on_complete_reviews=ratio(
                complete_correct, complete_correct + missing
            ),
        ),
        evidence=providers,
        limitations=[
            "Single-profile pilot, not a held-out benchmark.",
            "Partial labels yield observed metrics only.",
            "Shared extraction metrics exclude legacy provider-defined criteria.",
            "Quote presence does not prove semantic support.",
            "AI-assisted reviews are excluded from every metric.",
        ],
    )
