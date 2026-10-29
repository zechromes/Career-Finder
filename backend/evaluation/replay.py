"""Replay a frozen dataset's retrieval under each seniority rule, scored with human labels."""

import copy
import json
import time
from fastapi import HTTPException
from backend import runs
from backend.evaluation import experiments, review_datasets
from backend.evaluation.candidate_fit import (
    posting_exceeds_candidate_level,
    title_exceeds_candidate_level,
)

EMBEDDING_MODEL = "text-embedding-3-small"
RULES = [
    (
        "title_only",
        "Title only (until 28 Oct 2026)",
        lambda title, text, context, profile: title_exceeds_candidate_level(
            title, context, profile
        ),
    ),
    ("stated_years", "Stated years (current)", posting_exceeds_candidate_level),
]


def _relevance(data):
    """Rank each recorded search's pool by relevance alone; embeds only the role queries."""
    from backend.search.embedding_text import profile_embedding_text
    from backend.search.ranking import retrieval_queries, retrieval_query_weights
    from backend.search.retrieval import retrieve_relevant_jobs

    with runs.RUNS_LOCK:
        state = copy.deepcopy(runs.RUNS.get(data.source_id))
    scopes = sorted(
        (runs.RUNS_DIR / data.source_id).glob("vector_db_search_*/job_scope.json"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )
    if not state or not scopes:
        raise HTTPException(
            409, "The original search is no longer available, so it cannot be replayed."
        )
    profile, roles = data.profile.model_dump(), data.target_roles
    pool = {job.id for job in data.jobs}
    searches = []
    for path in scopes:
        # top_k=0 without a profile returns the full relevance order, before
        # seniority ordering and the shortlist cut, which the rules apply below.
        docs = retrieve_relevant_jobs(
            profile_embedding_text(profile),
            persist_dir=str(path.parent),
            top_k=0,
            queries=retrieval_queries(profile, roles),
            query_weights=retrieval_query_weights(profile, roles),
        )
        order = [experiments.posting_id(doc.metadata, doc.page_content) for doc in docs]
        searches.append([key for key in dict.fromkeys(order) if key in pool])
    inputs = state.get("search_inputs") or state.get("preferences") or {}
    return dict(
        embedding_model=EMBEDDING_MODEL,
        ranked_at=time.time(),
        top_k=int(inputs.get("top_k") or 15),
        searches=searches,
    )


def replay(identifier):
    from backend.search.embedding_text import profile_embedding_text

    bundle = review_datasets.read(identifier)
    data = bundle.dataset
    path = review_datasets._path(identifier) / "relevance.json"
    try:
        saved = json.loads(path.read_text())
    except FileNotFoundError:
        # The ranking is frozen with the dataset, so only the first replay embeds.
        saved = _relevance(data)
        with review_datasets.LOCK:
            review_datasets._write(path, saved)
    jobs = {job.id: job for job in data.jobs}
    labels = review_datasets.fit_labels(
        data,
        {key: row for key, row in bundle.labels.jobs.items() if not row.ai_assisted},
    )
    original = {job.id for job in data.jobs if job.previously_shortlisted}
    profile = data.profile.model_dump()
    context = profile_embedding_text(profile)
    ranked = {key for order in saved["searches"] for key in order}
    rules = []
    for key, name, exceeds in RULES:
        shortlist = []
        for order in saved["searches"]:
            # Stable partition, as in retrieval: relevance order holds within each group.
            ordered = sorted(
                order,
                key=lambda job: exceeds(
                    jobs[job].title, jobs[job].description, context, profile
                ),
            )
            # Appended searches cut first, then skip postings already assessed.
            shortlist.extend(
                job for job in ordered[: saved["top_k"]] if job not in shortlist
            )
        added = [job for job in shortlist if job not in original]
        rules.append(
            dict(
                rule=key,
                name=name,
                shortlist_size=len(shortlist),
                matches_original=(
                    len(original & set(shortlist)) / len(original) if original else None
                ),
                metrics=experiments.metrics(labels, list(jobs), shortlist),
                good_fits_added=[job for job in added if labels.get(job) is True],
                not_fits_added=[job for job in added if labels.get(job) is False],
                unassessed_added=len(added),
            )
        )
    return dict(
        dataset_id=identifier,
        embedding_model=saved["embedding_model"],
        ranked_at=saved["ranked_at"],
        searches=len(saved["searches"]),
        top_k=saved["top_k"],
        unranked=len(set(jobs) - ranked),
        rules=rules,
        limitations=[
            "Retrieval only: jobs a rule adds to the shortlist have no model assessment yet.",
            "Dismissals made before the original search are not replayed, so the title-only "
            "rule may not reproduce the original shortlist exactly; see its match rate.",
            "Recall and precision use partial labels, so they are observed values only.",
        ],
    )
