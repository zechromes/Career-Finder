"""Validate quoted evidence and compute an explicit, auditable rubric."""

# Keep each requirement tied to its importance, verdict, and supporting quotes.
from backend.schemas.evaluation import RequirementVerdict  # Compatibility export.


# Check supporting text against its source after case and whitespace normalization.
def quoted(quote, source):
    normalize = lambda value: " ".join(value.casefold().split())
    return bool(quote.strip()) and normalize(quote) in normalize(source)


# Verify quoted evidence before weighting requirements and applying fit thresholds.
def score_requirements(requirements, resume, job):
    rows = []
    seen = set()
    for item in requirements:
        row = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        key = " ".join(row["requirement"].casefold().split())
        if key in seen:
            continue
        seen.add(key)
        job_valid = quoted(row["job_quote"], job)
        # Each resume quote is checked on its own; one verified quote supports the verdict.
        quotes = [
            quote
            for quote in row.get("resume_quotes") or [row.get("resume_quote", "")]
            if quote.strip()
        ]
        found = [quoted(quote, resume) for quote in quotes]
        resume_valid = any(found)
        row["resume_quotes"], row["resume_quotes_verified"] = quotes, found
        row["resume_quote"] = next(
            (quote for quote, ok in zip(quotes, found) if ok), quotes[0] if quotes else ""
        )
        row["job_evidence_verified"] = job_valid
        row["resume_evidence_verified"] = resume_valid
        # A requirement the resume never mentions is not met (empty quote), but
        # only a verified resume quote can show a gap that rejects the job.
        # Unsupported claims cannot earn credit or cause hard rejection.
        missing = row["verdict"] == "not_met" and not quotes
        if not job_valid or not (resume_valid or missing):
            row["verdict"] = "unknown"
        rows.append(row)
    # Only requirements verified against the posting contribute to the denominator.
    valid = [row for row in rows if row["job_evidence_verified"]]
    mandatory = [row for row in valid if row["importance"] == "must_have"]
    if not valid:
        return (
            None,
            "review",
            "No verified requirement evidence; manual review needed.",
            rows,
        )
    # Mandatory requirements carry twice the weight of preferred requirements.
    weights = {"must_have": 2, "nice_to_have": 1, "unclear": 1}
    credits = {"met": 1, "partial": 0.5, "not_met": 0, "unknown": 0}
    score = round(
        100
        * sum(weights[r["importance"]] * credits[r["verdict"]] for r in valid)
        / sum(weights[r["importance"]] for r in valid)
    )
    # Evidence of a mandatory mismatch overrides the weighted score.
    if any(
        r["verdict"] == "not_met" and r["resume_evidence_verified"] for r in mandatory
    ):
        category, reason = (
            "not_suitable",
            "A mandatory requirement has an evidenced mismatch.",
        )
        score = min(score, 39)
    elif (
        mandatory
        and not any(row["importance"] == "unclear" for row in valid)
        and all(r["verdict"] == "met" for r in mandatory)
        and all(r["job_evidence_verified"] for r in rows)
        and score >= 80
    ):
        category, reason = "strong_match", ""
    else:
        category, reason = (
            "review",
            "Some requirements are partial, unknown, or lack verified evidence.",
        )
        score = min(score, 79)
    return score, category, reason, rows
