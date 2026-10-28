"""Repair missing exclusion details from saved vacancies, without scraping.

Run explicitly with a run directory. Only jobs absent from recommendations are
reassessed, and checkpoints prevent paying again for successful recovery calls.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil

import chromadb
from langchain_core.documents import Document
import pandas as pd

from backend.search.collection import _canonical_url
from backend.evaluation.providers import evaluate_jobs_with_claude


# Identify a posting when reconciling recovered and existing results.
def key(job):
    return _canonical_url(job.get("apply_url") or job.get("url") or "")


# Recover eligible stored results using the requested source and output settings.
def recover(run_dir, dry_run=False, identities_only=False):
    state_path = run_dir / "state.json"
    state = json.loads(state_path.read_text())
    if state["status"] != "complete":
        raise ValueError("Recovery requires a completed run.")
    if state.get("excluded_recommendations") and not any(
        job.get("reason_unavailable") for job in state["excluded_recommendations"]
    ):
        print("This run already has excluded-job details.")
        return
    databases = list(run_dir.glob("vector_db_search_*/chroma.sqlite3"))
    if len(databases) != 1:
        raise ValueError("Cannot unambiguously identify the saved search database.")
    collection = chromadb.PersistentClient(
        path=str(databases[0].parent)
    ).get_collection("langchain")
    data = collection.get(include=["documents", "metadatas"])
    documents = [
        Document(page_content=text, metadata=metadata)
        for text, metadata in zip(data["documents"], data["metadatas"])
    ]
    source_keys = {key(doc.metadata) for doc in documents}
    recommended_keys = {key(job) for job in state["recommendations"]}
    # Recovery by subtraction is safe only when every vacancy was evaluated,
    # and all recommendation URLs identify unique entries in the saved pool.
    if (
        len(source_keys) != len(documents)
        or "" in source_keys
        or len(documents) != state["evaluated_jobs"]
        or state.get("evaluation_failed", 0)
        or len(recommended_keys) != len(state["recommendations"])
        or not recommended_keys <= source_keys
    ):
        raise ValueError(
            "Cannot reliably distinguish excluded jobs from unevaluated vacancies."
        )
    excluded = [doc for doc in documents if key(doc.metadata) not in recommended_keys]
    if len(excluded) != state["excluded_jobs"]:
        raise ValueError("Saved exclusion count does not match identified jobs.")
    print(
        f"Identified {len(excluded)} excluded jobs from {len(documents)} saved vacancies.",
        flush=True,
    )
    if dry_run:
        return

    backup = run_dir / "state.before_exclusion_recovery.json"
    if identities_only:
        # This path uses local records only and never invents a reason or
        # calls Claude. All these jobs were excluded in the completed run.
        if not backup.exists():
            shutil.copy2(state_path, backup)
        state["excluded_recommendations"] = [
            {
                **doc.metadata,
                "apply_url": doc.metadata.get("url", ""),
                "fit_category": "not_suitable",
                "is_strong_fit": False,
                "reason_unavailable": True,
                "mismatch_reason": "The original individual reason was not saved. Reassessment is required to recover it.",
                "assessment_origin": "Job identity recovered from the completed search; original decision retained.",
            }
            for doc in excluded
        ]
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(
            f"Recovered {len(excluded)} job rows locally; individual reasons remain unavailable.",
            flush=True,
        )
        return

    checkpoint = run_dir / "recovered_assessments.json"
    results = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}

    # Persist the recovered assessment as it becomes available.
    def save_result(result):
        result["assessment_origin"] = (
            "Reassessed from saved vacancy to recover missing details"
        )
        results[key(result)] = result
        checkpoint.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(
            f"Saved {len(results)} / {len(excluded)} recovered assessments", flush=True
        )

    pending = [doc for doc in excluded if key(doc.metadata) not in results]
    evaluate_jobs_with_claude(
        (run_dir / "resume_context.txt").read_text(),
        pending,
        include_all=True,
        target_roles=state.get("search_inputs", {}).get("queries", []),
        on_result=save_result,
    )
    if any(key(doc.metadata) not in results for doc in excluded):
        raise RuntimeError(
            "Some assessments failed. Checkpoints saved; rerun to retry only missing jobs."
        )
    if not backup.exists():
        shutil.copy2(state_path, backup)
    recovered = [results[key(doc.metadata)] for doc in excluded]
    state["excluded_recommendations"] = [
        {**job, "reason": job["mismatch_reason"]}
        for job in recovered
        if job["fit_category"] == "not_suitable"
    ]
    state["recommendations"].extend(
        job for job in recovered if job["fit_category"] != "not_suitable"
    )
    state["recommendations"].sort(key=lambda job: job["fit_category"] != "strong_match")
    state["excluded_jobs"] = len(state["excluded_recommendations"])
    state["excluded_reasons"] = dict(
        Counter(job["reason"] for job in state["excluded_recommendations"])
    )
    state["displayed_jobs"] = len(state["recommendations"])
    state["recommendations_found"] = sum(
        job["fit_category"] == "strong_match" for job in state["recommendations"]
    )
    state["message"] = "Recovered individual job assessments from saved vacancies."
    # Regenerated assessments can change fit categories; keep the export and
    # displayed counts consistent with those updated decisions.
    pd.DataFrame(state["recommendations"]).to_excel(
        run_dir / "relevant_jobs.xlsx", index=False
    )
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(
        f"Recovery complete: {state['excluded_jobs']} excluded job rows saved.",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--identities-only",
        action="store_true",
        help="Recover job rows locally without calling Claude",
    )
    args = parser.parse_args()
    recover(args.run_dir, args.dry_run, args.identities_only)
