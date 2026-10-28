"""Offline retrieval benchmark: real Chroma, synthetic vectors, no provider calls.

Measures ANN recall against exact L2 neighbors and application hybrid latency.
These synthetic vectors are NOT human relevance labels or model embeddings.
Run with: python -m scripts.benchmark_retrieval --output /tmp/retrieval.json
"""

import argparse
from collections import Counter
import math
from contextlib import redirect_stdout
import io
import json
from importlib.metadata import version
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import numpy as np
from chromadb.config import Settings
from langchain_chroma import Chroma

from backend.search.retrieval import retrieve_relevant_jobs
from backend.search.collection_cache import CollectionCache
from backend.search.ranking import tokens, reciprocal_rank_fusion


def summarize(samples):
    return {
        "samples": len(samples),
        "p50_ms": round(float(np.percentile(samples, 50)), 3),
        "p95_ms": round(float(np.percentile(samples, 95)), 3),
    }


def baseline_bm25(texts, query, limit):
    """Frozen pre-optimization implementation for paired ranking comparisons."""
    documents = [Counter(tokens(text)) for text in texts]
    lengths = [sum(doc.values()) for doc in documents]
    average = sum(lengths) / max(1, len(lengths)) or 1
    frequency = Counter(term for doc in documents for term in doc)
    scores = []
    for index, doc in enumerate(documents):
        score = 0.0
        for term in set(tokens(query)):
            count = doc[term]
            if count:
                idf = math.log(
                    1
                    + (len(documents) - frequency[term] + 0.5) / (frequency[term] + 0.5)
                )
                score += (
                    idf
                    * count
                    * 2.5
                    / (count + 1.5 * (0.25 + 0.75 * lengths[index] / average))
                )
        if score > 0:
            scores.append((index, score))
    return [
        index
        for index, _ in sorted(scores, key=lambda item: (-item[1], item[0]))[:limit]
    ]


def baseline_hybrid(store, query, k):
    """Original full-corpus load, per-query BM25 and RRF; no level/location filters."""
    data = store.get(include=["documents", "metadatas"])
    index_by_url = {meta["url"]: i for i, meta in enumerate(data["metadatas"])}
    search_k = min(len(data["ids"]), max(k * 3, 50))
    semantic = store.similarity_search(query, k=search_k)
    rankings = [
        [index_by_url[doc.metadata["url"]] for doc in semantic],
        baseline_bm25(data["documents"], query, search_k),
    ]
    ranked = reciprocal_rank_fusion(rankings, len(data["ids"]))[:k]
    return [data["metadatas"][i]["url"] for i in ranked]


def benchmark(count=2000, dimensions=128, query_count=30, k=20, seed=42, ef_search=100):
    if min(count, dimensions, query_count, k) < 1 or k > count:
        raise ValueError("Use positive sizes and k <= documents")
    rng = np.random.default_rng(seed)
    roles = [
        "Python backend",
        "Java backend",
        "SQL analytics",
        "React frontend",
        "C++ robotics",
        "JavaScript web",
        "cloud infrastructure",
        "data science",
    ]
    centers = rng.normal(size=(len(roles), dimensions))
    vectors = centers[np.arange(count) % len(roles)] + rng.normal(
        scale=0.7, size=(count, dimensions)
    )
    vectors = (vectors / np.linalg.norm(vectors, axis=1, keepdims=True)).astype(
        np.float32
    )
    queries = centers[np.arange(query_count) % len(roles)] + rng.normal(
        scale=0.5, size=(query_count, dimensions)
    )
    queries = (queries / np.linalg.norm(queries, axis=1, keepdims=True)).astype(
        np.float32
    )
    texts = [
        f"{roles[i % len(roles)]} engineer. Build and maintain systems. Synthetic vacancy {i}."
        for i in range(count)
    ]
    query_texts = [
        f"{roles[i % len(roles)]} skills query {i}" for i in range(query_count)
    ]
    mapping = {
        text: vector.tolist()
        for text, vector in zip(texts + query_texts, np.concatenate([vectors, queries]))
    }

    class FixedEmbeddings:
        def embed_documents(self, values):
            return [mapping[value] for value in values]

        def embed_query(self, value):
            return mapping[value]

    embeddings = FixedEmbeddings()
    ann_times, exact_times, hybrid_times, recalls, missed_counts = [], [], [], [], []
    baseline_times, shared_times, parity = [], [], []
    filtered_times, filtered_recalls = [], []
    with TemporaryDirectory(prefix="career-retrieval-benchmark-") as directory:
        store = Chroma(
            persist_directory=str(Path(directory) / "vectors"),
            embedding_function=embeddings,
            client_settings=Settings(anonymized_telemetry=False),
            collection_configuration={"hnsw": {"ef_search": ef_search}},
        )
        start = perf_counter()
        store.add_texts(
            texts,
            metadatas=[
                {
                    "url": f"https://example.test/jobs/{i}",
                    "original_content": text,
                    "version_id": str(i),
                }
                for i, text in enumerate(texts)
            ],
            ids=[str(i) for i in range(count)],
        )
        index_ms = (perf_counter() - start) * 1000
        configuration = store._collection.configuration
        scope_dir = Path(directory) / "scope"
        scope_dir.mkdir()
        (scope_dir / "job_scope.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "index_dir": str(Path(directory) / "vectors"),
                    "ids": store.get(include=[])["ids"],
                }
            )
        )
        # Exclude one explicit warmup query from query latency percentiles.
        store.similarity_search(query_texts[0], k=k)
        with patch("langchain_openai.OpenAIEmbeddings", return_value=embeddings), patch(
            "langchain_chroma.Chroma",
            side_effect=lambda **kwargs: Chroma(
                **({"client_settings": Settings(anonymized_telemetry=False)} | kwargs)
            ),
        ):
            start = perf_counter()
            with redirect_stdout(io.StringIO()):
                retrieve_relevant_jobs(
                    query_texts[0],
                    persist_dir=str(scope_dir),
                    top_k=k,
                    queries=[query_texts[0]],
                )
            shared_cold_ms = (perf_counter() - start) * 1000
            for query_text, vector in zip(query_texts, queries):
                start = perf_counter()
                exact = set(
                    np.argsort(np.sum((vectors - vector) ** 2, axis=1))[:k].tolist()
                )
                exact_times.append((perf_counter() - start) * 1000)
                start = perf_counter()
                neighbors = store.similarity_search(query_text, k=k)
                ann_times.append((perf_counter() - start) * 1000)
                found = {
                    int(doc.metadata["url"].rsplit("/", 1)[-1]) for doc in neighbors
                }
                recalls.append(len(exact & found) / k)
                missed_counts.append(len(exact - found))
                eligible = np.arange(0, count, 2)
                filtered_k = min(k, len(eligible))
                expected_subset = set(
                    eligible[
                        np.argsort(np.sum((vectors[eligible] - vector) ** 2, axis=1))[
                            :filtered_k
                        ]
                    ].tolist()
                )
                start = perf_counter()
                subset = store.similarity_search(
                    query_text,
                    k=filtered_k,
                    filter={"version_id": {"$in": [str(i) for i in eligible]}},
                )
                filtered_times.append((perf_counter() - start) * 1000)
                found_subset = {
                    int(doc.metadata["url"].rsplit("/", 1)[-1]) for doc in subset
                }
                if not found_subset <= set(eligible.tolist()):
                    raise AssertionError("Posting outside eligible scope returned")
                filtered_recalls.append(
                    len(expected_subset & found_subset) / filtered_k
                )
                start = perf_counter()
                baseline_store = Chroma(
                    persist_directory=str(Path(directory) / "vectors"),
                    embedding_function=embeddings,
                    client_settings=Settings(anonymized_telemetry=False),
                )
                expected = baseline_hybrid(baseline_store, query_text, k)
                baseline_times.append((perf_counter() - start) * 1000)
                start = perf_counter()
                with redirect_stdout(io.StringIO()):
                    retrieve_relevant_jobs(
                        query_text,
                        persist_dir=str(Path(directory) / "vectors"),
                        top_k=k,
                        queries=[query_text],
                    )
                hybrid_times.append((perf_counter() - start) * 1000)
                start = perf_counter()
                with redirect_stdout(io.StringIO()):
                    actual = retrieve_relevant_jobs(
                        query_text,
                        persist_dir=str(scope_dir),
                        top_k=k,
                        queries=[query_text],
                    )
                shared_times.append((perf_counter() - start) * 1000)
                parity.append(expected == [doc.metadata["url"] for doc in actual])
        # Exercise both collection modes on exactly the same synthetic postings.
        jobs = [
            {
                "title": text,
                "description": text,
                "url": f"https://example.test/jobs/{i}",
            }
            for i, text in enumerate(texts)
        ]
        source_calls = 0

        def fetch():
            nonlocal source_calls
            source_calls += 1
            return jobs, True

        cache = CollectionCache(Path(directory) / "collections", ttl=900)
        uncached = CollectionCache(Path(directory) / "disabled", ttl=0)
        for _ in range(2):
            baseline, _ = uncached.collect({"synthetic": seed}, fetch)
        baseline_calls = source_calls
        source_calls = 0
        cold, _ = cache.collect({"synthetic": seed}, fetch)
        warm, hit = cache.collect({"synthetic": seed}, fetch)
        cache_report = {
            "searches_per_mode": 2,
            "uncached_source_calls": baseline_calls,
            "cached_source_calls": source_calls,
            "second_search_cache_hit": hit,
            "identical_posting_pool": baseline == cold == warm,
        }
    return {
        "dataset": {
            "kind": "seeded synthetic clustered vectors and job text",
            "documents": count,
            "dimensions": dimensions,
            "queries": query_count,
            "seed": seed,
            "k": k,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "chromadb": version("chromadb"),
            "langchain_chroma": version("langchain-chroma"),
        },
        "embedding_provider": "none; deterministic synthetic vectors, zero live API calls",
        "hnsw_configuration": configuration,
        "index_build_ms": round(index_ms, 3),
        "exact_vector_baseline": summarize(exact_times),
        "hnsw_vector_search": summarize(ann_times)
        | {
            "mean_ann_recall_at_k": float(np.mean(recalls)),
            "minimum_ann_recall_at_k": min(recalls),
            "missed_exact_neighbors_total": sum(missed_counts),
        },
        "application_hybrid_retrieval": summarize(hybrid_times),
        "filtered_hnsw": summarize(filtered_times)
        | {
            "eligible_documents": len(range(0, count, 2)),
            "mean_ann_recall_at_k": float(np.mean(filtered_recalls)),
            "minimum_ann_recall_at_k": min(filtered_recalls),
        },
        "original_hybrid_baseline": summarize(baseline_times),
        "shared_hybrid_retrieval": summarize(shared_times),
        "shared_corpus_first_query_ms": round(shared_cold_ms, 3),
        "paired_ranking_comparison": {
            "queries": query_count,
            "identical_ordered_shortlists": sum(parity),
            "all_identical": all(parity),
        },
        "collection_cache_comparison": cache_report,
        "human_relevance": {
            "labeled_cases": 0,
            "label_coverage": 0,
            "observed_recall_at_k": None,
            "strong_match_precision": None,
            "missed_relevant_jobs": None,
        },
        "limitations": [
            "ANN recall measures agreement with exact vector neighbors, not candidate fit.",
            "Hybrid latency includes Chroma open/get, Python BM25 and RRF for one query signal; excludes embedding network latency and LLM evaluation.",
            "Warm local timings; no production scraping latency measured. Shared corpus first-query load is reported separately.",
            "No human labels, held-out accuracy evaluation, or real embedding model quality claims.",
            "Collection comparison uses a synthetic source; call reduction is not measured production speedup.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=int, default=2000)
    parser.add_argument("--dimensions", type=int, default=128)
    parser.add_argument("--queries", type=int, default=30)
    parser.add_argument("--k", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ef-search", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = benchmark(
        args.documents, args.dimensions, args.queries, args.k, args.seed, args.ef_search
    )
    serialized = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
