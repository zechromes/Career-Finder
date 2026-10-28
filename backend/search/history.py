"""Posting identity for incremental search, separate from assessment identity."""

from backend.observability import stage
from backend.search.collection import _job_key, deduplicate_jobs
import json


# Map stored assessment fields back to the posting shape used for deduplication.
def assessment_posting(result):
    return {
        **result,
        "url": result.get("apply_url", ""),
        "description": result.get("job_description", ""),
    }


@stage("jobs.deduplicate_history")
def unseen_postings(jobs, previous):
    """Retain distinct openings; title alone never identifies a posting."""
    previous_keys = {_job_key(job) for job in previous}
    return [
        job
        for job in deduplicate_jobs(jobs)
        if _job_key(job) not in previous_keys
        and not any(len(deduplicate_jobs([known, job])) == 1 for known in previous)
    ]


def missing_journal_assessments(path, current):
    """Recover missing postings from a run's journal, preserving current rows.

    The latest journal row is a complete assessment snapshot for that posting.
    Ignore a truncated final line left by a stopped process.
    """
    if not path.is_file():
        return []
    latest = {}
    with path.open(encoding="utf-8") as journal:
        for line in journal:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or not (
                row.get("apply_url") or row.get("jobId")
            ):
                continue
            latest[_job_key(assessment_posting(row))] = row
    seen = [assessment_posting(row) for row in current]
    recovered = []
    for row in latest.values():
        posting = assessment_posting(row)
        if unseen_postings([posting], seen):
            recovered.append(row)
            seen.append(posting)
    return recovered
