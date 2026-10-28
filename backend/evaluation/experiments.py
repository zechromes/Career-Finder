"""In-memory experiments; never mutate production workspaces or vector indexes."""

import copy
import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from backend import runs
from backend.schemas.experiments import ExperimentResult, ExperimentDataset
from backend.evaluation.providers import (
    evaluate_jobs,
    evaluation_model_options,
    evaluation_model_id,
)
from backend.evaluation.runtime import classify_failure
from backend.search.ranking import (
    BM25Index,
    reciprocal_rank_fusion,
    retrieval_queries,
    retrieval_query_weights,
)
from backend.search.embedding_text import job_embedding_text

LOCK = threading.RLock()
EXPERIMENTS = {}
ACTIVE = set()
EMBEDDINGS = ["text-embedding-3-small", "text-embedding-3-large"]


def options():
    return {
        "generation_models": evaluation_model_options(),
        "embedding_models": EMBEDDINGS,
    }


def sources():
    with runs.RUNS_LOCK:
        return [
            dict(
                id=key,
                name=value.get("saved_profile_name") or "Workspace " + key[:8],
                job_count=len(value.get("recommendations", []))
                + len(value.get("excluded_recommendations", [])),
            )
            for key, value in runs.RUNS.items()
            if value.get("profile")
            and not value.get("worker_active")
            and value.get("status") != "running"
            and key not in runs.DELETING
        ]


def dataset(source_id):
    """Read original scoped postings without embedding or writing search state."""
    from langchain_core.documents import Document

    with runs.RUNS_LOCK:
        state = runs.RUNS.get(source_id)
        if not state or source_id in runs.DELETING:
            raise HTTPException(404, "Workspace no longer available.")
        if state.get("worker_active") or state.get("status") == "running":
            raise HTTPException(409, "Wait for the workspace search to finish.")
        state = copy.deepcopy(state)
        documents = []
        scope_paths = sorted(
            (runs.RUNS_DIR / source_id).glob("vector_db_search_*/job_scope.json"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
        if scope_paths:
            from langchain_chroma import Chroma
            from chromadb.config import Settings
            from backend.search.shared_index import read_scope, corpus

            try:
                for path in scope_paths:
                    scope = read_scope(path.parent)
                    if not scope or not Path(scope["index_dir"]).is_dir():
                        raise ValueError("Posting index expired.")
                    store = Chroma(
                        persist_directory=scope["index_dir"],
                        embedding_function=None,
                        client_settings=Settings(anonymized_telemetry=False),
                    )
                    for doc in copy.deepcopy(corpus(store, scope)[1]):
                        doc.metadata["_experiment_embedding_text"] = doc.page_content
                        documents.append(doc)
            except Exception:
                raise HTTPException(
                    409,
                    "The collected posting pool is unavailable or expired. Start a new search.",
                ) from None
            scope_name = "Collected posting pools from this workspace"
        else:
            scope_name = "Saved results only; not the full collected pool"
            for row in state.get("recommendations", []) + state.get(
                "excluded_recommendations", []
            ):
                description = row.get("job_description") or ""
                if description.strip():
                    documents.append(
                        Document(
                            page_content=description,
                            metadata={
                                "title": row.get("title", ""),
                                "company": row.get("company", ""),
                                "url": row.get("apply_url", ""),
                                "job_description": description,
                                "location": row.get("location", ""),
                            },
                        )
                    )
    unique = {}
    for doc in documents:
        original = (
            doc.metadata.get("original_content")
            or doc.metadata.get("job_description")
            or doc.page_content
        )
        if not original.strip():
            continue
        doc.page_content = original
        doc.metadata.setdefault("job_description", original)
        url = doc.metadata.get("url", "")
        identity_url = url if url.startswith(("https://", "http://")) else ""
        key = hashlib.sha256(
            (
                identity_url
                or (
                    doc.metadata.get("title", "")
                    + doc.metadata.get("company", "")
                    + original
                )
            ).encode()
        ).hexdigest()[:24]
        unique[key] = doc
    if not unique:
        raise HTTPException(
            422, "This workspace has no saved posting descriptions to evaluate."
        )
    if len(unique) > 500:
        raise HTTPException(
            422, "Choose a workspace with at most 500 postings for this experiment."
        )
    profile = state.get("profile") or {}
    roles = (state.get("preferences") or {}).get("queries", [])
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "profile": profile,
                "roles": roles,
                "jobs": [
                    (key, doc.page_content, doc.metadata) for key, doc in unique.items()
                ],
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    public = ExperimentDataset(
        source_id=source_id,
        fingerprint=fingerprint,
        scope=scope_name,
        jobs=[
            dict(
                id=key,
                title=doc.metadata.get("title", ""),
                company=doc.metadata.get("company", ""),
                description=doc.page_content,
            )
            for key, doc in unique.items()
        ],
    )
    return public, profile, roles, unique


def metrics(labels, pool, selected):
    selected, positive = set(selected), {key for key, value in labels.items() if value}
    judged = selected & labels.keys()
    return dict(
        label_coverage=len(labels) / len(pool) if pool else 0,
        observed_recall_at_k=(
            len(positive & selected) / len(positive) if positive else None
        ),
        precision_on_labeled=len(positive & selected) / len(judged) if judged else None,
        missed_labeled_positives=sorted(positive - selected),
        unlabeled_selected=len(selected - labels.keys()),
    )


def rank(profile, roles, documents, model, top_k, stopped):
    """Exact cosine + existing BM25/weighted RRF, isolated from production Chroma."""
    import numpy as np
    from langchain_openai import OpenAIEmbeddings

    queries = retrieval_queries(profile, roles)
    if not queries:
        raise ValueError("No retrieval query evidence.")
    texts = [
        doc.metadata.get("_experiment_embedding_text")
        or job_embedding_text(
            dict(
                title=doc.metadata.get("title", ""),
                description=doc.metadata.get("job_description", doc.page_content),
            )
        )
        for doc in documents
    ]
    embedder = OpenAIEmbeddings(model=model, request_timeout=90, max_retries=1)
    vectors = []
    for offset in range(0, len(texts), 32):
        if stopped():
            return []
        vectors.extend(embedder.embed_documents(texts[offset : offset + 32]))
    if stopped():
        return []
    query_vectors = embedder.embed_documents(queries)
    matrix = np.asarray(vectors, dtype=float)
    matrix /= np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
    lexical, rankings, weights = BM25Index(texts), [], []
    query_weights = retrieval_query_weights(profile, roles)
    window = min(len(texts), max(top_k * 3, 50))
    for query, vector in zip(queries, query_vectors):
        vector = np.asarray(vector, dtype=float)
        scores = matrix @ (vector / max(float(np.linalg.norm(vector)), 1e-12))
        rankings.extend(
            [
                np.argsort(-scores, kind="stable")[:window].tolist(),
                lexical.rank(query, window),
            ]
        )
        weights.extend([query_weights.get(query, 1) / 2] * 2)
    return reciprocal_rank_fusion(rankings, len(texts), weights=weights)[:top_k]


def _expire():
    for key, value in list(EXPERIMENTS.items()):
        if key not in ACTIVE and time.time() - value["created_at"] > 86400:
            del EXPERIMENTS[key]
    finished = sorted(
        (key for key in EXPERIMENTS if key not in ACTIVE),
        key=lambda key: EXPERIMENTS[key]["created_at"],
    )
    for key in finished[: -(20 - len(ACTIVE))]:
        del EXPERIMENTS[key]


def get(experiment_id):
    with LOCK:
        _expire()
        if experiment_id not in EXPERIMENTS:
            raise HTTPException(404, "Experiment expired or server restarted.")
        return copy.deepcopy(EXPERIMENTS[experiment_id])


def cancel(experiment_id):
    with LOCK:
        get(experiment_id)
        if experiment_id in ACTIVE:
            EXPERIMENTS[experiment_id].update(
                status="cancelled",
                message="Cancelled. In-flight provider calls may finish; no further trials will start.",
            )
        return get(experiment_id)


def start(body):
    public, profile, roles, documents = dataset(body.source_id)
    if body.fingerprint != public.fingerprint:
        raise HTTPException(
            409, "Workspace changed. Reload the dataset before running."
        )
    if set(body.labels) - documents.keys():
        raise HTTPException(422, "Labels must refer to jobs in this dataset.")
    if body.phase != "generation" and not retrieval_queries(profile, roles):
        raise HTTPException(
            422, "This workspace has no profile evidence for retrieval."
        )
    with LOCK:
        _expire()
        if ACTIVE:
            raise HTTPException(
                409, "Another experiment is still running. Wait for it to finish."
            )
        key = uuid.uuid4().hex
        result = ExperimentResult(
            id=key,
            status="running",
            source_id=body.source_id,
            created_at=time.time(),
            fingerprint=public.fingerprint,
            scope=public.scope,
            phase=body.phase,
            top_k=body.top_k,
            pool_size=len(documents),
            settings=body,
            message="Starting experiment.",
        ).model_dump()
        EXPERIMENTS[key] = result
        ACTIVE.add(key)
        _expire()
        try:
            threading.Thread(
                target=execute, args=(key, body, profile, roles, documents), daemon=True
            ).start()
        except Exception:
            ACTIVE.discard(key)
            EXPERIMENTS.pop(key, None)
            raise HTTPException(503, "Could not start experiment.") from None
        return copy.deepcopy(result)


def execute(key, body, profile, roles, documents):
    from backend.cli import profile_to_context
    from backend.schemas.resume import ResumeProfile
    from backend.evaluation.requirements import RequirementLoader

    def stopped():
        with LOCK:
            return EXPERIMENTS[key]["status"] == "cancelled"

    def publish(section, value):
        with LOCK:
            if not stopped():
                EXPERIMENTS[key][section].append(value)

    pool, docs = list(documents), list(documents.values())
    selected = pool[: body.top_k]
    failed = False
    try:
        if body.phase != "generation":
            for index, model in enumerate(body.embedding_models):
                if stopped():
                    return
                with LOCK:
                    EXPERIMENTS[key]["message"] = "Retrieving with " + model
                begin = time.monotonic()
                error = None
                try:
                    indices = rank(profile, roles, docs, model, body.top_k, stopped)
                    ranked = [pool[i] for i in indices]
                except Exception as exc:
                    error, ranked, failed = str(classify_failure(exc)), [], True
                if index == 0:
                    selected = ranked
                publish(
                    "retrieval",
                    dict(
                        model=model,
                        seconds=time.monotonic() - begin,
                        ranked_ids=ranked,
                        metrics=metrics(body.labels, pool, ranked),
                        error=error,
                    ),
                )
        if body.phase != "retrieval" and selected:
            loader = RequirementLoader(stopped)
            context = profile_to_context(ResumeProfile.model_validate(profile))
            for provider in body.providers:
                if stopped():
                    return
                with LOCK:
                    EXPERIMENTS[key]["message"] = "Assessing jobs with " + provider
                begin, errors, results = time.monotonic(), [], []
                try:
                    results = evaluate_jobs(
                        context,
                        [documents[item] for item in selected],
                        include_all=True,
                        target_roles=roles,
                        provider=provider,
                        candidate_profile=profile,
                        should_cancel=stopped,
                        requirement_loader=loader,
                        log_jobs=False,
                        on_error=lambda doc, error: errors.append(
                            str(classify_failure(error))
                        ),
                    )
                except Exception as exc:
                    errors.append(str(classify_failure(exc)))
                if len(results) < len(selected) and not errors and not stopped():
                    errors.append("Some assessments did not complete.")
                failed |= bool(errors)
                # Match assessments to the fixed dataset, including postings without URLs.
                strong = []
                for result in results:
                    matches = [
                        item
                        for item in selected
                        if result.get("apply_url", "")
                        == documents[item].metadata.get("url", "")
                        and result.get("title", "")
                        == documents[item].metadata.get("title", "")
                        and result.get("company", "")
                        == documents[item].metadata.get("company", "")
                        and (
                            "job_description" not in result
                            or result["job_description"]
                            == documents[item].metadata.get("job_description")
                        )
                    ]
                    if len(matches) == 1:
                        result["jobId"] = matches[0]
                        if result.get("fit_category") == "strong_match":
                            strong.append(matches[0])
                publish(
                    "generation",
                    dict(
                        provider=provider,
                        model=evaluation_model_id(provider),
                        seconds=time.monotonic() - begin,
                        input_ids=selected,
                        results=results,
                        errors=errors,
                        metrics=metrics(body.labels, pool, strong),
                    ),
                )
        with LOCK:
            if not stopped():
                completed = any(
                    not trial["error"] for trial in EXPERIMENTS[key]["retrieval"]
                ) or any(trial["results"] for trial in EXPERIMENTS[key]["generation"])
                EXPERIMENTS[key].update(
                    status=(
                        ("partial" if completed else "failed") if failed else "complete"
                    ),
                    message="Experiment finished. Quality metrics require human labels; timings include provider retries and shared requirement extraction.",
                )
    except Exception as exc:
        with LOCK:
            if not stopped():
                EXPERIMENTS[key].update(
                    status="failed", message=str(classify_failure(exc))
                )
    finally:
        with LOCK:
            ACTIVE.discard(key)
