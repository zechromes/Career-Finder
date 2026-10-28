"""Human review contracts; model outputs are evidence, never ground truth."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from backend.schemas.resume import ResumeProfile


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CriterionReview(StrictModel):
    correct: StrictBool | None = None
    importance: Literal["must_have", "nice_to_have", "unclear"] | None = None
    notes: str = Field(default="", max_length=3000)


class EvidenceReview(StrictModel):
    support: Literal["supported", "unsupported", "uncertain"] | None = None
    verdict: Literal["met", "partial", "not_met", "unknown"] | None = None
    notes: str = Field(default="", max_length=3000)


class MissingRequirement(StrictModel):
    requirement: str = Field(min_length=1, max_length=3000)
    job_quote: str = Field(min_length=1, max_length=10000)
    importance: Literal["must_have", "nice_to_have", "unclear"]


class JobReview(StrictModel):
    fit: Literal["strong_match", "review", "not_suitable"] | None = None
    # AI-suggested judgments are kept for reference but excluded from human metrics.
    ai_assisted: StrictBool = False
    notes: str = Field(default="", max_length=5000)
    extraction_complete: StrictBool = False
    criteria: dict[str, CriterionReview] = Field(default_factory=dict, max_length=500)
    missing_requirements: list[MissingRequirement] = Field(
        default_factory=list, max_length=100
    )
    evidence: dict[str, EvidenceReview] = Field(default_factory=dict, max_length=1500)


class SaveReview(StrictModel):
    revision: int = Field(ge=0)
    reviewer: str = Field(min_length=1, max_length=100)
    review: JobReview


class ReviewCriterion(BaseModel):
    id: str
    requirement: str
    importance: str
    job_quote: str
    section: str = ""
    origin: str
    extraction_model: str = ""
    extraction_version: str = ""
    set_id: str = ""


class ReviewEvidence(BaseModel):
    id: str
    provider: str
    model: str
    requirement: str
    verdict: str
    job_quote: str
    resume_quote: str
    explanation: str
    job_quote_found: bool
    profile_quote_found: bool


class ReviewJob(BaseModel):
    id: str
    title: str
    company: str
    url: str
    description: str
    previously_shortlisted: bool
    tags: list[str]
    criteria: list[ReviewCriterion]
    evidence: list[ReviewEvidence]
    extraction_available: bool


class ReviewDataset(BaseModel):
    id: str
    created_at: float
    source_id: str
    fingerprint: str
    scope: str
    split: Literal["pilot"] = "pilot"
    profile: ResumeProfile
    profile_text: str
    target_roles: list[str]
    jobs: list[ReviewJob]


class ReviewState(BaseModel):
    revision: int = 0
    jobs: dict[str, JobReview] = Field(default_factory=dict)
    reviewers: dict[str, str] = Field(default_factory=dict)
    updated_at: float | None = None


class ReviewBundle(BaseModel):
    dataset: ReviewDataset
    labels: ReviewState


class CreateReviewDataset(StrictModel):
    source_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class ReviewDatasetSummary(BaseModel):
    id: str
    created_at: float
    job_count: int
    outside_shortlist: int
    reviewed_jobs: int


from backend.schemas.experiments import ExperimentMetrics


class ExtractionMetrics(BaseModel):
    total: int
    reviewed: int
    precision: float | None
    importance_accuracy: float | None
    completeness_reviewed_jobs: int
    missed_requirements: int
    recall_on_complete_reviews: float | None


class EvidenceMetrics(BaseModel):
    total: int
    reviewed: int
    supported: int
    unsupported: int
    uncertain: int
    verdict_reviewed: int
    verdict_correct: int
    quotes_found: int
    review_coverage: float | None
    support_rate: float | None
    verdict_accuracy: float | None


class ReviewMetrics(BaseModel):
    dataset_id: str
    revision: int
    split: str
    pool_size: int
    fit_reviewed: int
    ai_assisted_reviews: int
    retrieval: ExperimentMetrics
    extraction: ExtractionMetrics
    evidence: dict[str, EvidenceMetrics]
    limitations: list[str]
