"""Measure exported rankings against human labels; never calls a provider.

Input JSON: [{"query_id": "q1", "labels": {"job1": true, "job2": false},
"shortlist": ["job1"], "predicted_strong": ["job1"]}]
Label the full collected pool for exact recall. Partial labels give observed recall.
"""

import argparse
import json
import random


# Compare ranked matches with available labels without treating unlabeled jobs as negatives.
def measure(cases):
    reports = []
    for case in cases:
        labels = case["labels"]
        if not all(isinstance(value, bool) for value in labels.values()):
            raise ValueError("Labels must be human boolean judgments")
        positive = {key for key, value in labels.items() if value}
        shortlist = set(case["shortlist"])
        predicted = set(case.get("predicted_strong", []))
        judged_predictions = predicted & labels.keys()
        reports.append(
            {
                "query_id": case["query_id"],
                "observed_recall_at_k": (
                    len(positive & shortlist) / len(positive) if positive else None
                ),
                "strong_match_precision_on_labeled": (
                    len(positive & predicted) / len(judged_predictions)
                    if judged_predictions
                    else None
                ),
                "unlabeled_shortlist_count": len(shortlist - labels.keys()),
                "unlabeled_strong_count": len(predicted - labels.keys()),
                "missed_labeled_strong": sorted(positive - shortlist),
                "outside_shortlist_sample": random.Random(42).sample(
                    sorted(set(case.get("pool", labels)) - shortlist),
                    min(10, len(set(case.get("pool", labels)) - shortlist)),
                ),
            }
        )
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels_json")
    args = parser.parse_args()
    with open(args.labels_json) as source:
        print(json.dumps(measure(json.load(source)), indent=2))
