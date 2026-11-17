"""Replay a saved run's retrieval under the legacy, evidence, skills and hyde query builders.

Reuses the run's stored job vectors and prints, per builder, the queries and
weights, the top jobs, and off-target title counts. Query embeddings are a live
OpenAI call, and hyde generates its job ads with a live model call unless they
are cached; job vectors are not re-embedded. These counts are title heuristics,
not human relevance labels. The output contains private run data: keep it local.
Run with: python -m scripts.compare_query_builders <run_id> [--top 20]
"""

import argparse
from contextlib import redirect_stdout
import io
import json
import re

from backend.paths import RUNS_DIR
from backend.search.embedding_text import profile_embedding_text
from backend.search.ranking import retrieval_queries, retrieval_query_weights
from backend.search.retrieval import retrieve_relevant_jobs

OFF_TARGET = {
    "mobile": r"\b(ios|android|mobile|flutter|react native)\b",
    "game dev": r"\b(game|games|gaming|unity|unreal)\b",
    "HR/admin": r"\b(hr|human resources|recruit\w*|admin\w*|payroll)\b",
}


def off_target(titles):
    return {
        name: sum(bool(re.search(pattern, title, re.I)) for title in titles)
        for name, pattern in OFF_TARGET.items()
    }


def compare(run_id, top=20):
    run_dir = RUNS_DIR / run_id
    state = json.loads((run_dir / "state.json").read_text())
    profile = state.get("profile")
    if not profile:
        raise SystemExit("This run has no extracted profile.")
    indexes = sorted(run_dir.glob("vector_db_search_*"), key=lambda path: path.stat().st_mtime)
    if not indexes:
        raise SystemExit("This run has no job index; run a search first.")
    preferences = state.get("preferences") or {}
    roles = preferences.get("queries") or profile.get("preferred_domains") or []
    report = {}
    for builder in ("legacy", "evidence", "skills", "hyde"):
        weights = retrieval_query_weights(profile, roles, builder=builder)
        with redirect_stdout(io.StringIO()):
            documents = retrieve_relevant_jobs(
                profile_embedding_text(profile),
                persist_dir=str(indexes[-1]),
                top_k=top,
                queries=retrieval_queries(profile, roles, builder=builder),
                candidate_profile=profile if preferences.get("seniority", "auto") == "auto" else None,
                query_weights=weights,
            )
        titles = [document.metadata.get("title", "") for document in documents]
        report[builder] = {
            "queries": [{"query": query, "weight": round(weight, 3)} for query, weight in weights.items()],
            "top": [
                f"{rank}. {title} | {document.metadata.get('company', '')}"
                for rank, (title, document) in enumerate(zip(titles, documents), 1)
            ],
            "off_target_in_top": off_target(titles),
        }
    jobs = {name: {line.split(". ", 1)[1] for line in report[name]["top"]} for name in ("legacy", "evidence", "skills", "hyde")}
    # Jobs each builder shares with the default evidence builder's top list.
    report["overlap_in_top"] = {name: len(jobs[name] & jobs["evidence"]) for name in ("legacy", "skills", "hyde")}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(compare(args.run_id, args.top), indent=2))
