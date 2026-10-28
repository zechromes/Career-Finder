"""Freeze one existing workspace for human review; no network or provider calls."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import runs
from backend.evaluation import review_datasets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-id",
        help="Required when more than one saved-profile workspace exists.",
    )
    args = parser.parse_args()
    states = []
    for path in runs.RUNS_DIR.glob("*/state.json"):
        state = json.loads(path.read_text())
        if state.get("saved_profile_id") and (
            not args.source_id or state.get("id") == args.source_id
        ):
            states.append(state)
    if len(states) != 1:
        parser.error(
            "Choose exactly one existing saved-profile workspace with --source-id."
        )
    state = states[0]
    runs.RUNS[state["id"]] = (
        state  # Isolated CLI process; never load/expire other runs.
    )
    bundle = review_datasets.create(state["id"])
    print(
        json.dumps(
            {
                "dataset_id": bundle.dataset.id,
                "jobs": len(bundle.dataset.jobs),
                "outside_shortlist": sum(
                    not job.previously_shortlisted for job in bundle.dataset.jobs
                ),
                "shared_extraction_jobs": sum(
                    job.extraction_available for job in bundle.dataset.jobs
                ),
                "evidence_rows": sum(len(job.evidence) for job in bundle.dataset.jobs),
                "human_labels": 0,
                "review_url": "/eval/datasets/" + bundle.dataset.id,
            }
        )
    )


if __name__ == "__main__":
    main()
