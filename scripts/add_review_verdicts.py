"""Add saved model verdicts to older review datasets; no network or provider calls."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import runs
from backend.evaluation import review_datasets
from backend.paths import REVIEW_DATASETS_DIR


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-id",
        help="Required when more than one review dataset exists.",
    )
    args = parser.parse_args()
    ids = [
        path.parent.name
        for path in REVIEW_DATASETS_DIR.glob("*/dataset.json")
        if not args.dataset_id or path.parent.name == args.dataset_id
    ]
    if len(ids) != 1:
        parser.error("Choose exactly one existing review dataset with --dataset-id.")
    source_id = review_datasets.read(ids[0]).dataset.source_id
    path = runs.RUNS_DIR / source_id / "state.json"
    if not path.is_file():
        parser.error("The source workspace is no longer available.")
    # Isolated CLI process; never load or expire other runs.
    runs.RUNS[source_id] = json.loads(path.read_text())
    result = review_datasets.add_verdicts(ids[0])
    print(json.dumps({"dataset_id": ids[0], **result}))


if __name__ == "__main__":
    main()
