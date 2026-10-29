"""Retrieval replay compares seniority rules on frozen labels; no live providers."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend import runs
from backend.evaluation import replay, review_datasets
from backend.routers.review_datasets import router

DATASET = "c" * 32


def job(key, title, description, shortlisted):
    return dict(
        id=key,
        title=title,
        company="Example",
        url=f"https://example.test/{key}",
        description=description,
        previously_shortlisted=shortlisted,
        tags=[],
        criteria=[],
        evidence=[],
        extraction_available=False,
    )


class RetrievalReplayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        folder = self.root / DATASET
        folder.mkdir()
        (folder / "dataset.json").write_text(
            json.dumps(
                dict(
                    id=DATASET,
                    created_at=1.0,
                    source_id="a" * 32,
                    fingerprint="b" * 64,
                    scope="Synthetic",
                    profile=dict(career_level="mid", years_of_experience=2),
                    profile_text="Synthetic profile",
                    target_roles=["AI Engineer"],
                    jobs=[
                        job("senior_open", "Senior AI Engineer", "Build agents.", False),
                        job("senior_years", "Senior Engineer", "Minimum of 5 years of Python.", False),
                        job("plain_good", "AI Engineer", "Build agents.", True),
                        job("plain_not", "Developer", "Maintain forms.", True),
                        job("second", "Data Engineer", "Pipelines.", True),
                    ],
                )
            )
        )
        fits = dict(
            senior_open="strong_match",
            senior_years="not_suitable",
            plain_good="strong_match",
            plain_not="not_suitable",
        )
        (folder / "reviews.json").write_text(
            json.dumps(dict(jobs={key: dict(fit=fit) for key, fit in fits.items()}))
        )
        self.ranking = dict(
            embedding_model="synthetic",
            ranked_at=2.0,
            top_k=2,
            # The appended search ranks an already-assessed posting first.
            searches=[
                ["senior_open", "senior_years", "plain_good", "plain_not"],
                ["plain_good", "second"],
            ],
        )
        for obj, name, value in [
            (review_datasets, "REVIEW_DATASETS_DIR", self.root),
            (runs, "RUNS", {}),
        ]:
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)

    def run_replay(self):
        with patch.object(replay, "_relevance", return_value=self.ranking) as rank:
            result = replay.replay(DATASET)
        return result, rank

    def test_compares_rules_on_the_same_labels(self):
        result, _ = self.run_replay()
        old, new = result["rules"]
        self.assertEqual(old["rule"], "title_only")
        # The title-only rule reproduces the original shortlist.
        self.assertEqual(old["matches_original"], 1.0)
        self.assertEqual(old["metrics"]["observed_recall_at_k"], 0.5)
        self.assertEqual(old["good_fits_added"], [])
        # Without stated years, a senior title is no longer held back.
        self.assertEqual(new["metrics"]["observed_recall_at_k"], 1.0)
        self.assertEqual(new["metrics"]["precision_on_labeled"], 1.0)
        self.assertEqual(new["good_fits_added"], ["senior_open"])
        self.assertEqual(new["not_fits_added"], [])
        self.assertEqual(new["unassessed_added"], 1)
        self.assertEqual(new["shortlist_size"], 3)
        self.assertEqual(result["unranked"], 0)

    def test_ranking_is_saved_so_later_replays_do_not_embed(self):
        _, rank = self.run_replay()
        self.assertEqual(rank.call_count, 1)
        _, rank = self.run_replay()
        rank.assert_not_called()
        self.assertTrue((self.root / DATASET / "relevance.json").is_file())

    def test_ai_assisted_labels_are_excluded(self):
        path = self.root / DATASET / "reviews.json"
        reviews = json.loads(path.read_text())
        reviews["jobs"]["senior_open"]["ai_assisted"] = True
        path.write_text(json.dumps(reviews))
        result, _ = self.run_replay()
        self.assertEqual(result["rules"][1]["good_fits_added"], [])

    def test_missing_source_search_is_a_conflict(self):
        app = FastAPI()
        app.include_router(router)
        response = TestClient(app).post(f"/api/review-datasets/{DATASET}/replay")
        self.assertEqual(response.status_code, 409)
        self.assertFalse((self.root / DATASET / "relevance.json").exists())


if __name__ == "__main__":
    unittest.main()
