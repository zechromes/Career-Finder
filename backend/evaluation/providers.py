"""Provider models, structured assessments, and bounded request execution."""

from backend.observability import stage, submit, mark
from backend.evaluation.telemetry import model_request, streaming_options
from backend.evaluation.structured_output import (
    required_output_schema,
    validate_assessment_response,
)
from backend.schemas.evaluation import RequirementVerdict
from backend.evaluation.evidence import score_requirements
import os
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional
from backend.evaluation.candidate_fit import RECRUITER_PROMPT, enforce_experience_fit
from backend.evaluation.runtime import (
    EvaluationFailure,
    GeminiRequestPolicy,
    classify_failure,
    shared_pacer,
    retry_invalid_assessment,
)

EVALUATION_DEFAULTS = {
    "gemini": "gemini-4-argon",
    "claude": "claude-sonnet-5-5",
    "gpt": "gpt-6.1-sol",
}


# Resolve the provider model override without changing provider identity.
def evaluation_model_id(provider):
    if provider not in EVALUATION_DEFAULTS:
        raise ValueError("Evaluation provider must be gemini, claude or gpt.")
    return (
        os.getenv(f"{provider.upper()}_EVALUATION_MODEL")
        or EVALUATION_DEFAULTS[provider]
    )


# Expose provider labels and configured model IDs to the interface.
def evaluation_model_options():
    names = {
        "claude": "Anthropic Claude",
        "gpt": "OpenAI GPT",
        "gemini": "Google Gemini",
    }
    return [
        {
            "value": provider,
            "label": f"{names[provider]} · {evaluation_model_id(provider)}",
            "model_id": evaluation_model_id(provider),
        }
        for provider in EVALUATION_DEFAULTS
    ]


# Validate one provider’s assessment before deterministic scoring and result merging.
from backend.schemas.evaluation import JobEvaluation  # Compatibility export.


def _evaluate_concurrently(
    jobs, evaluate_one, workers, on_progress=None, on_result=None, on_error=None
):
    """Overlap network waits, isolate failures, and preserve semantic order.

    Progress callbacks run on the coordinating thread, so callers can safely
    persist counters without concurrent callbacks overwriting one another.
    """
    results = [None] * len(jobs)
    successful = failed = 0
    if not jobs:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as executor:
        pending = {
            submit(executor, evaluate_one, job): index for index, job in enumerate(jobs)
        }
        for future in as_completed(pending):
            index = pending[future]
            try:
                results[index] = future.result()
                successful += 1
            except Exception as exc:
                failed += 1
                mark("partial")
                failure = classify_failure(exc)
                print(
                    f"Evaluation failed for job {index + 1}: {failure.category} — {failure}"
                )
                if on_error:
                    on_error(jobs[index], failure)
            # Persist successful assessments individually before the next
            # completion. A later outage must not erase job-to-reason links.
            if results[index] is not None and on_result:
                on_result(results[index])
            if on_progress:
                on_progress(successful, failed, len(jobs))
    return [result for result in results if result is not None]


def evaluation_reasoning_options(provider):
    """Lower reasoning for the selected models without breaking legacy overrides."""
    model = evaluation_model_id(provider)
    if provider == "gpt" and model == "gpt-6.1-sol":
        return {"reasoning_effort": "low"}
    if provider == "gemini" and model in {"gemini-3.6-flash", "gemini-4-argon"}:
        return {"thinking_level": "low"}
    return {}


def create_evaluation_llm(provider):
    """Select the evaluation provider independently of the resume model."""
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=evaluation_model_id(provider),
            **streaming_options(provider),
            **evaluation_reasoning_options(provider),
            # Gemini uses fixed sampling defaults; omit unsupported overrides.
            # The shared policy controls retries and cooldown, avoiding a
            # separate retry burst from each concurrent SDK request.
            timeout=90.0,
            max_retries=0,
        )
    if provider == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=evaluation_model_id(provider),
            **streaming_options(provider),
            default_request_timeout=90.0,
            max_retries=1,
            max_tokens=8192,
        )
    if provider == "gpt":
        from langchain_openai import ChatOpenAI

        try:
            timeout = min(
                600, max(30, int(os.getenv("GPT_EVALUATION_TIMEOUT_SECONDS", "180")))
            )
        except ValueError:
            timeout = 180
        return ChatOpenAI(
            model=evaluation_model_id(provider),
            **streaming_options(provider),
            timeout=float(timeout),
            max_retries=1,
            **evaluation_reasoning_options(provider),
        )
    raise ValueError("Evaluation provider must be gemini, claude or gpt.")


@stage("evaluation.provider")
def evaluate_jobs(
    resume_context: str,
    jobs: list,
    include_all: bool = False,
    target_roles: Optional[list[str]] = None,
    on_progress=None,
    on_result=None,
    provider: str = "gemini",
    candidate_profile=None,
    on_error=None,
    should_cancel=None,
    cache_directory=None,
    requirement_loader=None,
    log_jobs=True,
):
    """Assess jobs with Gemini, Claude or GPT using the same suitability schema.

    The command-line pipeline keeps only strong fits by default. The web UI
    passes ``include_all=True`` so it can display all top semantic matches,
    including roles that need further review.
    """
    from langchain_core.prompts import ChatPromptTemplate

    if provider not in EVALUATION_DEFAULTS:
        raise ValueError("Evaluation provider must be gemini, claude or gpt.")
    if not jobs:
        return []
    # Keep concurrency modest. Gemini uses shared pacing/retries; Claude uses
    # SDK retries per request. Never retry the complete evaluation corpus.
    workers = min(
        8,
        max(
            1,
            int(
                os.getenv(
                    f"{provider.upper()}_EVALUATION_WORKERS",
                    "2" if provider == "gemini" else "4",
                )
            ),
        ),
    )
    from backend.evaluation.requirements import RequirementLoader, align_assessment

    requirement_loader = requirement_loader or RequirementLoader(
        should_cancel or (lambda: False)
    )
    llm = create_evaluation_llm(provider)
    structured_llm = llm.with_structured_output(
        (
            required_output_schema(JobEvaluation)
            if provider in {"claude", "gpt"}
            else JobEvaluation
        ),
        **(
            {"method": "json_schema"} if provider in {"gemini", "claude", "gpt"} else {}
        ),
        **({"include_raw": True} if provider == "claude" else {}),
        **({"strict": True} if provider == "gpt" else {}),
    )
    policy = None
    if provider == "gemini":
        rpm = max(0, int(os.getenv("GEMINI_EVALUATION_RPM", "0")))
        policy = GeminiRequestPolicy(shared_pacer(llm.model, rpm))

    # The system message sets the evaluation rules; the human message supplies
    # the candidate and one job at a time.
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                RECRUITER_PROMPT
                + "\nThe shared requirements are authoritative. Evaluate exactly one verdict per requirement_id. "
                "Copy requirement_id, requirement, importance, job_quote, section and type exactly. "
                "Do not add, omit, split, merge or reclassify criteria. Unclear importance is not mandatory. "
                "Responsibilities alone do not establish prior employment prerequisites.\n",
            ),
            (
                "human",
                "<candidate_evidence>\n{resume}\n</candidate_evidence>\n"
                "Selected roles of interest: {target_roles}\n"
                "<untrusted_job_evidence>\n{job_desc}\n</untrusted_job_evidence>\n"
                "<shared_requirements>\n{requirements}\n</shared_requirements>\nURL: {url}\n{correction}",
            ),
        ]
    )

    chain = prompt | structured_llm

    @stage(f"evaluation.{provider}")
    def evaluate_one(job):
        """Each request assesses one job; the worker pool overlaps requests."""
        if should_cancel and should_cancel():
            raise RuntimeError("Run cancelled")
        company = job.metadata.get("company", "Unknown")
        title = job.metadata.get("title", "Unknown Title")
        if log_jobs:
            print(f"Evaluating: {title} at {company}...")

        requirements = requirement_loader(job)
        inputs = {
            "correction": "",
            "requirements": requirements.model_dump_json(),
            "resume": resume_context,
            "job_desc": job.page_content,
            "target_roles": ", ".join(target_roles or [])
            or "Use the resume preferred domains",
            "url": job.metadata.get("url", "No URL"),
        }

        correction = ""

        # Perform one provider request and validate its structured response before accepting it.
        def operation():
            nonlocal correction
            if should_cancel and should_cancel():
                raise RuntimeError("Run cancelled")
            with model_request(provider, evaluation_model_id(provider)) as callbacks:
                result = chain.invoke(
                    {**inputs, "correction": correction},
                    config={"callbacks": callbacks},
                )
            try:
                return align_assessment(
                    validate_assessment_response(result, JobEvaluation), requirements
                )
            except EvaluationFailure as exc:
                correction = (
                    "The previous assessment failed validation: "
                    + str(exc)
                    + " Return the complete corrected assessment, preserving every "
                    "shared criterion and its importance."
                )
                raise

        # Each retry still passes cancellation checks and the provider's pacer.
        from backend.evaluation.cache import cached_assessment

        evaluation = cached_assessment(
            cache_directory,
            {
                "inputs": inputs,
                "profile": candidate_profile,
                "posting_version": job.metadata.get("version_id"),
                "provider": provider,
                "model": evaluation_model_id(provider),
                **(
                    {"reasoning_options": evaluation_reasoning_options(provider)}
                    if evaluation_reasoning_options(provider)
                    else {}
                ),
                "prompt": prompt.pretty_repr(),
                "schema": JobEvaluation.model_json_schema(),
                "policy": "shared-requirements-v1",
            },
            JobEvaluation,
            lambda: retry_invalid_assessment(
                lambda: policy.invoke(operation) if policy else operation()
            ),
            should_cancel or (lambda: False),
        )

        evaluation = align_assessment(evaluation, requirements)
        score, fit_category, mismatch_reason, evidence = score_requirements(
            evaluation.requirement_verdicts, resume_context, job.page_content
        )
        # Only corroborated code checks may override the evidence rubric.
        checked_category, checked_reason = enforce_experience_fit(
            evaluation, job, resume_context, candidate_profile
        )
        if checked_category == "not_suitable" and checked_reason.startswith(
            ("Seniority mismatch:", "Required experience exceeds profile:")
        ):
            fit_category, mismatch_reason = checked_category, checked_reason
            score = min(score, 39) if score is not None else None
        elif (
            fit_category == "strong_match"
            and evaluation.experience_alignment != "meets"
        ):
            fit_category, mismatch_reason = (
                "review",
                "Professional experience alignment needs review.",
            )
            score = min(score, 79)
        result = {
            "jobId": hashlib.sha256(
                str(job.metadata.get("url") or (title + company)).encode()
            ).hexdigest()[:24],
            "score": score,
            "score_method": "shared-requirements-rubric-v1",
            "requirement_set_id": hashlib.sha256(
                json.dumps(requirements.model_dump(), sort_keys=True).encode()
            ).hexdigest(),
            "requirement_extraction_model": requirements.extraction_model,
            "requirement_extraction_version": requirements.extraction_version,
            "requirement_verdicts": evidence,
            "work_type": evaluation.work_type,
            "verification": "unverified",
            "title": title,
            "company": company,
            "company_logo": job.metadata.get("company_logo", ""),
            "rationale": evaluation.match_rationale,
            "missing_skills": evaluation.missing_skills,
            # The source URL is the stable job identity; do not let model
            # formatting changes break links or assessment recovery.
            "apply_url": job.metadata.get("url") or evaluation.apply_url,
            "is_strong_fit": fit_category == "strong_match",
            "fit_category": fit_category,
            "mismatch_reason": mismatch_reason,
            "location": job.metadata.get("location", "Unknown Location"),
            "requested_location": job.metadata.get("requested_location", ""),
            "source": job.metadata.get("source", "Unknown Platform"),
            "posted_at": job.metadata.get("posted_at", ""),
            "evaluation_provider": provider,
            "evaluation_model_id": evaluation_model_id(provider),
            "job_description": job.metadata.get("job_description", ""),
            "description_available": (
                bool(job.metadata.get("job_description", "").strip())
                if "job_description" in job.metadata
                else None
            ),
            "about_company": evaluation.about_company,
            "candidate_requirements": evaluation.candidate_requirements,
            "salary": evaluation.salary,
            "experience_alignment": (
                "gap"
                if fit_category == "not_suitable"
                and evaluation.fit_category != "not_suitable"
                else evaluation.experience_alignment
            ),
            "required_experience_evidence": evaluation.required_experience_evidence,
            "minimum_professional_years": evaluation.minimum_professional_years,
        }

        if result["description_available"] is False:
            result.update(
                score=None,
                fit_category="review",
                is_strong_fit=False,
                about_company="",
                candidate_requirements=[],
                missing_skills=[],
                requirement_verdicts=[],
                salary=None,
                work_type="unknown",
                experience_alignment="unknown",
                minimum_professional_years=None,
                required_experience_evidence="",
                rationale="The source did not return a job description. Candidate fit cannot be assessed reliably.",
                mismatch_reason="Job description unavailable; company details, requirements and skills gaps need review.",
            )

        # The web UI requests all categories and filters not_suitable after
        # evaluation; the CLI retains its original strong-match behavior.
        return result

    recommendations = _evaluate_concurrently(
        jobs, evaluate_one, workers, on_progress, on_result, on_error
    )
    return [
        job
        for job in recommendations
        if include_all or job["fit_category"] == "strong_match"
    ]


def evaluate_jobs_with_claude(
    resume_context: str,
    jobs: list,
    include_all: bool = False,
    target_roles: Optional[list[str]] = None,
    on_progress=None,
    on_result=None,
):
    """Compatibility entry point for callers that explicitly request Claude."""
    return evaluate_jobs(
        resume_context,
        jobs,
        include_all=include_all,
        target_roles=target_roles,
        on_progress=on_progress,
        on_result=on_result,
        provider="claude",
    )
