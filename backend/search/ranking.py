"""Small-corpus lexical ranking and deterministic reciprocal rank fusion."""

import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from backend.search.embedding_text import entry_year, profile_embedding_text
from backend.search.filters import LEVEL_PATTERNS


# Retrieval tuning defaults; RETRIEVAL_WEIGHTS (a JSON object) overrides any key.
DEFAULT_RETRIEVAL_WEIGHTS = {
    # Votes per query family, normalized so all weights sum to 1. Roles are short titles that
    # would otherwise decide the ranking alone; soft skills are in almost every posting, so
    # they are not searched (they still inform the fit assessment).
    "votes": {"roles": 0.5, "skills": 1.0, "soft_skills": 0.0, "experience": 1.0},
    # Separate experience queries kept, strongest first.
    "experience_queries": 8,
    # A skill only listed is a claim; each entry using it adds that entry's strength.
    "listed_skill": 0.5,
    # QUERY_BUILDER=skills keeps skills no entry shows, at this low score instead of dropping them.
    "listed_only": 0.2,
    "role_skill_boost": 1.5,
    "recency": {"recent_years": 1, "recent": 1.0, "mid_years": 3, "mid": 0.6, "older": 0.3, "undated": 0.6},
    # Entries from profiles extracted before types existed count as "untyped".
    "entry_types": {
        "job": 1.0, "internship": 0.8, "project": 0.8, "hackathon": 0.6,
        "education": 0.6, "other": 0.8, "untyped": 1.0,
    },
    # Skill and role-word matches an entry needs for full relevance, and the minimum.
    "relevance": {"full_at": 3, "floor": 0.25},
}


def retrieval_weights():
    raw = os.getenv("RETRIEVAL_WEIGHTS", "").strip()
    try:
        override = json.loads(raw) if raw else {}
    except json.JSONDecodeError as error:
        raise ValueError(f"RETRIEVAL_WEIGHTS is not valid JSON: {error}") from error
    if not isinstance(override, dict):
        raise ValueError("RETRIEVAL_WEIGHTS must be a JSON object")
    unknown = override.keys() - DEFAULT_RETRIEVAL_WEIGHTS.keys()
    if unknown:
        raise ValueError(f"Unknown RETRIEVAL_WEIGHTS keys: {', '.join(sorted(unknown))}")
    return {
        key: (
            {**value, **override[key]}
            if isinstance(value, dict) and isinstance(override.get(key), dict)
            else override.get(key, value)
        )
        for key, value in DEFAULT_RETRIEVAL_WEIGHTS.items()
    }


# Recent entries are stronger evidence; undated ones (often projects) sit in between.
def _recency_factor(entry, this_year, recency):
    year = entry_year(entry)
    if not year:
        return recency["undated"]
    age = this_year - min(year, this_year)
    if age <= recency["recent_years"]:
        return recency["recent"]
    return recency["mid"] if age <= recency["mid_years"] else recency["older"]


# Words that grade a skill rather than name it: "Docker (basics)" is Docker.
LEVEL_WORDS = (
    "basics", "basic", "fundamentals", "fundamental", "beginner", "intermediate",
    "advanced", "familiarity", "exposure", "proficient", "knowledge",
)
_STOP_WORDS = {"and", "of", "with", "for", "the", "in", "a", "an", "to", "using"}


def _stem(word):
    """Light stemming used on both sides, so "scripts", "scripting" and "script" meet."""
    # "ExpressJS" and "Express.js" are one framework; stemming it would make "expressed" match.
    if word.isalpha() and word.endswith("js") and len(word) > 4:
        return f"{word[:-2]}.js"
    if not word.isalpha() or word.endswith("ss"):
        return word
    for suffix in ("ations", "ation", "ments", "ment", "ings", "ing", "ed", "s"):
        # A plural keeps three letters, so "APIs" is "API".
        if word.endswith(suffix) and len(word) - len(suffix) >= (3 if suffix == "s" else 4):
            return word[: -len(suffix)]
    return word


def _stems(text_tokens, aliases=False):
    """Stemmed words; with aliases, an entry's bare "Express" also reads as "express.js"."""
    found = set()
    for token in text_tokens:
        for word in {token, *(part for part in token.split("-") if part)}:
            stem = _stem(word)
            found.add(stem)
            if aliases and stem.endswith(".js"):
                found.add(stem[:-3])
            elif aliases and word.isalpha():
                found.add(f"{word}.js")
    return found


_IGNORED = {_stem(word) for word in (*LEVEL_WORDS, "integration")} | _STOP_WORDS


@lru_cache(maxsize=4096)
def skill_names(skill):
    """Each word set that names the skill, from "Git/GitHub", "Flutter (Dart)" or
    "Claude, GPT and Gemini integration"; an entry naming any one of them shows the skill."""
    inner = re.findall(r"\(([^)]*)\)", skill)
    names = []
    for chunk in [re.sub(r"\([^)]*\)", " ", skill), *inner]:
        parts = re.split(r",|\s+(?:and|&)\s+", chunk) if "," in chunk else [chunk]
        for part in parts:
            names.append(part)
            # "Git/GitHub" and "Unix/Linux Command Basics" name each side on its own.
            names += [
                side
                for pair in re.findall(r"[\w.+#-]+(?:/[\w.+#-]+)+", part)
                for side in pair.split("/")
                if len(side) > 1
            ]
    words = [_stems(tokens(name)) for name in names]
    keys = [frozenset(name - _IGNORED) for name in words]
    # "(basics)" alone names nothing; only a skill made of such words keeps them.
    if not any(keys):
        keys = [frozenset(name - _STOP_WORDS) for name in words]
    return tuple(dict.fromkeys(key for key in keys if key))


def skill_label(skill):
    """How a skill reads in a query: "Docker (basics)" searches as "Docker"."""
    label = re.sub(rf"\b(?:{'|'.join(LEVEL_WORDS)})\b", " ", skill, flags=re.I)
    label = re.sub(r"\(\s*[,\s]*\)", " ", label)
    return re.sub(r"\s+", " ", label).strip(" ,") or skill


# All words of one of the skill's names, in any order, so "RESTful APIs" shows "RESTful API".
def _mentions(skill, text_tokens):
    words = _stems(text_tokens, aliases=True)
    return any(key <= words for key in skill_names(skill))


def _evidence_votes(profile, target_roles, with_experience=True, hyde=False):
    """Weight each query by resume evidence within its family's vote; weights sum to 1.

    Without experience, entries only weight the skill queries and are never searched.
    With hyde, generated job ads take the role vote; the titles return if generation fails.
    """
    data = profile if isinstance(profile, dict) else profile.model_dump()
    config = retrieval_weights()
    this_year = date.today().year
    roles = list(
        dict.fromkeys(str(role).strip() for role in target_roles if str(role).strip())
    )
    role_tokens = [tokens(role) for role in roles]
    seniority = re.compile("|".join(LEVEL_PATTERNS.values()))
    # Two-letter words count: "AI", "ML", "UI" and "QA" name the work.
    role_words = {
        word
        for role in roles
        for word in tokens(seniority.sub(" ", role.casefold()))
        if len(word) > 1
    }
    entries = list(
        dict.fromkeys(
            str(entry).strip()
            for entry in [
                *(data.get("work_history") or []),
                *(
                    entry
                    for section in data.get("sections") or []
                    for entry in section.get("entries") or []
                ),
                *(data.get("projects") or []),
                *(data.get("education") or []),
            ]
            if str(entry).strip()
        )
    )
    found = {
        str(item.get("entry") or "").strip(): item
        for item in data.get("entry_evidence") or []
    }
    # Extracted skills join the entry's own words; an entry edited since
    # extraction no longer matches and falls back to its words alone.
    entry_tokens = {
        entry: tokens(
            "\n".join(
                [
                    entry,
                    *(found.get(entry, {}).get("hard_skills") or []),
                    *(found.get(entry, {}).get("soft_skills") or []),
                ]
            )
        )
        for entry in entries
    }

    # Like inverse document frequency: a role word most entries share ("and", "of") says nothing.
    role_words = {
        word
        for word in role_words
        if sum(word in entry_tokens[entry] for entry in entries) <= max(2, len(entries) / 2)
    }

    def clean(values):
        return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))

    def proven(skill):
        return [entry for entry in entries if _mentions(skill, entry_tokens[entry])]

    def strength(entry):
        item = found.get(entry) or {}
        types = config["entry_types"]
        return _recency_factor(
            item.get("end") or entry, this_year, config["recency"]
        ) * types.get(item.get("type") or "untyped", types["untyped"])

    def wanted(skill):
        return any(_mentions(skill, words) for words in role_tokens)

    def score(skill):
        shown_in = proven(skill)
        listed = config["listed_skill"] if shown_in or with_experience else config["listed_only"]
        return (listed + sum(strength(entry) for entry in shown_in)) * (
            config["role_skill_boost"] if wanted(skill) else 1.0
        )

    skills = clean(data.get("tech_skills") or [])
    shown = {}
    if not with_experience:
        # Entry text is not searched, so skills only an entry shows join the skill queries.
        # "Express" in an entry is the listed "ExpressJS", so it is not added twice.
        def loose(skill):
            return {frozenset(word.removesuffix(".js") for word in key) for key in skill_names(skill)}

        listed = {key for skill in skills for key in loose(skill)}
        for entry in entries:
            for skill in clean(found.get(entry, {}).get("hard_skills") or []):
                if listed.isdisjoint(loose(skill)):
                    shown.setdefault(skill.lower(), skill)
                    listed.update(loose(skill))
        skills += list(shown.values())
    evidence = {skill: score(skill) for skill in skills}
    # Under evidence, listed-only skills would pull in jobs for work the resume never shows;
    # the skills builder keeps every skill and lets the low listed_only score rank them last.
    kept = (
        {skill for skill in skills if proven(skill) or wanted(skill)} or set(skills)
        if with_experience
        else set(skills)
    )

    by_key = {skill.lower(): skill for skill in skills}
    groups, grouped = [], set()
    for group in data.get("skill_groups") or []:
        keys = dict.fromkeys(str(skill).strip().lower() for skill in group.get("skills") or [])
        members = [by_key[key] for key in keys if key in by_key and key not in grouped]
        grouped.update(keys)
        if members:
            groups.append(
                (
                    str(group.get("name") or "").strip(),
                    members,
                    str(group.get("query") or "").strip(),
                )
            )
    # A skill only entries show joins the group whose skills those entries use most,
    # so "Other skills" does not become one blurred query of unrelated work.
    for key, skill in shown.items():
        if key in grouped:
            continue
        uses = [
            entry
            for entry in entries
            if key in {str(s).strip().lower() for s in found.get(entry, {}).get("hard_skills") or []}
        ]
        counts = [
            sum(_mentions(member, entry_tokens[entry]) for entry in uses for member in members)
            for _, members, _ in groups
        ]
        if counts and max(counts):
            index = counts.index(max(counts))
            name, members, _ = groups[index]
            # The written sentence does not name the added skill, so the group lists its skills.
            groups[index] = (name, [*members, skill], "")
            grouped.add(key)
    rest = [skill for skill in skills if skill.lower() not in grouped]
    if rest:
        groups.append(("Other skills" if groups else "", rest, ""))
    skill_queries = {}
    for name, members, sentence in groups:
        strong = sorted(
            (skill for skill in members if skill in kept), key=evidence.get, reverse=True
        )
        if not strong:
            continue
        # The written sentence names every group skill, so use it only when none were dropped;
        # otherwise list them, strongest first, without level words.
        if sentence and len(strong) == len(members):
            text = sentence
        else:
            labels = ", ".join(skill_label(skill) for skill in strong)
            text = f"{name}: {labels}" if name else labels
        members = strong
        # The average, not the sum, so a long list of skills does not outweigh a short,
        # strongly proven one.
        skill_queries[text] = sum(evidence[skill] for skill in members) / len(members)
    # Keyword lines weigh like the groups, by the average skill they name; a line naming
    # no kept skill is unsupported by the resume and dropped.
    for line in clean(data.get("keyword_queries") or []):
        named = [skill for skill in kept if _mentions(skill, tokens(line))]
        if named and line not in skill_queries:
            skill_queries[line] = sum(evidence[skill] for skill in named) / len(named)

    def relevance(entry):
        words = set(entry_tokens[entry])
        hits = sum(_mentions(skill, entry_tokens[entry]) for skill in skills)
        limits = config["relevance"]
        return max(
            limits["floor"], min(1.0, (hits + len(role_words & words)) / limits["full_at"])
        )

    experience = sorted(
        (
            (entry, strength(entry) * relevance(entry))
            for entry in entries
        ),
        key=lambda item: item[1],
        reverse=True,
    )[: int(config["experience_queries"])]

    # Shown soft skills lead; listed-only ones are used when no entry shows any.
    soft = clean(
        [
            *(data.get("soft_skills") or []),
            *(skill for entry in entries for skill in found.get(entry, {}).get("soft_skills") or []),
        ]
    )
    soft = sorted(
        [skill for skill in soft if proven(skill)] or soft, key=score, reverse=True
    )
    soft_query = {f"Soft skills: {', '.join(soft)}": 1.0} if soft else {}

    def experience_text(entry):
        item = found.get(entry) or {}
        summary = str(item.get("summary") or "").strip()
        used = ", ".join(clean(item.get("hard_skills") or []))
        if not summary:
            return entry
        return f"{summary} Using {used}." if used else summary

    role_queries = {role: 1.0 for role in roles}
    if hyde and config["votes"]["roles"]:
        from backend.search.hyde import HYDE_PREFIX, job_ads

        ads = job_ads(
            roles,
            [skill_label(skill) for skill in sorted(kept, key=evidence.get, reverse=True)[:8]],
            [experience_text(entry) for entry, _ in experience[:2]],
            data.get("years_of_experience"),
            data.get("career_level") or "unknown",
        )
        if ads:
            role_queries = {
                f"{HYDE_PREFIX}{ad}": share for ad, share in zip(ads, (0.4, 0.35, 0.25))
            }

    votes = defaultdict(float)
    for scored, vote in (
        (role_queries, config["votes"]["roles"]),
        (skill_queries, config["votes"]["skills"]),
        (soft_query, config["votes"]["soft_skills"]),
        (
            {experience_text(entry): weight for entry, weight in experience}
            if with_experience
            else {},
            config["votes"]["experience"],
        ),
    ):
        # A family set to zero votes is not searched at all.
        if not vote:
            continue
        total = sum(scored.values())
        for query, weight in scored.items():
            votes[query] += vote * weight / total
    if not votes:
        focused = profile_embedding_text(data)
        if focused:
            votes[focused] = 1.0
    # Votes are shares, so all weights sum to 1.
    total = sum(votes.values())
    return {query: weight / total for query, weight in votes.items()}


def _legacy_queries(profile, target_roles=()):
    data = profile if isinstance(profile, dict) else profile.model_dump()
    focused = profile_embedding_text(data)
    queries = [str(role).strip() for role in target_roles if str(role).strip()]
    if data.get("tech_skills"):
        queries.append(" ".join(data["tech_skills"]))
    recent = (
        focused.partition("Recent work: ")[2]
        .split("\nTechnical skills:")[0]
        .split("\nPreferred domains:")[0]
    )
    if recent:
        queries.append(recent)
    # Projects, certifications and education share the experience vote with recent work.
    evidence = [
        entry
        for section in data.get("sections") or []
        for entry in section.get("entries") or []
    ] + list(data.get("projects") or []) + list(data.get("education") or [])
    if evidence:
        queries.append("\n".join(evidence))
    if not queries and focused:
        queries.append(focused)
    return list(dict.fromkeys(queries))


def _legacy_weights(profile, target_roles=()):
    data = profile if isinstance(profile, dict) else profile.model_dump()
    roles = list(
        dict.fromkeys(str(role).strip() for role in target_roles if str(role).strip())
    )
    background = _legacy_queries(data)
    skills = " ".join(data.get("tech_skills") or [])
    groups = [roles]
    if skills:
        groups.append([skills])
    recent = [query for query in background if query != skills]
    if recent:
        groups.append(recent)
    weights = defaultdict(float)
    for group in groups:
        for query in group:
            weights[query] += 1 / len(group)
    return dict(weights)


QUERY_BUILDERS = ("evidence", "skills", "legacy", "hyde")
# Searches use hyde unless QUERY_BUILDER says otherwise; a failed ad generation falls back to
# the evidence builder's role titles.
DEFAULT_QUERY_BUILDER = "hyde"


# QUERY_BUILDER=skills searches skills only, with experience as their weight; legacy keeps the
# pre-evidence queries for side-by-side comparison; hyde is evidence with generated job ads
# for roles. A typo must not silently run another builder.
def _builder(builder):
    name = (builder or os.getenv("QUERY_BUILDER", DEFAULT_QUERY_BUILDER)).strip().lower()
    if name not in QUERY_BUILDERS:
        raise ValueError(f"QUERY_BUILDER must be one of: {', '.join(QUERY_BUILDERS)}")
    return name


# Build distinct role, skill-group and experience queries to capture different match signals.
def retrieval_queries(profile, target_roles=(), builder=None):
    name = _builder(builder)
    if name == "legacy":
        return _legacy_queries(profile, target_roles)
    return list(retrieval_query_weights(profile, target_roles, name))


def retrieval_query_weights(profile, target_roles=(), builder=None):
    """Split each family's vote (see DEFAULT_RETRIEVAL_WEIGHTS) by evidence; weights sum to 1."""
    name = _builder(builder)
    if name == "legacy":
        return _legacy_weights(profile, target_roles)
    return _evidence_votes(
        profile, target_roles, with_experience=name != "skills", hyde=name == "hyde"
    )


# Preserve punctuation that distinguishes technology names during lexical matching.
def tokens(text):
    # Preserve technology names such as C++, C#, .NET and Node.js.
    return re.findall(r"\.?[a-z0-9]+(?:[.+#-][a-z0-9+#]+|[+#]+)*", text.lower())


class BM25Index:
    """Reusable lexical statistics and inverted postings, preserving the BM25 formula."""

    def __init__(self, texts):
        documents = [Counter(tokens(text)) for text in texts]
        self.lengths = [sum(doc.values()) for doc in documents]
        self.average = sum(self.lengths) / max(1, len(self.lengths)) or 1
        self.count = len(documents)
        self.postings = defaultdict(list)
        for index, document in enumerate(documents):
            for term, count in document.items():
                self.postings[term].append((index, count))

    def rank(self, query, limit):
        scores = defaultdict(float)
        # Preserve the original term accumulation order and index tie-break.
        for term in set(tokens(query)):
            postings = self.postings.get(term, ())
            if not postings:
                continue
            idf = math.log(
                1 + (self.count - len(postings) + 0.5) / (len(postings) + 0.5)
            )
            for index, count in postings:
                scores[index] += (
                    idf
                    * count
                    * 2.5
                    / (count + 1.5 * (0.25 + 0.75 * self.lengths[index] / self.average))
                )
        return [
            index
            for index, score in sorted(
                scores.items(), key=lambda item: (-item[1], item[0])
            )
            if score > 0
        ][:limit]


def bm25_rank(texts, query, limit):
    """Compatibility helper for callers with a single query."""
    return BM25Index(texts).rank(query, limit)


# Combine rank positions so lexical and semantic scores need not share a scale.
def reciprocal_rank_fusion(rankings, limit, constant=60, weights=None):
    scores = defaultdict(float)
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("One weight is required per ranking")
    for index, ranking in enumerate(rankings):
        for rank, key in enumerate(dict.fromkeys(ranking), 1):
            scores[key] += (weights[index] if weights is not None else 1) / (
                constant + rank
            )
    return sorted(scores, key=lambda key: (-scores[key], str(key)))[:limit]
