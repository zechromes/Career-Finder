# Regression coverage for exports; fixtures and assertions document the expected behavior.
import json
import tempfile
import unittest
import warnings
from pathlib import Path

import pandas as pd

from backend.exports import EXCEL_CELL_LIMIT, export_jobs_excel


class ExcelExportTests(unittest.TestCase):
    def test_long_text_and_model_evidence_round_trip_without_truncation(self):
        description = "Job details é " * 6000
        evaluations = {"claude": {"evidence": "Resume evidence " * 3000}}
        jobs = [
            {
                "title": "Engineer",
                "description": description,
                "model_evaluations": evaluations,
                "score": 85,
            },
            {"title": "Analyst", "description": "Short description", "score": 70},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.xlsx"
            with warnings.catch_warnings():
                warnings.simplefilter("error", UserWarning)
                export_jobs_excel(jobs, path)
            frame = pd.read_excel(path).fillna("")
        for field, expected in [
            ("description", description),
            ("model_evaluations", json.dumps(evaluations, ensure_ascii=False)),
        ]:
            columns = [
                c
                for c in frame.columns
                if c == field or c.startswith(field + " (continued ")
            ]
            self.assertEqual("".join(frame.loc[0, c] for c in columns), expected)
            self.assertTrue(
                all(len(frame.loc[0, c]) <= EXCEL_CELL_LIMIT for c in columns)
            )
        # Check the expected behavior: long text and model evidence round trip without truncation.
        self.assertEqual(frame.loc[1, "description"], "Short description")
        self.assertEqual(frame.loc[0, "score"], 85)
        self.assertEqual(jobs[0]["model_evaluations"], evaluations)

    def test_empty_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.xlsx"
            export_jobs_excel([], path)
            self.assertTrue(pd.read_excel(path).empty)
