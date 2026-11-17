"""Evaluate with every available provider, preserving independent results and retry identity."""

from backend.observability import stage, submit, mark
import copy
import hashlib
from concurrent.futures import ThreadPoolExecutor, wait
from threading import RLock
from langchain_core.documents import Document
from backend.evaluation.providers import (
    evaluate_jobs as evaluate_provider,
    UNUSABLE,
    check_availability,
    evaluation_model_options,
    mark_unavailable,
)
from backend.evaluation.runtime import classify_failure, EvaluationFailure


# Keep the same job identity when independent provider results arrive.
def identity(job):
    return (
        job.get("apply_url")
        or job.get("jobId")
        or (job.get("title", "") + "|" + job.get("company", ""))
    )


NAMES = {"claude": "Claude", "gpt": "GPT", "gemini": "Gemini"}
AVAILABILITY_CHECK_SECONDS = 20


# Require an assessment from every model the job was sent to; disagreement
# remains review. A model skipped as unavailable keeps a retryable row but does
# not count until a retry completes it.
def summarize(job):
    result = copy.deepcopy(job)
    assessments = result.get("model_evaluations", {})
    used = [
        key
        for key in NAMES
        if key in assessments and assessments[key].get("status") != "skipped"
    ]
    required = len(used)
    complete = [row for row in assessments.values() if row.get("status") == "complete"]
    set_ids = {row.get("requirement_set_id", "") for row in complete}
    compatible = len(set_ids) <= 1
    all_complete = required > 0 and len(complete) == required and compatible
    categories = {row.get("fit_category", "review") for row in complete}
    result["fit_category"] = (
        next(iter(categories)) if all_complete and len(categories) == 1 else "review"
    )
    scores = [row["score"] for row in complete if row.get("score") is not None]
    result["score"] = (
        round(sum(scores) / required)
        if all_complete and len(scores) == required
        else None
    )
    # Expose available agreement without replacing the conservative final verdict.
    result["completed_models"] = len(complete)
    counts = {
        category: sum(row.get("fit_category", "review") == category for row in complete)
        for category in categories
    }
    result["agreement_count"] = max(counts.values(), default=0)
    result["provisional_score"] = (
        round(sum(scores) / len(scores))
        if len(scores) >= 2 and not all_complete and compatible
        else None
    )
    result["assessment_summary"] = (
        f"{len(complete)}/{required} models complete; {result['agreement_count']}/{len(complete)} completed verdicts agree."
        if complete
        else "Waiting for model assessments."
    )
    if result["provisional_score"] is not None:
        result[
            "assessment_summary"
        ] += f" Provisional average: {result['provisional_score']}/100. Not a final verdict or confidence estimate."
    if not compatible:
        result[
            "assessment_summary"
        ] += " Assessments use different requirement lists; no combined score is shown. Start a new search to compare the same criteria."
    result["is_strong_fit"] = result["fit_category"] == "strong_match"
    result["score_method"] = (
        "three-model-average-v1" if required == 3 else f"{required}-model-average-v1"
    )
    result["evaluation_provider"] = "all"
    result["evaluation_model_id"] = " + ".join(NAMES[key] for key in used)
    everyone = "The model" if required == 1 else f"All {required} models"
    result["rationale"] = (
        (
            "Only one model was available; this is its verdict."
            if required == 1
            else f"{everyone} agree on the verdict."
        )
        if all_complete and len(categories) == 1
        else (
            "Models disagree; compare their assessments below."
            if all_complete
            else "Model assessments are incomplete. Review the available results below."
        )
    )
    if not compatible:
        result["rationale"] = (
            "Assessments use different requirement lists. Review individual results or start a new search."
        )
    result["mismatch_reason"] = (
        f"{everyone} marked this job not recommended."
        if result["fit_category"] == "not_suitable"
        else ""
    )
    result["missing_skills"] = sorted(
        {skill for row in complete for skill in row.get("missing_skills", [])}
    )
    result["requirement_verdicts"] = []  # Evidence belongs to its individual model.
    return result


# Merge provider progress without replacing an existing assessment with pending state.
def merge_result(existing, incoming):
    if not incoming.get("model_evaluations"):
        return incoming
    merged = {**existing, **incoming}
    rows = copy.deepcopy(existing.get("model_evaluations", {}))
    # A pending or skipped row never replaces an earlier assessment.
    for provider, row in incoming["model_evaluations"].items():
        if row.get("status") not in {"pending", "skipped"} or provider not in rows:
            rows[provider] = row
    merged["model_evaluations"] = rows
    return summarize(merged)


@stage("evaluation.all_providers")
def evaluate_jobs(
    resume_context,
    jobs,
    include_all=False,
    target_roles=None,
    on_progress=None,
    on_result=None,
    provider=None,
    candidate_profile=None,
    on_error=None,
    should_cancel=None,
    cache_directory=None,
    on_unavailable=None,
):
    """The web flow uses every available model; tagged retry documents use only that model.

    A model that cannot evaluate (quota or spend cap, credentials, model access)
    is skipped and reported through on_unavailable instead of failing every job.
    """
    from backend.evaluation.requirements import RequirementLoader

    requirement_loader = RequirementLoader(should_cancel or (lambda: False))
    configured = {item["value"]: item for item in evaluation_model_options()}
    options = [configured[key] for key in ("claude", "gpt", "gemini")]
    if should_cancel and should_cancel():
        options = []
    # A retry checks only the models it would call. The retry service clears their
    # cached answers first, so a model whose quota was restored is used again.
    retry = bool(jobs) and all("_evaluation_provider" in doc.metadata for doc in jobs)
    if retry:
        needed = {doc.metadata["_evaluation_provider"] for doc in jobs}
        options = [item for item in options if item["value"] in needed]
    # A slow provider counts as available rather than delaying the search.
    executor = ThreadPoolExecutor(max_workers=3)
    futures = [executor.submit(check_availability, item["value"]) for item in options]
    wait(futures, timeout=AVAILABILITY_CHECK_SECONDS)
    executor.shutdown(wait=False)
    checks = [future.result() if future.done() else None for future in futures]
    # With no model available, a new search evaluates anyway so each failure is
    # recorded; a retry never re-sends to a model that is still unavailable.
    skipped = []
    if retry or not all(checks):
        skipped = [(item, failure) for item, failure in zip(options, checks) if failure]
        for item, failure in skipped:
            if on_unavailable:
                on_unavailable(item, failure)
        options = [item for item, failure in zip(options, checks) if not failure]
    by_key = {}
    lock = RLock()
    failures = 0
    for rank, doc in enumerate(jobs):
        key = str(
            doc.metadata.get("url")
            or (doc.metadata.get("title", "") + doc.metadata.get("company", ""))
        )
        if key in by_key:
            continue
        by_key[key] = {
            "jobId": hashlib.sha256(key.encode()).hexdigest()[:24],
            "apply_url": doc.metadata.get("url", ""),
            "title": doc.metadata.get("title", ""),
            "company": doc.metadata.get("company", ""),
            "location": doc.metadata.get("location", ""),
            "source": doc.metadata.get("source", ""),
            "posted_at": doc.metadata.get("posted_at", ""),
            "company_logo": doc.metadata.get("company_logo", ""),
            "job_description": doc.metadata.get("job_description", ""),
            # Shortlist position orders jobs with the same verdict; a retry keeps
            # the original position by not sending one.
            **(
                {}
                if "_evaluation_provider" in doc.metadata
                else {"shortlist_rank": rank}
            ),
            "description_available": bool(
                doc.metadata.get("job_description", "").strip()
            ),
            "model_evaluations": {
                item["value"]: {
                    "provider": item["value"],
                    "evaluation_model_id": item["model_id"],
                    "status": "pending",
                }
                for item in options
            },
        }
        # A skipped row is saved with the failed jobs, so a later retry can fill it.
        for item, failure in skipped:
            by_key[key]["model_evaluations"][item["value"]] = {
                "provider": item["value"],
                "evaluation_model_id": item["model_id"],
                "status": "skipped",
                "error": str(failure),
            }

    # Resolve the posting key used to join this batch’s provider assessments.
    def key_for(doc):
        return str(
            doc.metadata.get("url")
            or (doc.metadata.get("title", "") + doc.metadata.get("company", ""))
        )

    # Publish a combined snapshot while serializing concurrent provider callbacks.
    def publish(key):
        if on_result:
            on_result(summarize(by_key[key]))
        if on_progress:
            done = sum(
                all(
                    row["status"] != "pending"
                    for row in job["model_evaluations"].values()
                )
                for job in by_key.values()
            )
            on_progress(done, failures, len(by_key))

    # Publish the shortlist before waiting for any remote assessment. Callbacks
    # are serialized with subsequent results, including persistence callbacks.
    with lock:
        initial_keys = {
            key_for(doc) for doc in jobs if "_evaluation_provider" not in doc.metadata
        }
        for key in by_key:
            if should_cancel and should_cancel():
                break
            if key in initial_keys:
                publish(key)

    # Run one provider batch with callbacks bound to that provider.
    @stage("evaluation.provider_batch")
    def evaluate_batch(option):
        if should_cancel and should_cancel():
            return
        current = option["value"]
        documents = {
            key_for(doc): doc
            for doc in jobs
            if doc.metadata.get("_evaluation_provider", current) == current
        }
        settled = set()
        blocked = [None]

        # Merge a completed assessment into the matching job’s provider results.
        def success(result):
            with lock:
                if should_cancel and should_cancel():
                    return
                key = next(
                    (
                        key
                        for key, doc in documents.items()
                        if (
                            result.get("jobId")
                            and by_key[key]["jobId"] == result["jobId"]
                        )
                        or (
                            doc.metadata.get("url")
                            and doc.metadata["url"] == result.get("apply_url")
                        )
                        or (
                            not doc.metadata.get("url")
                            and doc.metadata.get("title", "") == result.get("title", "")
                            and doc.metadata.get("company", "")
                            == result.get("company", "")
                        )
                    ),
                    None,
                )
                if key is None:
                    return
                if key in settled:
                    return
                settled.add(key)
                by_key[key]["model_evaluations"][current] = {
                    **result,
                    "provider": current,
                    "status": "complete",
                }
                # Keep the original Claude, GPT, Gemini metadata preference even
                # when provider responses finish in a different order.
                for field in (
                    "about_company",
                    "candidate_requirements",
                    "salary",
                    "work_type",
                ):
                    value = None
                    for item in options:
                        assessment = by_key[key]["model_evaluations"][item["value"]]
                        if (
                            assessment.get("status") == "complete"
                            and assessment.get(field) is not None
                        ):
                            value = assessment[field]
                            if value:
                                break
                    if value is not None:
                        by_key[key][field] = value
                publish(key)

        # Record a failed assessment while retaining other providers’ completed work.
        def failure(doc, error):
            mark("partial")
            nonlocal failures
            with lock:
                if should_cancel and should_cancel():
                    return
                key = key_for(doc)
                if key in settled:
                    return
                settled.add(key)
                failures += 1
                if getattr(error, "category", "") in {
                    "quota",
                    "credentials",
                    "model",
                    "request",
                    "rate_limit",
                }:
                    blocked[0] = error
                if getattr(error, "category", "") in UNUSABLE:
                    # Skip this model in the next search without another check.
                    mark_unavailable(current, error)
                by_key[key]["model_evaluations"][current] = {
                    "provider": current,
                    "evaluation_model_id": option["model_id"],
                    "status": "failed",
                    "error": str(error),
                }
                if on_error:
                    on_error(
                        Document(
                            page_content=doc.page_content,
                            metadata={**doc.metadata, "_evaluation_provider": current},
                        ),
                        error,
                    )
                publish(key)

        if not documents:
            return
        try:
            pending = list(documents.values())
            # Prioritize the first 15 for each provider without skipping other models.
            for start in range(0, len(pending), 15):
                if should_cancel and should_cancel():
                    return
                wave = pending[start : start + 15]
                kwargs = (
                    {"cache_directory": cache_directory}
                    if cache_directory is not None
                    else {}
                )
                evaluate_provider(
                    resume_context,
                    wave,
                    include_all=True,
                    target_roles=target_roles,
                    provider=current,
                    candidate_profile=candidate_profile,
                    requirement_loader=requirement_loader,
                    on_result=success,
                    on_error=failure,
                    should_cancel=should_cancel,
                    **kwargs,
                )
                # Configuration, quota and exhausted rate limits stop later waves.
                if any(
                    by_key[key_for(doc)]["model_evaluations"][current].get("status")
                    == "failed"
                    for doc in wave
                ):
                    # Keep these failures retryable without submitting another wave now.
                    if blocked[0]:
                        for doc in pending[start + 15 :]:
                            failure(
                                doc,
                                EvaluationFailure(
                                    blocked[0].category, str(blocked[0]), skipped=True
                                ),
                            )
                        break

        except Exception as exc:
            if should_cancel and should_cancel():
                return
            for key, doc in documents.items():
                if key not in settled:
                    failure(doc, classify_failure(exc))

    # Each provider retains its own bounded request pool and rate policy.
    # Overlap providers without increasing any individual provider limit.
    with ThreadPoolExecutor(
        max_workers=max(1, len(options)), thread_name_prefix="evaluation-provider"
    ) as executor:
        futures = [submit(executor, evaluate_batch, option) for option in options]
        for future in futures:
            future.result()
    results = [summarize(job) for job in by_key.values()]
    return results if include_all else [job for job in results if job["is_strong_fit"]]
