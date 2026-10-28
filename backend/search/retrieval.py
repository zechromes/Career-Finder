"""Retrieve ranked postings and apply conservative search filters."""

from backend.observability import stage
import re
import copy
from typing import Optional
from backend.evaluation.candidate_fit import (
    title_exceeds_candidate_level,
    experience_context,
)
from backend.search.ranking import reciprocal_rank_fusion
from backend.search.shared_index import read_scope, corpus


@stage("jobs.retrieve")
def retrieve_relevant_jobs(
    resume_context: str,
    persist_dir: str = "./vector_db",
    top_k: int = 15,
    locations: Optional[list[str]] = None,
    queries: Optional[list[str]] = None,
    candidate_profile: Optional[dict] = None,
    query_weights: Optional[dict[str, float]] = None,
    dismissal_feedback: Optional[dict] = None,
):
    """Return semantically relevant jobs that also match requested locations."""
    from langchain_chroma import Chroma
    from langchain_openai import OpenAIEmbeddings

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    scope = read_scope(persist_dir)
    settings = {}
    if scope:
        from chromadb.config import Settings

        settings["client_settings"] = Settings(anonymized_telemetry=False)
    vector_store = Chroma(
        persist_directory=scope["index_dir"] if scope else persist_dir,
        embedding_function=embeddings,
        **settings,
    )
    search_filter = (
        {"filter": {"version_id": {"$in": scope["ids"]}}}
        if scope and scope["ids"]
        else {}
    )

    # A top_k of zero means the UI requested every relevant posting. Chroma's
    # collection count lets us retrieve the complete current search corpus.
    collection_count = len(scope["ids"]) if scope else vector_store._collection.count()
    if not collection_count:
        return []

    prioritize_level = (
        candidate_profile is not None
        and experience_context(resume_context, candidate_profile)[1]
    )
    search_k = (
        collection_count
        if top_k == 0 or locations or prioritize_level
        else min(collection_count, max(top_k * 3, 50))
    )
    query_texts = list(
        dict.fromkeys(q for q in (queries or [resume_context]) if q.strip())
    )

    if not query_texts:
        return []

    # Fuse semantic and keyword rankings across the candidate’s distinct query signals.
    if queries:
        ids, documents, lexical = corpus(vector_store, scope)
        identity = lambda doc: (doc.metadata.get("url", ""), doc.page_content)
        index_by_identity = {
            identity(doc): index for index, doc in enumerate(documents)
        }
        rankings = []

        for query in query_texts:
            semantic = vector_store.similarity_search(
                query, k=search_k, **search_filter
            )
            rankings.append(
                [
                    index_by_identity[identity(doc)]
                    for doc in semantic
                    if identity(doc) in index_by_identity
                ]
            )
            rankings.append(lexical.rank(query, search_k))
        weights = (
            [
                query_weights.get(query, 1.0) / 2
                for query in query_texts
                for _ in range(2)
            ]
            if query_weights is not None
            else None
        )
        ranked = reciprocal_rank_fusion(rankings, len(ids), weights=weights)

        if top_k == 0:
            ranked_set = set(ranked)
            ranked.extend(index for index in range(len(ids)) if index not in ranked_set)
        relevant_docs = [documents[index] for index in ranked]
    else:
        relevant_docs = vector_store.similarity_search(
            resume_context, k=search_k, **search_filter
        )
    # A posting can still appear more than once if an older vector store was
    # created before ingestion deduplication was enabled. Remove duplicates at
    # retrieval time as a second line of defence.
    unique_docs = []
    seen = set()
    for document in relevant_docs:
        metadata = document.metadata
        url = (metadata.get("url") or "").strip().lower().rstrip("/")
        key = (
            url
            if url and not url.startswith("no url")
            else "|".join(
                str(metadata.get(field, "")).strip().lower()
                for field in ("title", "company", "location")
            )
        )
        if key not in seen:
            seen.add(key)
            unique_docs.append(document)
    relevant_docs = unique_docs
    if locations:
        filtered_docs = [
            document
            for document in relevant_docs
            if _location_matches(document.metadata.get("location", ""), locations)
        ]
        relevant_docs = filtered_docs
    if dismissal_feedback:
        from backend.search.preferences import prioritize_preferences

        relevant_docs = prioritize_preferences(relevant_docs, dismissal_feedback)
    if prioritize_level:
        # Stable partition keeps relevance order within each group. Other levels
        # remain available when the shortlist has room, including top_k=0.
        relevant_docs.sort(
            key=lambda doc: title_exceeds_candidate_level(
                doc.metadata.get("title", ""), resume_context, candidate_profile
            )
        )
    # Apply the requested evaluation budget after deduplication and level prioritization.
    if top_k:
        relevant_docs = relevant_docs[:top_k]
    # Retrieval uses focused vectors; evaluation receives the unabridged posting.
    relevant_docs = copy.deepcopy(relevant_docs)
    for document in relevant_docs:
        if document.metadata.get("original_content"):
            document.page_content = document.metadata["original_content"]
    print(
        f"Retrieved {len(relevant_docs)} semantically relevant jobs from the database."
    )
    return relevant_docs


@stage("jobs.screen_experience")
def screen_jobs_for_experience(
    profile: dict, jobs: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Remove only obvious experience mismatches before expensive processing.

    Domain changes are deliberately retained for Claude review. This gate is
    conservative and focuses on explicit seniority and years-of-experience
    signals in the job title/description.
    """
    years = max(0, int(profile.get("years_of_experience") or 0))
    profile_terms = {
        token
        for value in [
            *(profile.get("preferred_domains") or []),
            *(profile.get("tech_skills") or []),
        ]
        for token in re.findall(r"[a-z0-9]+", str(value).lower())
    }
    executive_terms = {"principal", "director", "head", "chief", "vp", "vice president"}
    advanced_terms = {"senior", "sr", "lead", "staff", "manager"}
    accepted = []
    excluded = []

    for job in jobs:
        title = str(job.get("title", ""))
        description = str(job.get("description", ""))
        role_text = f"{title} {description}".lower()
        title_tokens = set(re.findall(r"[a-z0-9]+", title.lower()))
        reason = ""

        # Do not treat a different domain as a hard failure: a user may be
        # intentionally changing careers. Profile terms provide context to
        # semantic matching and Claude, but never cause a pre-screen reject.
        is_domain_pivot = not title_tokens.intersection(profile_terms)
        required_years = [
            int(value) for value in re.findall(r"(\d+)\s*\+?\s*years?", role_text)
        ]
        if required_years and max(required_years) > years + 2:
            reason = "required experience exceeds profile"
        elif (
            any(term in title_tokens for term in executive_terms)
            or "vice president" in title.lower()
        ) and years < 7:
            reason = "seniority mismatch"
        elif any(term in title_tokens for term in advanced_terms) and years < 3:
            reason = "seniority mismatch"

        if reason:
            excluded.append(
                {
                    "title": job.get("title", "Unknown Title"),
                    "company": job.get("company", "Unknown Company"),
                    "reason": reason,
                }
            )
        else:
            # Preserve a lightweight signal for the evaluator and future
            # reporting without excluding a possible career transition.
            accepted.append(
                {
                    **job,
                    "pre_screen_note": (
                        "possible career pivot" if is_domain_pivot else ""
                    ),
                }
            )

    return accepted, excluded


def _location_matches(job_location: str, requested_locations: list[str]) -> bool:
    from backend.search.locations import location_matches

    return location_matches(job_location, requested_locations)
