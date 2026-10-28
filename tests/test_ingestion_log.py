"""Ingestion drops are recorded with reasons; synthetic postings, no external calls."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from backend.search import ingestion_log
from backend.search.collection import fetch_job_vacancies


def row(i, **extra):
    return {
        **dict(
            title=f"Engineer {i}",
            company=f"Company {i}",
            job_url=f"https://example.test/{i}",
            location="Sydney, Australia",
            description="Engineering work " * 10,
            site="indeed",
        ),
        **extra,
    }


class IngestionLogTests(unittest.TestCase):
    def collect(self, rows, candidates="100"):
        log = ingestion_log.IngestionLog()
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ",
            {
                "JOB_SEARCH_PROVIDER": "jobspy",
                "JOB_COLLECTION_CACHE_TTL_SECONDS": "0",
                "JOBSPY_DESCRIPTION_CACHE_DIR": directory,
                "JOB_COLLECTION_MAX_BATCHES": "1",
                "JOB_COLLECTION_MAX_CANDIDATES": candidates,
            },
        ), patch.dict("backend.search.board_cooldown._UNTIL", {}, clear=True), patch(
            "jobspy.scrape_jobs", return_value=pd.DataFrame(rows)
        ), ingestion_log.recording(
            log
        ):
            kept = fetch_job_vacancies(
                ["Engineer"], ["Sydney"], ["indeed"], adaptive=True, posted_days_old=0
            )
        return kept, log

    def test_records_each_drop_with_its_stage_and_reason(self):
        kept, log = self.collect(
            [
                row(1),
                row(2, location="London, UK"),
                row(3, description=""),
                dict(row(1), title="Engineer 1", description="Engineering work"),
                row(4),
            ]
        )
        self.assertEqual({job["url"] for job in kept}, {
            "https://example.test/1",
            "https://example.test/4",
        })
        reasons = {(job["stage"], job["reason"]) for job in log.dropped}
        self.assertIn(("filter", "location does not match"), reasons)
        self.assertIn(("description", "no usable description"), reasons)
        duplicate = next(job for job in log.dropped if job["stage"] == "deduplicate")
        self.assertEqual(duplicate["duplicate_of"]["method"], "same link")
        self.assertEqual(log.collected, {"indeed": 5})
        summary = log.to_dict(len(kept))
        self.assertEqual(summary["kept"], 2)
        self.assertFalse(summary["cached"])

    def test_candidate_limit_drops_are_budget_losses(self):
        kept, log = self.collect([row(i) for i in range(1, 5)], candidates="2")
        self.assertEqual(len(kept), 2)
        self.assertEqual(
            {job["stage"] for job in log.dropped}, {"budget"}, log.dropped
        )

    def test_workspace_duplicates_are_counted_not_stored_and_caps_hold(self):
        log = ingestion_log.IngestionLog()
        log.drop({"url": "https://example.test/w"}, "deduplicate", "already in this workspace")
        for i in range(ingestion_log.CAPS["filter"] + 5):
            log.drop({"url": f"https://example.test/{i}"}, "filter", "posted too long ago")
        self.assertEqual(len(log.dropped), ingestion_log.CAPS["filter"])
        self.assertEqual(log.omitted, 5)
        counts = {(c["stage"], c["reason"]): c["count"] for c in log.to_dict(0)["counts"]}
        self.assertEqual(counts[("deduplicate", "already in this workspace")], 1)
        self.assertEqual(counts[("filter", "posted too long ago")], 125)

    def test_cache_hits_are_marked_and_searches_append(self):
        log = ingestion_log.IngestionLog()
        with patch(
            "backend.search.collection.CollectionCache.collect",
            return_value=([], True),
        ), ingestion_log.recording(log):
            fetch_job_vacancies(["Engineer"], ["Sydney"], ["indeed"], adaptive=True)
        self.assertTrue(log.cached)
        with tempfile.TemporaryDirectory() as directory:
            ingestion_log.save(Path(directory), log, 0, {"queries": ["Engineer"]})
            ingestion_log.save(Path(directory), ingestion_log.IngestionLog(), 3, {})
            searches = ingestion_log.load(Path(directory))["searches"]
        self.assertEqual([s["cached"] for s in searches], [True, False])
        self.assertEqual(searches[1]["kept"], 3)

    def test_recording_is_inactive_outside_a_search(self):
        self.assertFalse(ingestion_log.active())
        ingestion_log.drop({"url": "x"}, "filter", "posted too long ago")


if __name__ == "__main__":
    unittest.main()
