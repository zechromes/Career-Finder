"""Hypothetical job ads (HyDE) for the role queries of QUERY_BUILDER=hyde.

Ads are written in posting language from resume evidence only, cached on disk by their
inputs, and searched densely; any failure falls back to the plain role titles.
"""

import hashlib
import json
import re
import time

from pydantic import BaseModel, Field

from backend.paths import HYDE_QUERY_CACHE_DIR

# Marks a query as a generated ad; retrieval sends it to dense search only.
HYDE_PREFIX = "Job ad: "
# Bump when the prompt changes so cached ads are regenerated.
PROMPT_VERSION = "hyde-v1"
_FAILURE_TTL = 300
_FAILED = {}

PROMPT = """Write {count} short, different job ads this candidate would be a strong match for.
Each ad: a job title, then 3-4 sentences of responsibilities and requirements.

Rules:
- Name only skills, tools and domains from the lists below; add none.
- Seniority level: {level}. {years_rule}
- No company names, salary, benefits or culture statements.

Target roles: {roles}
Strongest skills: {skills}
Most recent work:
{experience}"""


class _Ads(BaseModel):
    ads: list[str] = Field(min_length=1, max_length=3)


def _years_rule(years):
    if years is None:
        return "Do not state a number of years of experience."
    return f"Do not ask for more than {years:g} years of experience."


def _asks_more_years(ad, years):
    asked = [int(value) for value in re.findall(r"(\d{1,2})\s*\+?\s*(?:years?|yrs)\b", ad, re.I)]
    return bool(asked) and (years is None or max(asked) > years)


def _generate(prompt):
    from backend.profiles.extraction import profile_llm, profile_model_id

    return profile_llm(profile_model_id("openai")).with_structured_output(_Ads).invoke(prompt).ads


def job_ads(roles, skills, experience, years=None, level="unknown", count=3):
    """Up to `count` ads, or [] when generation fails or the profile names nothing to search."""
    if not (roles or skills):
        return []
    prompt = PROMPT.format(
        count=count,
        level=level if level and level != "unknown" else "match the work below",
        years_rule=_years_rule(years),
        roles=", ".join(roles) or "any that fit the skills",
        skills=", ".join(skills) or "none listed",
        experience="\n".join(f"- {entry}" for entry in experience) or "- none listed",
    )
    key = hashlib.sha256(f"{PROMPT_VERSION}\n{prompt}".encode()).hexdigest()
    path = HYDE_QUERY_CACHE_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # A search builds queries and weights in two calls; both must see the same failure.
    # shortcut: a failure is remembered per process for 5 minutes, move to a request-scoped memo if that bites.
    if time.monotonic() - _FAILED.get(key, -_FAILURE_TTL) < _FAILURE_TTL:
        return []
    try:
        ads = [str(ad).strip() for ad in _generate(prompt)][:count]
    except Exception as error:
        print(f"HyDE generation failed; using role titles instead: {type(error).__name__}")
        _FAILED[key] = time.monotonic()
        return []
    # The prompt forbids inflated experience; drop any ad that ignored it.
    ads = [ad for ad in ads if ad and not _asks_more_years(ad, years)]
    if not ads:
        _FAILED[key] = time.monotonic()
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ads, ensure_ascii=False), encoding="utf-8")
    return ads
