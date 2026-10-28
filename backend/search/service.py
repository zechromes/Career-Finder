"""Search service operations, separate from HTTP route declarations."""

from backend.observability import stage, mark
import json
import copy
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from fastapi import Form, HTTPException
from backend.schemas.resume import ResumeProfile
from backend.search.collection import _job_key
from backend.search.history import assessment_posting, unseen_postings
from backend.schemas.contracts import FindMoreRequest, ProfileConfirmation, Preferences
from backend.search.embedding_text import profile_embedding_text
from backend.search.ranking import retrieval_queries, retrieval_query_weights
from backend.evaluation.orchestration import identity
from backend.exports import export_jobs_excel
from backend.cli import profile_to_context
import backend.configuration as configuration
import backend.evaluation.service as evaluation_service
import backend.profiles.service as profiles_service
import backend.runs as runs
import backend.evaluation.orchestration as orchestration
import backend.search.collection as collection
import backend.search.retrieval as retrieval


def retry_external_call(operation, attempts=3):
    """Retry transient API failures that can occur when a device wakes up."""
    last_error = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(2**attempt)
    raise last_error


@stage("search.pipeline")
def execute_job_search(run_id, resume_path, options):
    """Complete steps 2 and 3: search, match, and evaluate the jobs."""
    run_dir = runs.RUNS_DIR / run_id
    # Each search gets an immutable eligibility scope over shared public-job vectors.
    # Other searches cannot add unrelated postings to this scope.
    db_dir = Path(options["persist_dir"])
    jobs_csv = run_dir / "retrieved_jobs.csv"
    recommendations_xlsx = run_dir / "relevant_jobs.xlsx"
    append = options.get("append", False)
    history_path = run_dir / "shortlisted_jobs.json"

    try:
        from backend.search.preferences import load_feedback

        # Read owner-scoped feedback once; later changes affect the next search.
        dismissal_feedback = load_feedback(run_id)
        # Read the candidate context and copy the current results before starting this batch.
        # The copy keeps previous results stable while the search does its external work.
        with runs.RUNS_LOCK:
            resume_context = runs.RUN_CONTEXTS[run_id]
            candidate_profile = runs.RUNS[run_id].get("profile") or {}
            previous = copy.deepcopy(runs.RUNS[run_id])
        # A repeat worker must not erase assessments even if an older caller
        # omitted the incremental flag.
        append = append or bool(
            previous.get("recommendations") or previous.get("excluded_recommendations")
        )
        # Preserve cumulative results; only this new batch consumes the new shortlist budget.
        prior_results = (
            (
                previous.get("recommendations", [])
                + previous.get("excluded_recommendations", [])
            )
            if append
            else []
        )
        prior_count = len(prior_results)
        seen_postings = (
            json.loads(history_path.read_text())
            if append and history_path.is_file()
            else []
        )
        seen_postings.extend(assessment_posting(item) for item in prior_results)
        prior_errors = previous.get("evaluation_errors", []) if append else []
        prior_failed = len(prior_errors)

        # Collect by user-selected roles first. Resume experience and interests
        # are used only after collection, so career changes keep a broad pool.
        runs.update_run(
            run_id,
            phase=2,
            phase_label="Collecting vacancies by role",
            status="running",
            matching_strategy="role_first",
            scrape_errors=[],
            last_search_added=0,
            evaluation_model="all",
            evaluation_model_id="Claude + GPT + Gemini",
        )
        if not append:
            runs.update_run(
                run_id,
                phase=2,
                phase_label="Collecting vacancies by role",
                matching_strategy="role_first",
                recommendations=[],
                jobs_found=0,
                jobs_screened=0,
                evaluated_jobs=0,
                displayed_jobs=0,
                excluded_jobs=0,
                excluded_reasons={},
                recommendations_found=0,
                excluded_recommendations=[],
                evaluation_total=0,
                evaluation_failed=0,
                evaluation_errors=[],
                evaluation_skipped=0,
                status="running",
                scrape_errors=[],
                evaluation_model="all",
                evaluation_model_id="Claude + GPT + Gemini",
            )
        scrape_errors = []

        # Keep source failures visible while other job-board searches continue.
        def scrape_failure(message):
            mark("partial")
            scrape_errors.append(message)
            runs.update_run(run_id, scrape_errors=list(scrape_errors))

        jobs = collection.fetch_job_vacancies(
            options["queries"],
            options["locations"],
            options["platforms"],
            adaptive=True,
            seen_postings=seen_postings if append else None,
            remote=options["remote"],
            posted_days_old=options["posted_days_old"],
            on_progress=lambda count: runs.update_run(
                run_id,
                jobs_found=count + (previous.get("jobs_found", 0) if append else 0),
            ),
            on_error=scrape_failure,
            on_status=lambda message: runs.update_run(run_id, message=message),
            should_cancel=lambda: runs.stopped(run_id),
            # An explicit repeat search asks for newly available postings now.
            force_refresh=append,
            search_filters={
                key: options.get(key, default)
                for key, default in (
                    ("exclusions", []),
                    ("work_type", "any"),
                    ("seniority", "auto"),
                )
            },
        )
        runs.check_running(run_id)
        exclusions = [
            value.lower() for value in options.get("exclusions", []) if value.strip()
        ]
        jobs = [
            job
            for job in jobs
            if not any(
                value
                in (
                    str(job.get("title", "")) + " " + str(job.get("company", ""))
                ).lower()
                for value in exclusions
            )
        ]
        from backend.search.filters import work_arrangement, matches_seniority

        work_type = options.get("work_type", "any")
        if work_type != "any":
            jobs = [job for job in jobs if work_arrangement(job) == work_type]
        seniority = options.get("seniority", "auto")
        if seniority not in {"auto", "any"}:
            jobs = [
                job
                for job in jobs
                if matches_seniority(job.get("title", ""), seniority)
            ]
        if append:
            jobs = unseen_postings(jobs, seen_postings)
        # A duplicate-only search completes without clearing the earlier result snapshot.
        if append and not jobs:
            runs.update_run(
                run_id,
                phase=4,
                status="error" if scrape_errors else "complete",
                error=(
                    "Job searches failed. Retry finding more jobs."
                    if scrape_errors
                    else None
                ),
                last_search_added=0,
                jobs_found=previous.get("jobs_found", 0),
                message=(
                    "Job searches failed; your previous results are still available."
                    if scrape_errors
                    else "No new jobs were found. Your previous results are still available."
                ),
            )
            if not scrape_errors:
                profiles_service.save_completed_search_profile(run_id)
            return
        if not jobs:
            jobs_csv.write_text("", encoding="utf-8")
            export_jobs_excel([], recommendations_xlsx)
            runs.update_run(
                run_id,
                phase=2,
                jobs_found=0,
                jobs_screened=0,
                evaluated_jobs=0,
                displayed_jobs=0,
                excluded_jobs=0,
                excluded_reasons={},
                recommendations=[],
                message=(
                    "No jobs were found"
                    if not scrape_errors
                    else "Job searches failed. Retry scraping."
                ),
                status="complete" if not scrape_errors else "error",
                error="Job searches failed. Retry scraping." if scrape_errors else None,
            )
            if not scrape_errors:
                profiles_service.save_completed_search_profile(run_id)
            return

        # The aggregator applies location/date constraints and deduplication.
        # Automatic seniority prioritizes experience-compatible titles during
        # ranking; it does not discard other levels from the collected pool.
        runs.update_run(
            run_id,
            phase=2,
            jobs_found=len(jobs) + (previous.get("jobs_found", 0) if append else 0),
            # Retain this API field for old clients; now it counts the pool
            # available for matching after the search constraints.
            jobs_screened=len(jobs)
            + (previous.get("jobs_screened", 0) if append else 0),
            message=f"Collected {len(jobs)} vacancies; ranking against your resume",
        )

        runs.update_run(run_id, phase=3, phase_label="Semantic matching")
        retry_external_call(
            lambda: collection.vectorize_jobs_to_db(
                jobs,
                persist_dir=str(db_dir),
                shared=True,
                should_cancel=lambda: runs.stopped(run_id),
            )
        )
        runs.check_running(run_id)
        import pandas as pd

        # Append collected postings to the export while normalizing duplicate identities.
        previous_csv = (
            pd.read_csv(jobs_csv)
            if append and jobs_csv.is_file() and jobs_csv.stat().st_size
            else None
        )
        with jobs_csv.open("w", encoding="utf-8", newline="") as output_file:
            import pandas as pd

            frame = pd.DataFrame(jobs).drop(columns=["description"], errors="ignore")
            if previous_csv is not None:
                frame = pd.concat([previous_csv, frame], ignore_index=True)
                keys = [_job_key(row) for row in frame.fillna("").to_dict("records")]
                frame = frame.loc[~pd.Series(keys).duplicated().to_numpy()]
            frame.to_csv(output_file, index=False)

        # Step 3: retrieve the closest jobs and assess candidate suitability.
        runs.update_run(
            run_id, phase=3, phase_label="Matching experience, skills and interests"
        )
        relevant_jobs = retry_external_call(
            lambda: retrieval.retrieve_relevant_jobs(
                profile_embedding_text(candidate_profile),
                persist_dir=str(db_dir),
                top_k=options["top_k"],
                candidate_profile=candidate_profile if seniority == "auto" else None,
                queries=retrieval_queries(candidate_profile, options["queries"]),
                dismissal_feedback=dismissal_feedback,
                query_weights=retrieval_query_weights(
                    candidate_profile, options["queries"]
                ),
                # This fresh store contains only jobs already filtered by the
                # aggregator. Do not apply a different location rule here.
            )
        )
        if append:
            # Defend against old vector-store metadata and duplicate retrieval rows.
            relevant_postings = unseen_postings(
                [
                    {
                        **doc.metadata,
                        "description": doc.metadata.get(
                            "job_description", doc.page_content
                        ),
                    }
                    for doc in relevant_jobs
                ],
                seen_postings,
            )
            allowed_keys = {_job_key(item) for item in relevant_postings}
            unique_documents = {}
            # Retry checkpoints must retain the roles used for this specific search batch.
            for doc in relevant_jobs:
                key = _job_key(doc.metadata)
                if key in allowed_keys:
                    unique_documents.setdefault(key, doc)
            relevant_jobs = list(unique_documents.values())
        for doc in relevant_jobs:
            doc.metadata["_evaluation_target_roles"] = options["queries"]
        if not append:
            history_path.write_text("[]", encoding="utf-8")
        # Return every relevant semantic match to the UI; the frontend handles
        # pagination without dropping jobs from the evaluation set.
        runs.update_run(
            run_id,
            phase=4,
            phase_label="Fit evaluation",
            evaluation_total=prior_count + len(relevant_jobs),
            message=f"Evaluating 0 / {len(relevant_jobs)} jobs",
        )

        # Combine existing result counts with progress from the current evaluation batch.
        def report_evaluation_progress(successful, failed, total):
            runs.update_run(
                run_id,
                evaluated_jobs=prior_count + successful,
                evaluation_failed=prior_failed + failed,
                message=f"Evaluating {successful} / {total} jobs · {failed} model assessments failed",
            )

        # Publish and journal each assessment so partial work survives interruption.
        def save_assessment(result):
            # Keep a durable association between the job and its exact reason,
            # even if the worker stops before it writes the final run summary.
            # Merge this assessment and save its history and retry checkpoints together.
            # Other lock-using callbacks wait, preventing conflicting updates to the same job.
            with runs.RUNS_LOCK:
                runs.check_running(run_id)
                existing = next(
                    (
                        row
                        for field in ("recommendations", "excluded_recommendations")
                        for row in runs.RUNS[run_id].get(field, [])
                        if identity(row) == identity(result)
                    ),
                    None,
                )
                result["added_at"] = (
                    existing.get("added_at")
                    if existing is not None
                    else datetime.now(timezone.utc).isoformat()
                )
                with (run_dir / "job_assessments.jsonl").open(
                    "a", encoding="utf-8"
                ) as output:
                    output.write(json.dumps(result) + "\n")
                evaluation_service.upsert_assessment(run_id, result)
                seen_postings.append(assessment_posting(result))
                seen_postings[:] = list(
                    {_job_key(item): item for item in seen_postings}.values()
                )
                history_path.write_text(json.dumps(seen_postings), encoding="utf-8")
                # Keep pending requests recoverable after cancellation/restart.
                # Complete providers leave the checkpoint without being charged again.
                matching_doc = next(
                    (
                        doc
                        for doc in relevant_jobs
                        if _job_key(doc.metadata)
                        == _job_key(assessment_posting(result))
                    ),
                    None,
                )
                if matching_doc is not None:
                    for provider_name, assessment in result.get(
                        "model_evaluations", {}
                    ).items():
                        failed_documents[:] = [
                            entry
                            for entry in failed_documents
                            if not (
                                _job_key(entry["metadata"])
                                == _job_key(matching_doc.metadata)
                                and entry["metadata"].get("_evaluation_provider")
                                == provider_name
                            )
                        ]
                        if assessment.get("status") != "complete":
                            failed_documents.append(
                                {
                                    "page_content": matching_doc.page_content,
                                    "metadata": {
                                        **matching_doc.metadata,
                                        "_evaluation_provider": provider_name,
                                    },
                                }
                            )
                    failed_path.write_text(json.dumps(failed_documents))
                runs.update_run(
                    run_id,
                    last_search_added=len(runs.RUNS[run_id].get("recommendations", []))
                    + len(runs.RUNS[run_id].get("excluded_recommendations", []))
                    - prior_count,
                    displayed_jobs=len(runs.RUNS[run_id].get("recommendations", [])),
                    excluded_jobs=len(
                        runs.RUNS[run_id].get("excluded_recommendations", [])
                    ),
                )

        # Keep earlier failures retryable alongside failures from the additional search.
        evaluation_errors = list(prior_errors)
        failed_path = run_dir / "failed_jobs.json"
        failed_documents = (
            json.loads(failed_path.read_text())
            if append and failed_path.is_file()
            else []
        )
        failed_path.write_text(json.dumps(failed_documents))

        # Checkpoint the failed document and a safe error summary for targeted retry.
        def save_evaluation_error(job, failure):
            runs.check_running(run_id)
            failed_documents.append(
                {"page_content": job.page_content, "metadata": job.metadata}
            )
            (run_dir / "failed_jobs.json").write_text(json.dumps(failed_documents))
            # Save actionable causes instead of an exception class alone. Do
            # not record provider payloads that may contain resume text/keys.
            evaluation_errors.append(
                {
                    "title": job.metadata.get("title", "Unknown title"),
                    "company": job.metadata.get("company", "Unknown company"),
                    "apply_url": job.metadata.get("url", ""),
                    "provider": job.metadata.get("_evaluation_provider", ""),
                    "category": failure.category,
                    "message": str(failure),
                    "skipped": failure.skipped,
                }
            )
            runs.update_run(
                run_id,
                evaluation_errors=list(evaluation_errors),
                evaluation_skipped=sum(item["skipped"] for item in evaluation_errors),
            )

        # Individual requests retry under the selected provider policy. Retrying this
        # entire function would charge again for jobs that already succeeded.
        evaluated_recommendations = orchestration.evaluate_jobs(
            resume_context,
            relevant_jobs,
            cache_directory=profiles_service.evaluation_cache_directory(run_id),
            include_all=True,
            target_roles=options["queries"],
            on_progress=report_evaluation_progress,
            on_result=save_assessment,
            provider=options.get(
                "evaluation_model", configuration.DEFAULT_EVALUATION_PROVIDER
            ),
            candidate_profile=candidate_profile,
            on_error=save_evaluation_error,
            should_cancel=lambda: runs.stopped(run_id),
        )
        runs.check_running(run_id)
        failed_evaluations = len(evaluation_errors)
        if relevant_jobs and not evaluated_recommendations:
            provider_name = options.get(
                "evaluation_model", configuration.DEFAULT_EVALUATION_PROVIDER
            ).capitalize()
            reason = (
                evaluation_errors[0]["message"]
                if evaluation_errors
                else "Check credentials and provider availability."
            )
            raise RuntimeError(f"No {provider_name} evaluations succeeded. {reason}")
        # Read the original Date added values without a concurrent locked result update.
        # These values are reused so evaluation does not reset a job’s original date.
        with runs.RUNS_LOCK:
            added_dates = {
                identity(row): row.get("added_at")
                for field in ("recommendations", "excluded_recommendations")
                for row in runs.RUNS[run_id].get(field, [])
            }
        for row in evaluated_recommendations:
            row["added_at"] = added_dates.get(
                identity(row), datetime.now(timezone.utc).isoformat()
            )
        # Suitability is decided after collecting and ranking vacancies.
        # Career changes with transferable skills can remain review matches.
        claude_exclusions = [
            {
                **job,
                "reason": job.get("mismatch_reason") or "candidate-fit mismatch",
            }
            for job in evaluated_recommendations
            if evaluation_service.candidate_fit_category(job) == "not_suitable"
        ]
        recommendations = [
            job
            for job in evaluated_recommendations
            if evaluation_service.candidate_fit_category(job)
            in {"strong_match", "review"}
        ]
        if append:
            # Copy the combined old and new results before preparing the final append response.
            # Check cancellation first so a stopped run is not finalized as successful.
            with runs.RUNS_LOCK:
                runs.check_running(run_id)
                recommendations = copy.deepcopy(
                    runs.RUNS[run_id].get("recommendations", [])
                )
                claude_exclusions = copy.deepcopy(
                    runs.RUNS[run_id].get("excluded_recommendations", [])
                )
        # Stable sorting keeps semantic relevance within each fit category.
        recommendations.sort(
            key=lambda job: evaluation_service.candidate_fit_category(job)
            != "strong_match"
        )
        export_jobs_excel(recommendations, recommendations_xlsx)
        strong_matches = sum(1 for job in recommendations if job["is_strong_fit"])
        runs.update_run(
            run_id,
            phase=4,
            recommendations=recommendations,
            evaluated_jobs=prior_count + len(evaluated_recommendations),
            last_search_added=len(evaluated_recommendations),
            evaluation_failed=failed_evaluations,
            displayed_jobs=len(recommendations),
            excluded_jobs=len(claude_exclusions),
            excluded_recommendations=claude_exclusions,
            excluded_reasons=evaluation_service.group_exclusion_reasons(
                claude_exclusions
            ),
            recommendations_found=strong_matches,
            message=(
                (
                    f"Added {len(evaluated_recommendations)} new jobs; "
                    if append
                    else f"Evaluated {len(evaluated_recommendations)} jobs; "
                )
                + f"showing {len(recommendations)} candidate-fit matches; {failed_evaluations} failed"
            ),
            status="complete",
        )
        profiles_service.save_completed_search_profile(run_id)
    except runs.RunStopped:
        mark("cancelled")
        return
    except Exception as exc:
        mark("failed")
        if runs.stopped(run_id):
            return
        # Surface worker failures in the polling response instead of losing
        # them in the background thread.
        runs.update_run(
            run_id,
            status="error",
            error=str(exc),
            message="The pipeline could not finish",
        )


async def start_job_search(
    run_id: str,
    queries: str = Form(...),
    locations: str = Form(""),
    platforms: str = Form("linkedin,indeed,glassdoor"),
    remote: bool = Form(False),
    posted_days_old: int = Form(30),
    top_k: int = Form(15),
    evaluation_model: Literal["gemini", "claude", "gpt"] = Form(
        configuration.DEFAULT_EVALUATION_PROVIDER
    ),
):
    """Start steps 2 and 3 after the user confirms the profile search inputs."""
    # Look up the run safely in the shared dictionary.
    # This lock ends after the lookup; it does not protect the later search-start steps.
    with runs.RUNS_LOCK:
        run = runs.RUNS.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    if run_id in runs.ACTIVE_WORKERS or run["status"] not in {
        "awaiting_search",
        "complete",
        "error",
        "cancelled",
    }:
        raise HTTPException(
            status_code=409, detail="The profile is not ready for a job search."
        )
    # Only failed searches can reuse a profile. Extraction failures require a
    # new upload; do not launch another doomed worker without resume context.
    if run["status"] == "error" and (
        not run.get("profile") or not runs.RUN_CONTEXTS.get(run_id)
    ):
        raise HTTPException(
            status_code=409,
            detail="Upload your resume again to generate a profile before searching.",
        )
    if not 0 <= top_k <= 10000:
        raise HTTPException(
            status_code=400, detail="Results to evaluate must be between 0 and 10000."
        )
    if posted_days_old not in {0, 1, 7, 30}:
        raise HTTPException(
            status_code=400, detail="Posted age must be 0, 1, 7, or 30 days."
        )

    def split_values(value):
        """Read JSON arrays while supporting older comma-separated clients."""
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (TypeError, json.JSONDecodeError):
            pass
        return [item.strip() for item in value.split(",") if item.strip()]

    query_values = split_values(queries)
    location_values = split_values(locations) or ["Worldwide"]
    if not query_values:
        raise HTTPException(status_code=400, detail="Add at least one role.")

    options = {
        "queries": query_values,
        "locations": location_values,
        "platforms": split_values(platforms),
        "remote": remote,
        "posted_days_old": posted_days_old,
        "top_k": top_k,
        "evaluation_model": evaluation_model,
        "persist_dir": str(
            runs.RUNS_DIR / run_id / f"vector_db_search_{uuid.uuid4().hex}"
        ),
    }
    options.update(
        {
            key: run.get("preferences", {}).get(key, default)
            for key, default in [
                ("work_type", "any"),
                ("seniority", "auto"),
                ("exclusions", []),
            ]
        }
    )
    if run.get("recommendations") or run.get("excluded_recommendations"):
        return await find_more_jobs(
            run_id, FindMoreRequest(preferences=Preferences.model_validate(options))
        )
    if run.get("status") == "cancelled":
        runs.RUNS[run_id]["status"] = "awaiting_search"
    runs.update_run(
        run_id,
        status="running",
        phase=2,
        error=None,
        message="Starting your job search",
        # Restore confirmed search chips and filters when the tab reconnects.
        search_inputs={
            key: value for key, value in options.items() if key != "persist_dir"
        },
    )
    resume_path = runs.RUNS_DIR / run_id / "resume.pdf"
    runs.ACTIVE_WORKERS.add(run_id)
    worker = runs.threading.Thread(
        target=runs.run_worker,
        args=(run_id, execute_job_search, resume_path, options),
        daemon=True,
    )
    worker.start()
    return {"id": run_id}


async def retry_scraping(run_id: str):
    """Retry failed sources using confirmed inputs without replacing results."""
    return await find_more_jobs(run_id, None, retry_failed=True)


async def find_more_jobs(
    run_id: str, body: FindMoreRequest | None, *, retry_failed=False
):
    """Append new postings using the existing profile and edited search preferences."""
    # Check availability and reserve the run for an additional search in one locked sequence.
    # This prevents competing lock-using requests from starting work on the same run.
    with runs.RUNS_LOCK:
        run = runs.snapshot(run_id)
        if run_id in runs.ACTIVE_WORKERS or run["status"] not in {
            "complete",
            "error",
            "cancelled",
        }:
            raise HTTPException(
                409, "Wait for the current search to finish before finding more jobs."
            )
        if not run.get("profile") or not runs.RUN_CONTEXTS.get(run_id):
            raise HTTPException(409, "Generate a profile before finding more jobs.")
        prefs = (
            Preferences.model_validate(
                run.get("preferences") or run.get("search_inputs") or {}
            ).model_dump()
            if retry_failed
            else body.preferences.model_dump()
        )
        for field in ("queries", "locations", "platforms"):
            prefs[field] = [value.strip() for value in prefs[field] if value.strip()]
            if field == "locations" and not prefs[field]:
                prefs[field] = ["Worldwide"]
            if not prefs[field]:
                raise HTTPException(422, f"Add at least one {field} value.")
        retry_boards = prefs["platforms"]
        if retry_failed:
            errors = run.get("scrape_errors") or []
            if not errors:
                raise HTTPException(
                    409, "There are no failed job-board searches to retry."
                )
            # Older generic warnings have no source identity: retry the selected scope.
            identified = {
                board
                for board in prefs["platforms"]
                if any(
                    str(message).lower().startswith(board.lower()) for message in errors
                )
            }
            unknown = any(
                not any(
                    str(message).lower().startswith(board.lower())
                    for board in prefs["platforms"]
                )
                for message in errors
            )
            retry_boards = [
                board for board in prefs["platforms"] if unknown or board in identified
            ]
        failed_path = runs.RUNS_DIR / run_id / "failed_jobs.json"
        if failed_path.is_file():
            legacy_failures = json.loads(failed_path.read_text())
            original_roles = run.get("search_inputs", {}).get(
                "queries", run.get("preferences", {}).get("queries", [])
            )
            for entry in legacy_failures:
                entry.setdefault("metadata", {}).setdefault(
                    "_evaluation_target_roles", original_roles
                )
            failed_path.write_text(json.dumps(legacy_failures), encoding="utf-8")
        options = {
            **prefs,
            "remote": prefs["work_type"] == "remote",
            "append": True,
            "persist_dir": str(
                runs.RUNS_DIR / run_id / f"vector_db_search_{uuid.uuid4().hex}"
            ),
        }
        if retry_failed:
            options["platforms"] = retry_boards
        # Cancelled searches need explicit user reactivation before updates resume.
        runs.RUNS[run_id].update(
            status="running",
            error=None,
            phase=2,
            last_search_added=0,
            preferences=prefs,
            search_inputs=prefs,
            message=(
                "Retrying failed sources; keeping your previous results"
                if retry_failed
                else "Finding more jobs; keeping your previous results"
            ),
            scrape_errors=[],
        )
        runs.ACTIVE_WORKERS.add(run_id)
        runs.persist_run(run_id)
        worker = runs.threading.Thread(
            target=runs.run_worker,
            args=(
                run_id,
                execute_job_search,
                runs.RUNS_DIR / run_id / "resume.pdf",
                options,
            ),
            daemon=True,
        )
        try:
            worker.start()
        except Exception:
            runs.ACTIVE_WORKERS.discard(run_id)
            runs.RUNS[run_id].update(
                status=run["status"], error="The search could not start."
            )
            runs.persist_run(run_id)
            raise
    return {"id": run_id, "runId": run_id}


# Confirm initial profile inputs; existing assessments use the append search path.
async def confirm_search_profile(run_id: str, body: ProfileConfirmation):
    prefs = body.preferences.model_dump()

    for field in ("queries", "locations", "platforms"):
        prefs[field] = [value.strip() for value in prefs[field] if value.strip()]
        # Change to worldwide if location field is empty
        if field == "locations" and not prefs[field]:
            prefs[field] = ["Worldwide"]

        if not prefs[field]:
            raise HTTPException(422, f"Add at least one {field} value.")

    # Validate the current run and apply the confirmed profile under the same lock.
    # Conflicting lock-using operations wait while search startup is arranged.
    with runs.RUNS_LOCK:
        run = runs.snapshot(run_id)
        if run_id in runs.ACTIVE_WORKERS or run["status"] == "running":
            raise HTTPException(
                409, "Wait for the active worker to finish before confirming a profile."
            )
        if not run.get("profile"):
            raise HTTPException(409, "Extract a profile before confirming it.")

        if run.get("recommendations") or run.get("excluded_recommendations"):
            current_profile = ResumeProfile.model_validate(run["profile"]).model_dump()
            if current_profile != body.profile.model_dump():
                raise HTTPException(
                    409,
                    "This search already has assessments for its existing profile. Start a new search to use a changed resume or profile.",
                )
            return await find_more_jobs(
                run_id, FindMoreRequest(preferences=body.preferences)
            )
        context = profile_to_context(body.profile)
        runs.RUNS[run_id].update(
            profile=body.profile.model_dump(),
            preferences=prefs,
            status="awaiting_search",
        )
        runs.RUN_CONTEXTS[run_id] = context
        runs.run_context_path(run_id).write_text(context, encoding="utf-8")
        runs.persist_run(run_id)
        await start_job_search(
            run_id,
            queries=json.dumps(prefs["queries"]),
            locations=json.dumps(prefs["locations"]),
            platforms=",".join(prefs["platforms"]),
            remote=prefs["work_type"] == "remote",
            posted_days_old=prefs["posted_days_old"],
            top_k=prefs["top_k"],
            evaluation_model=prefs["evaluation_model"],
        )
    return {"id": run_id, "runId": run_id}
