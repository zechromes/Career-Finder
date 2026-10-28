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
from backend.schemas.review_datasets import (
    ModelVerdict,
    ReviewBundle,
    ReviewDataset,
    ReviewState,
)

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


def _verdicts(assessments):
    return {
        provider: dict(
            model=assessment.get("evaluation_model_id", ""),
            status=assessment.get("status", "unknown"),
            fit_category=(
                assessment.get("fit_category")
                if assessment.get("status") == "complete"
                else None
            ),
            score=(
                assessment.get("score")
                if assessment.get("status") == "complete"
                else None
            ),
        )
        for provider, assessment in assessments.items()
    }


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
                model_verdicts=_verdicts(assessments),
                app_verdict=row.get("fit_category") if assessment_matches else None,
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


def add_verdicts(identifier):
    """Add saved verdicts to an older snapshot from its source workspace, once.

    A row is used only when its URL, title and company identify exactly one frozen
    job and its requirement verdicts are the ones frozen as evidence, so a newer
    assessment never lends its verdict. Labels are untouched."""
    with LOCK:
        bundle = read(identifier)
        dataset = bundle.dataset
        if dataset.verdicts_added_at or any(
            job.model_verdicts or job.app_verdict for job in dataset.jobs
        ):
            raise HTTPException(409, "This dataset already has model verdicts.")
        with runs.RUNS_LOCK:
            state = copy.deepcopy(runs.RUNS.get(dataset.source_id))
        if not state:
            raise HTTPException(404, "The source workspace is no longer available.")
        candidates = {}
        for row in state.get("recommendations", []) + state.get(
            "excluded_recommendations", []
        ):
            for url in {row.get("apply_url"), row.get("url")} - {None, ""}:
                key = (url, row.get("title", ""), row.get("company", ""))
                candidates.setdefault(key, []).append(row)
        # Identify the frozen assessment by its provider requirement verdicts.
        evidence = lambda rows: sorted(
            (provider, item.get("requirement", ""), item.get("verdict", "unknown"))
            for provider, assessment in rows.items()
            if assessment.get("status") == "complete"
            for item in assessment.get("requirement_verdicts", [])
        )
        matched = 0
        for job in dataset.jobs:
            found = candidates.get((job.url, job.title, job.company), [])
            if len(found) != 1:
                continue
            row = found[0]
            frozen = sorted(
                (item.provider, item.requirement, item.verdict) for item in job.evidence
            )
            if not frozen or frozen != evidence(row.get("model_evaluations", {})):
                continue
            matched += 1
            job.model_verdicts = {
                provider: ModelVerdict(**verdict)
                for provider, verdict in _verdicts(
                    row.get("model_evaluations", {})
                ).items()
            }
            job.app_verdict = row.get("fit_category")
        if not matched:
            raise HTTPException(
                422, "No saved verdicts match this dataset; it was left unchanged."
            )
        dataset.verdicts_added_at = time.time()
        _write(_path(identifier) / "dataset.json", dataset.model_dump())
        return dict(
            matched=matched,
            shortlisted=sum(job.previously_shortlisted for job in dataset.jobs),
        )


def delete(identifier):
    # Remove the frozen evidence and its reviews; source workspaces are unaffected.
    with LOCK:
        path = _path(identifier)
        if not (path / "dataset.json").is_file():
            raise HTTPException(404, "Review dataset not found.")
        shutil.rmtree(path)
        return {"deleted": True}


def _generation(model, pairs):
    """Compare (human_fit, model_verdict_or_None_if_failed) pairs for binary-labeled jobs."""
    counts = {"strong_match": {}, "not_suitable": {}}
    failed, rejected = 0, []
    for job_id, human, verdict in pairs:
        if verdict is None:
            failed += 1
            continue
        bucket = counts[human]
        bucket[verdict] = bucket.get(verdict, 0) + 1
        if human == "strong_match" and verdict == "not_suitable":
            rejected.append(job_id)
    good, bad = counts["strong_match"], counts["not_suitable"]
    true_strong, false_strong = good.get("strong_match", 0), bad.get("strong_match", 0)
    good_total = sum(good.values())
    return dict(
        model=model,
        assessed=good_total + sum(bad.values()),
        failed=failed,
        human_good=good,
        human_not_fit=bad,
        strong_match_precision=(
            true_strong / (true_strong + false_strong)
            if true_strong + false_strong
            else None
        ),
        good_fit_recall=true_strong / good_total if good_total else None,
        good_fits_rejected=rejected,
    )


def _stages(data, labels):
    """Trace each human good fit through retrieval and generation."""
    from backend.evaluation.candidate_fit import title_exceeds_candidate_level

    profile = data.profile.model_dump()
    binary = {
        job.id: (job, labels[job.id].fit)
        for job in data.jobs
        if job.id in labels
        and labels[job.id].fit in {"strong_match", "not_suitable"}
    }
    good = [job for job, fit in binary.values() if fit == "strong_match"]
    shortlisted = [job for job in good if job.previously_shortlisted]
    outcome = lambda verdict: sum(job.app_verdict == verdict for job in shortlisted)
    providers = sorted({p for job, _ in binary.values() for p in job.model_verdicts})
    generation = {}
    for provider in providers:
        pairs, model = [], ""
        for job, fit in binary.values():
            verdict = job.model_verdicts.get(provider)
            if not verdict:
                continue
            model = model or verdict.model
            complete = verdict.status == "complete" and verdict.fit_category
            pairs.append((job.id, fit, verdict.fit_category if complete else None))
        generation[provider] = _generation(model, pairs)
    app_pairs = [
        (job.id, fit, job.app_verdict)
        for job, fit in binary.values()
        if job.previously_shortlisted and job.app_verdict
    ]
    return dict(
        verdicts_available=any(job.app_verdict for job in data.jobs),
        funnel=dict(
            good_fits=len(good),
            lost_at_retrieval=len(good) - len(shortlisted),
            not_assessed=sum(job.app_verdict is None for job in shortlisted),
            rejected_at_generation=outcome("not_suitable"),
            needs_review=outcome("review"),
            recommended=outcome("strong_match"),
        ),
        retrieval_missed=[
            dict(
                id=job.id,
                title=job.title,
                experienced_title=title_exceeds_candidate_level(
                    job.title, data.profile_text, profile
                ),
            )
            for job in good
            if not job.previously_shortlisted
        ],
        generation=generation,
        app=_generation("Combined app verdict", app_pairs) if app_pairs else None,
    )


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
        stages=_stages(data, labels),
        limitations=[
            "Single-profile pilot, not a held-out benchmark.",
            "Partial labels yield observed metrics only.",
            "Shared extraction metrics exclude legacy provider-defined criteria.",
            "Quote presence does not prove semantic support.",
            "AI-assisted reviews are excluded from every metric.",
            "Generation metrics cover only shortlisted jobs, which were the only ones assessed.",
            "Ingestion losses are not tracked yet.",
        ],
    )
