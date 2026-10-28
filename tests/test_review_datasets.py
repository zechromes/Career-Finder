"""Human judgments are separate from immutable model evidence; no live providers."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from backend import runs
from backend.evaluation import review_datasets as service
from backend.schemas.experiments import ExperimentDataset
from backend.schemas.review_datasets import SaveReview
from backend.routers.review_datasets import router


class ReviewDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = "a" * 32
        self.profile = {"headline": "Python developer", "tech_skills": ["Python"]}
        criterion = dict(
            requirement="Python experience",
            importance="must_have",
            job_quote="Python required",
            resume_quote="Technical skills: Python",
            verdict="met",
            explanation="Skills match",
        )
        self.state = dict(
            recommendations=[
                dict(
                    title="Developer",
                    company="Example",
                    apply_url="https://example.test/1",
                    job_description="Python required. SQL preferred.",
                    fit_category="review",
                    model_evaluations={
                        "gpt": dict(
                            status="complete",
                            evaluation_model_id="synthetic",
                            requirement_set_id="shared",
                            requirement_extraction_model="synthetic-extractor",
                            requirement_extraction_version="test",
                            requirement_verdicts=[criterion],
                            fit_category="strong_match",
                        ),
                        "claude": dict(
                            status="complete",
                            evaluation_model_id="synthetic",
                            requirement_set_id="shared",
                            requirement_verdicts=[criterion],
                            fit_category="review",
                        ),
                    },
                )
            ]
        )
        self.docs = {
            "job1": Document(
                page_content="Python required. SQL preferred.",
                metadata={
                    "title": "Developer",
                    "company": "Example",
                    "url": "https://example.test/1",
                    "job_description": "Python required. SQL preferred.",
                },
            ),
            "job2": Document(
                page_content="Design illustrations.",
                metadata={
                    "title": "Designer",
                    "company": "Example",
                    "url": "https://example.test/2",
                    "job_description": "Design illustrations.",
                },
            ),
        }
        self.public = ExperimentDataset(
            source_id=self.source,
            fingerprint="b" * 64,
            scope="Synthetic full pool",
            jobs=[],
        )
        for obj, name, value in [
            (runs, "RUNS", {self.source: self.state}),
            (service, "REVIEW_DATASETS_DIR", Path(self.temp.name)),
        ]:
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(
            service.experiments,
            "dataset",
            return_value=(self.public, self.profile, ["Developer"], self.docs),
        )
        p.start()
        self.addCleanup(p.stop)
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.bundle = service.create(self.source)
        self.id = self.bundle.dataset.id

    def test_snapshot_covers_outside_shortlist_and_never_labels_from_models(self):
        data = self.bundle.dataset
        self.assertEqual(len(data.jobs), 2)
        self.assertFalse(data.jobs[1].previously_shortlisted)
        self.assertEqual(len(data.jobs[0].criteria), 1)
        self.assertEqual(len(data.jobs[0].evidence), 2)
        self.assertEqual(self.bundle.labels.jobs, {})
        report = service.measure(self.id)
        self.assertIsNone(report["extraction"]["precision"])
        self.assertIsNone(report["evidence"]["gpt:synthetic"]["support_rate"])
        self.assertEqual(report["retrieval"]["label_coverage"], 0)
        self.state["recommendations"].clear()
        self.assertEqual(service.read(self.id).dataset.model_dump(), data.model_dump())

    def test_save_persists_reviews_and_computes_only_reviewed_metrics(self):
        job = self.bundle.dataset.jobs[0]
        body = SaveReview(
            revision=0,
            reviewer="Reviewer A",
            review=dict(
                fit="strong_match",
                extraction_complete=True,
                criteria={
                    job.criteria[0].id: dict(correct=True, importance="must_have")
                },
                missing_requirements=[
                    dict(
                        requirement="SQL",
                        job_quote="SQL preferred.",
                        importance="nice_to_have",
                    )
                ],
                evidence={
                    "gpt-0": dict(support="unsupported", verdict="partial"),
                    "claude-0": dict(support="uncertain"),
                },
            ),
        )
        path = Path(self.temp.name) / self.id / "dataset.json"
        before = path.read_bytes()
        response = self.client.put(
            f"/api/review-datasets/{self.id}/jobs/job1", json=body.model_dump()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(service.read(self.id).labels.reviewers["job1"], "Reviewer A")
        report = service.measure(self.id)
        self.assertEqual(report["extraction"]["precision"], 1)
        self.assertEqual(report["extraction"]["recall_on_complete_reviews"], 0.5)
        self.assertEqual(report["extraction"]["missed_requirements"], 1)
        self.assertEqual(report["evidence"]["gpt:synthetic"]["support_rate"], 0)
        self.assertEqual(report["evidence"]["gpt:synthetic"]["verdict_accuracy"], 0)
        self.assertIsNone(report["evidence"]["claude:synthetic"]["support_rate"])
        self.assertEqual(report["retrieval"]["label_coverage"], 0.5)
        self.assertEqual(
            self.client.put(
                f"/api/review-datasets/{self.id}/jobs/job1", json=body.model_dump()
            ).status_code,
            409,
        )

    def test_ai_assisted_reviews_are_saved_but_excluded_from_metrics(self):
        job = self.bundle.dataset.jobs[0]
        review = dict(
            fit="strong_match",
            ai_assisted=True,
            criteria={job.criteria[0].id: dict(correct=False)},
            evidence={"gpt-0": dict(support="supported", verdict="met")},
        )
        response = self.client.put(
            f"/api/review-datasets/{self.id}/jobs/job1",
            json=dict(revision=0, reviewer="Reviewer A", review=review),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(service.read(self.id).labels.jobs["job1"].ai_assisted)
        report = self.client.get(f"/api/review-datasets/{self.id}/metrics").json()
        self.assertEqual(report["ai_assisted_reviews"], 1)
        self.assertEqual(report["fit_reviewed"], 0)
        self.assertEqual(report["retrieval"]["label_coverage"], 0)
        self.assertEqual(report["extraction"]["reviewed"], 0)
        self.assertEqual(report["evidence"]["gpt:synthetic"]["reviewed"], 0)
        # Human reviews saved before the flag existed still count as human.
        path = Path(self.temp.name) / self.id / "reviews.json"
        path.write_text(
            '{"revision": 2, "jobs": {"job2": {"fit": "not_suitable"}},'
            ' "reviewers": {"job2": "B"}, "updated_at": null}'
        )
        report = service.measure(self.id)
        self.assertEqual(report["ai_assisted_reviews"], 0)
        self.assertEqual(report["fit_reviewed"], 1)

    def test_delete_removes_snapshot_and_reviews_only(self):
        path = Path(self.temp.name) / self.id
        response = self.client.delete(f"/api/review-datasets/{self.id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": True})
        self.assertFalse(path.exists())
        self.assertEqual(
            self.client.get(f"/api/review-datasets/{self.id}").status_code, 404
        )
        self.assertEqual(self.client.get("/api/review-datasets").json(), [])
        self.assertIn(self.source, runs.RUNS)
        self.assertEqual(
            self.client.delete(f"/api/review-datasets/{self.id}").status_code, 404
        )
        self.assertEqual(
            self.client.delete("/api/review-datasets/..").status_code, 404
        )

    def test_stages_trace_good_fits_through_retrieval_and_generation(self):
        job = self.bundle.dataset.jobs[0]
        self.assertEqual(job.model_verdicts["gpt"].fit_category, "strong_match")
        self.assertEqual(job.app_verdict, "review")
        self.assertEqual(self.bundle.dataset.jobs[1].model_verdicts, {})
        for revision, job_id in enumerate(["job1", "job2"]):
            self.client.put(
                f"/api/review-datasets/{self.id}/jobs/{job_id}",
                json=dict(
                    revision=revision, reviewer="A", review=dict(fit="strong_match")
                ),
            )
        stages = self.client.get(f"/api/review-datasets/{self.id}/metrics").json()[
            "stages"
        ]
        self.assertTrue(stages["verdicts_available"])
        self.assertEqual(
            stages["funnel"],
            dict(
                good_fits=2,
                lost_at_retrieval=1,
                not_assessed=0,
                rejected_at_generation=0,
                needs_review=1,
                recommended=0,
            ),
        )
        self.assertEqual(
            stages["retrieval_missed"],
            [dict(id="job2", title="Designer", experienced_title=False)],
        )
        gpt, claude = stages["generation"]["gpt"], stages["generation"]["claude"]
        self.assertEqual((gpt["assessed"], gpt["good_fit_recall"]), (1, 1))
        self.assertEqual(gpt["strong_match_precision"], 1)
        self.assertEqual(claude["human_good"], dict(strong_match=0, review=1, not_suitable=0))
        self.assertEqual(claude["good_fit_recall"], 0)
        self.assertIsNone(claude["strong_match_precision"])
        self.assertEqual(stages["app"]["human_good"]["review"], 1)

    def test_add_verdicts_backfills_older_snapshot_once(self):
        path = Path(self.temp.name) / self.id / "dataset.json"
        older = json.loads(path.read_text())
        for job in older["jobs"]:
            job.pop("model_verdicts")
            job.pop("app_verdict")
        path.write_text(json.dumps(older))
        reviews = (Path(self.temp.name) / self.id / "reviews.json").read_bytes()
        self.assertFalse(service.measure(self.id)["stages"]["verdicts_available"])
        self.assertEqual(
            service.add_verdicts(self.id), dict(matched=1, shortlisted=1)
        )
        data = service.read(self.id).dataset
        self.assertIsNotNone(data.verdicts_added_at)
        self.assertEqual(data.jobs[0].model_verdicts["claude"].fit_category, "review")
        self.assertEqual(data.jobs[0].app_verdict, "review")
        self.assertEqual(
            (Path(self.temp.name) / self.id / "reviews.json").read_bytes(), reviews
        )
        with self.assertRaises(HTTPException) as again:
            service.add_verdicts(self.id)
        self.assertEqual(again.exception.status_code, 409)

    def test_add_verdicts_skips_newer_assessments_and_leaves_file_unchanged(self):
        path = Path(self.temp.name) / self.id / "dataset.json"
        older = json.loads(path.read_text())
        for job in older["jobs"]:
            job.pop("model_verdicts")
            job.pop("app_verdict")
        path.write_text(json.dumps(older))
        before = path.read_bytes()
        # A re-evaluation changed the verdicts, so the frozen evidence no longer matches.
        gpt = self.state["recommendations"][0]["model_evaluations"]["gpt"]
        gpt["requirement_verdicts"] = [
            dict(gpt["requirement_verdicts"][0], verdict="not_met")
        ]
        with self.assertRaises(HTTPException) as refused:
            service.add_verdicts(self.id)
        self.assertEqual(refused.exception.status_code, 422)
        self.assertEqual(path.read_bytes(), before)

    def test_unknown_keys_bad_quotes_and_incomplete_reviews_rejected(self):
        for review in [
            dict(criteria={"foreign": dict(correct=True)}),
            dict(evidence={"foreign": dict(support="supported")}),
            dict(extraction_complete=True),
            dict(
                missing_requirements=[
                    dict(
                        requirement="Imaginary",
                        job_quote="Not in posting",
                        importance="must_have",
                    )
                ]
            ),
        ]:
            response = self.client.put(
                f"/api/review-datasets/{self.id}/jobs/job1",
                json=dict(revision=0, reviewer="A", review=review),
            )
            self.assertEqual(response.status_code, 422)
        self.assertEqual(service.read(self.id).labels.revision, 0)
        self.assertEqual(
            self.client.get("/api/review-datasets/invalid").status_code, 404
        )

    def test_legacy_criteria_do_not_count_as_shared_extraction(self):
        for assessment in self.state["recommendations"][0][
            "model_evaluations"
        ].values():
            assessment.pop("requirement_set_id")
        bundle = service.create(self.source)
        self.assertFalse(bundle.dataset.jobs[0].extraction_available)
        self.assertTrue(
            all(
                row.origin == "legacy_provider"
                for row in bundle.dataset.jobs[0].criteria
            )
        )
        self.assertEqual(service.measure(bundle.dataset.id)["extraction"]["total"], 0)

    def test_changed_posting_does_not_inherit_old_assessment(self):
        self.state["recommendations"][0]["job_description"] = "Outdated posting"
        bundle = service.create(self.source)
        self.assertEqual(bundle.dataset.jobs[0].evidence, [])
        self.assertEqual(bundle.dataset.jobs[0].criteria, [])
        self.assertTrue(bundle.dataset.jobs[0].previously_shortlisted)
