"""Excel exports that preserve long descriptions and model assessments."""

import json

import pandas as pd


EXCEL_CELL_LIMIT = 32767


def export_jobs_excel(jobs, path):
    """Split oversized text across continuation columns instead of truncating it."""
    rows = []
    for job in jobs:
        row = {}
        for field, value in job.items():
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, ensure_ascii=False, default=str)
            if isinstance(value, str) and len(value) > EXCEL_CELL_LIMIT:
                row[field] = value[:EXCEL_CELL_LIMIT]
                for offset in range(EXCEL_CELL_LIMIT, len(value), EXCEL_CELL_LIMIT):
                    part = offset // EXCEL_CELL_LIMIT + 1
                    row[f"{field} (continued {part})"] = value[
                        offset : offset + EXCEL_CELL_LIMIT
                    ]
            else:
                row[field] = value
        rows.append(row)
    pd.DataFrame(rows).to_excel(path, index=False)
