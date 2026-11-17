"""Label-free checks of an extracted profile against its original resume text."""

import re
from datetime import date

from backend.schemas.resume import ResumeProfile

# Headings the core profile fields already cover, so they never count as empty sections.
CORE_HEADINGS = re.compile(
    r"experience|employment|work|career|education|qualification|skill|summary|profile|about|objective|contact|personal details|references",
    re.I,
)
IGNORED = set(
    "the and for with from into over using use our their your this that are was were "
    "january february march april may june july august september october november december "
    "jan feb mar apr jun jul aug sep sept oct nov dec present current".split()
)


def _words(text):
    return [
        word
        for word in re.findall(r"[a-z0-9+#]+", text.casefold())
        if len(word) > 2 and not word.isdigit() and word not in IGNORED
    ]


def check(profile: ResumeProfile, threshold=0.6):
    """Report what extraction may have missed or invented; no model calls."""
    source = set(_words(profile.source_text))
    missing = [
        label
        for label, value in (
            ("Name", profile.name),
            ("Work history", profile.work_history),
            ("Education", profile.education),
            ("Technical skills", profile.tech_skills),
            ("Years of experience", profile.years_of_experience is not None),
            ("Target roles", profile.preferred_domains),
        )
        if not value
    ]
    filled = {
        section.heading.strip().lower()
        for section in profile.sections
        if any(entry.strip() for entry in section.entries)
    }
    empty = [
        heading
        for heading in profile.section_headings
        if heading.strip().lower() not in filled and not CORE_HEADINGS.search(heading)
    ]
    unsupported, checked = [], 0
    if source:
        entries = [("Work history", e) for e in profile.work_history]
        entries += [("Education", e) for e in profile.education]
        entries += [(s.heading, e) for s in profile.sections for e in s.entries]
        for field, entry in entries:
            words = _words(entry)
            if not words:
                continue
            checked += 1
            share = sum(word in source for word in words) / len(words)
            if share < threshold:
                unsupported.append(dict(field=field, entry=entry, found_share=round(share, 2)))
    skills = [
        skill
        for skill in profile.tech_skills
        if source and _words(skill) and not all(w in source for w in _words(skill))
    ]
    # Years cannot exceed the span from the earliest dated job to now.
    starts = [int(y) for e in profile.work_history for y in re.findall(r"\b(?:19|20)\d{2}\b", e)]
    span = date.today().year - min(starts) + 1 if starts else None
    years = (
        f"{profile.years_of_experience:g} years recorded, but dated jobs span at most {span}."
        if span is not None
        and profile.years_of_experience is not None
        and profile.years_of_experience > span
        else ""
    )
    return dict(
        source_text_available=bool(source),
        missing_fields=missing,
        empty_sections=empty,
        entries_checked=checked,
        unsupported_entries=unsupported,
        skills_not_in_resume=skills,
        years_check=years,
    )
