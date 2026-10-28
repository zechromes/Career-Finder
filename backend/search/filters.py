"""Conservative explicit search filters; unknown is distinct from a mismatch."""

import re


def work_arrangement(job):
    structured = str(job.get("work_type", "")).strip().casefold()
    if structured in {"remote", "hybrid", "on-site"}:
        return structured
    text = " ".join(
        str(job.get(field, "")) for field in ("location", "description")
    ).casefold()
    text = text.replace("onsite", "on-site")
    # Negative statements take priority over positive keyword mentions.
    not_remote = bool(
        re.search(
            r"\b(?:not|no|non)[ -]+(?:a\s+)?remote\b|\bremote\s+(?:work|working)\s+(?:is\s+)?(?:not|unavailable)|\b(?:no|not)\s+work\s+from\s+home\b|\bwork\s+from\s+home\s+(?:is\s+)?(?:not|unavailable)",
            text,
        )
    )
    hybrid = bool(
        re.search(
            r"\bhybrid\s+(?:work|working|role|position|arrangement|schedule|model)\b|\(hybrid\)|^hybrid$",
            text,
        )
    )
    if hybrid and not re.search(r"\b(?:not|no|non)[ -]+(?:a\s+)?hybrid\b", text):
        return "hybrid"
    if not not_remote and re.search(
        r"\b(?:fully|100%|entirely)\s+remote\b|\bremote\s+(?:work|working|role|position|opportunity)\b|\bwork\s+from\s+home\b",
        text,
    ):
        return "remote"
    location = str(job.get("location", "")).casefold()
    if not not_remote and re.search(r"\bremote\b", location):
        return "remote"
    if not re.search(
        r"\b(?:not|no|non)[ -]+(?:an?\s+)?(?:on-site|office[- ]based|in[- ]office)\b",
        text,
    ) and re.search(r"\bon-site\b|\boffice[- ]based\b|\bin[- ]office\b", text):
        return "on-site"
    return "unknown"


LEVEL_PATTERNS = {
    "graduate": r"\b(?:graduate|new grad)\b",
    "entry": r"\b(?:entry[- ]level|entry|intern|internship)\b",
    "junior": r"\b(?:junior|jr)\b",
    "mid": r"\b(?:mid[- ]level|mid|intermediate)\b",
    "senior": r"\b(?:senior|sr|lead|principal|staff|director|head|chief)\b",
}


def matches_seniority(title, requested):
    if requested in {"auto", "any"}:
        return True
    levels = {
        level
        for level, pattern in LEVEL_PATTERNS.items()
        if re.search(pattern, str(title).casefold())
    }
    # Unmarked roles are possible entry/mid candidates, not asserted to have that level.
    if not levels:
        return requested in {"entry", "mid"}
    return requested in levels and not (requested != "senior" and "senior" in levels)


def matches_search_filters(job, filters):
    if any(
        term.strip().casefold()
        in (str(job.get("title", "")) + " " + str(job.get("company", ""))).casefold()
        for term in filters.get("exclusions", [])
        if term.strip()
    ):
        return False
    work_type = filters.get("work_type", "any")
    if work_type != "any" and work_arrangement(job) != work_type:
        return False
    return matches_seniority(job.get("title", ""), filters.get("seniority", "auto"))
