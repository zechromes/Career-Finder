"""Explicit dismissal preferences; private, reversible shortlist ordering only."""

import copy
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from backend.search.filters import LEVEL_PATTERNS
from backend.schemas.contracts import DismissalPreference


def normalize(value):
    return " ".join(str(value or "").casefold().split())


def action_key(job):
    url = job.get("apply_url") or job.get("url") or ""
    try:
        parsed = urlsplit(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            query = sorted(
                (k, v)
                for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                if not re.match(r"^(utm_|trk$|trackingId$|ref$|source$)", k, re.I)
            )
            return urlunsplit(
                (
                    parsed.scheme,
                    parsed.netloc.lower(),
                    parsed.path,
                    urlencode(query),
                    "",
                )
            ).rstrip("/")
    except ValueError:
        pass
    return (
        job.get("jobId")
        or url
        or "|".join(str(job.get(k) or "") for k in ("title", "company", "location"))
    )


def explicit_level(title):
    levels = [
        level
        for level, pattern in LEVEL_PATTERNS.items()
        if re.search(pattern, normalize(title))
    ]
    # Mixed-level postings are not evidence of a single level preference.
    return levels[0] if len(levels) == 1 else ""


def make_preference(dismissal, job):
    return DismissalPreference(
        **dismissal.model_dump(),
        title=job.get("title") or "",
        location=job.get("location") or "",
        seniority=explicit_level(job.get("title")),
    ).model_dump()


# Deliberately narrow: explicit currency code, complete range and pay period.
# A bare '$', an open-ended range or missing period is unknown, never inferred.
_AMOUNT = r"\d+(?:,\d{3})*(?:\.\d+)?\s*[kK]?"
_PAY = re.compile(
    rf"\b(?P<currency>AUD|USD|GBP|EUR|CAD|NZD)\s*\$?\s*(?P<low>{_AMOUNT})"
    rf"(?:\s*(?:-|–|—|to)\s*(?:(?P<high_currency>AUD|USD|GBP|EUR|CAD|NZD)\s*)?\$?\s*(?P<high>{_AMOUNT}))?"
    r"\s*(?:/|per\s+|a\s+)(?P<period>year|annum|hour|hr)\b",
    re.I,
)


def stated_pay(text):
    values = []
    for match in _PAY.finditer(text):
        if (
            match["high_currency"]
            and match["high_currency"].upper() != match["currency"].upper()
        ):
            continue
        suffix = text[match.end() : match.end() + 32]
        if re.match(
            r"\s*(?:\+|plus\b|and\s+(?:above|up)\b|or\s+more\b|upwards\b)", suffix, re.I
        ):
            continue
        prefix = text[max(0, match.start() - 60) : match.start()]
        if not re.search(
            r"\b(?:salary|pay|remuneration|compensation|wage|rate)\b", prefix, re.I
        ):
            continue
        # Do not treat "from AUD 80k/year" or "up to ..." as a closed fixed rate.
        if re.search(
            r"\b(?:from|starting at|up to|minimum|at least)\s*$",
            text[max(0, match.start() - 24) : match.start()],
            re.I,
        ):
            continue

        def amount(value):
            value = value.replace(",", "").replace(" ", "").lower()
            return float(value.rstrip("k")) * (1000 if value.endswith("k") else 1)

        low = amount(match["low"])
        high = amount(match["high"]) if match["high"] else low
        if low > high:
            continue
        period = "hour" if match["period"].lower() in {"hour", "hr"} else "year"
        values.append((match["currency"].upper(), period, high))
    # Multiple offers/rates are ambiguous; do not infer which applies to the job.
    return values[0] if len(values) == 1 else None


def matches_preference(metadata, preference):
    reason = preference.reason
    if reason == "role":
        title = normalize(preference.title)
        return bool(
            title
            and title != "unknown title"
            and title == normalize(metadata.get("title"))
        )
    if reason == "location":
        location = normalize(preference.location)
        return bool(
            location
            and location not in {"unknown", "unknown location"}
            and location == normalize(metadata.get("location"))
        )
    if reason == "seniority":
        return bool(
            preference.seniority
            and preference.seniority == explicit_level(metadata.get("title"))
        )
    if reason == "salary":
        pay = stated_pay(
            str(
                metadata.get("job_description")
                or metadata.get("original_content")
                or ""
            )
        )
        return bool(
            pay
            and pay[:2] == (preference.currency, preference.period)
            and pay[2] < preference.minimum_salary
        )
    return False


def prioritize_preferences(documents, feedback):
    preferences = []
    for value in (feedback or {}).values():
        try:
            preferences.append(DismissalPreference.model_validate(value))
        except ValueError:
            continue  # An unreadable legacy preference must not break searching.
    # Stable partition: no exclusions, repeated dismissals do not compound a penalty.
    return sorted(
        documents,
        key=lambda doc: any(matches_preference(doc.metadata, p) for p in preferences),
    )


def load_feedback(run_id):
    """Snapshot private preferences for a worker without serializing an API response."""
    from fastapi import HTTPException
    from backend import runs
    from backend.profiles import storage

    with storage.LOCK, runs.RUNS_LOCK:
        runs.check_running(run_id)
        owner = runs.RUNS[run_id]
        profile_id = owner.get("saved_profile_id")
        if profile_id:
            try:
                owner = storage.read_profile(profile_id)
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
        return copy.deepcopy(owner.get("dismissal_feedback", {}))
