"""Focused retrieval text; original evidence remains available for evaluation."""

import re
from html import unescape


# Build focused candidate text for retrieval without embedding unrelated resume details.
def profile_embedding_text(profile):
    data = profile if isinstance(profile, dict) else profile.model_dump()
    history = list(data.get("work_history") or [])

    # Sort current roles first, then use the latest year mentioned in each entry.
    def recency(entry):
        if re.search(r"\b(present|current|now)\b", entry, re.I):
            return 9999
        years = re.findall(r"\b(?:19|20)\d{2}\b", entry)
        return max(map(int, years), default=0)

    # Stable ordering retains resume order for ties/undated roles. Limit older
    # history rather than claiming we can determine relevance from titles alone.
    recent = sorted(history, key=recency, reverse=True)[:3]
    fields = [
        ("Headline", data.get("headline")),
        ("Summary", data.get("profile")),
        ("Recent work", "\n".join(recent)),
        ("Technical skills", ", ".join(data.get("tech_skills") or [])),
        ("Preferred domains", ", ".join(data.get("preferred_domains") or [])),
    ]
    return "\n".join(
        f"{label}: {value.strip()}"
        for label, value in fields
        if value and value.strip()
    )


# Heading patterns separate retrieval noise from requirement-bearing sections.
_NOISE = re.compile(
    r"^(?:about (?:us|the company|our company)|who we are|our (?:company|story|mission|values)|"
    r"(?:perks (?:and|&) )?benefits|what we offer|why (?:join|work (?:with|for)) us|"
    r"compensation(?: (?:and|&) benefits)?|equal (?:employment )?opportunity(?: employer)?|"
    r"diversity(?:,? equity)?(?: (?:and|&) inclusion)?|how to apply|application (?:process|instructions)|"
    r"privacy(?: notice| policy)?|legal(?: notice| disclaimer)?)$",
    re.I,
)
_KEEP = re.compile(
    r"^(?:(?:key |main |your )?(?:responsibilities|duties)|(?:job |role )?requirements|"
    r"(?:required |preferred |minimum )?qualifications|(?:technical |required |preferred )?skills|"
    r"(?:about|the) (?:role|position|opportunity)|job description|what you(?:['’]ll| will) (?:do|bring)|"
    r"what we(?:['’]re| are) looking for|experience|education)$",
    re.I,
)


# Remove low-value posting boilerplate before semantic indexing.
def clean_job_description(description):
    text = str(description or "")
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", text, flags=re.I | re.S)
    text = re.sub(
        r"</?(?:p|div|h[1-6]|li|ul|ol|br|section)\b[^>]*>", "\n", text, flags=re.I
    )
    text = unescape(re.sub(r"<[^>]+>", "", text))
    kept = []
    skipping = False
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        heading, separator, remainder = line.partition(":")
        heading = heading.strip(" #*•-–\t")
        if _NOISE.fullmatch(heading):
            skipping = True
            continue
        if _KEEP.fullmatch(heading):
            skipping = False
            if separator and remainder.strip():
                kept.append(remainder.strip())
            continue
        if not skipping:
            # Remove common standalone application/legal boilerplate only.
            if re.match(
                r"^(?:we are an equal opportunity employer|all qualified applicants will receive|to apply[, :]|apply now\b)",
                line,
                re.I,
            ):
                continue
            kept.append(line)
    return "\n".join(kept)


# Combine posting identity and focused requirements for job embeddings.
def job_embedding_text(job):
    return f"Job title: {job.get('title') or ''}\nResponsibilities and requirements:\n{clean_job_description(job.get('description'))}".strip()
