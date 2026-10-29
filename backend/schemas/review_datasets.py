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
    # For a posting merged as a duplicate: is it the same job as the one kept?
    duplicate_correct: StrictBool | None = None
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


class ModelVerdict(BaseModel):
    model: str = ""
    status: str
    fit_category: str | None = None
    score: float | None = None


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
    # Saved provider verdicts and the app's combined verdict; empty in older snapshots.
    model_verdicts: dict[str, ModelVerdict] = Field(default_factory=dict)
    app_verdict: str | None = None


class DuplicateOf(BaseModel):
    title: str
    company: str
    url: str
    board: str
    description: str
    method: str


class DroppedJob(BaseModel):
    id: str
    title: str
    company: str
    location: str
    url: str
    board: str
    stage: str
    reason: str
    description: str
    duplicate_of: DuplicateOf | None = None


class IngestionCount(BaseModel):
    stage: str
    reason: str
    board: str
    count: int


class IngestionRecord(BaseModel):
    searches: int
    # False when a search used the collection cache or predates recording.
    complete: bool
    collected: dict[str, int]
    kept: int
    counts: list[IngestionCount]
    omitted: int


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
    # Set when verdicts were added from the source workspace after snapshot creation.
    verdicts_added_at: float | None = None
    # Postings dropped before ranking; absent in snapshots of unrecorded searches.
    ingestion: IngestionRecord | None = None
    dropped_jobs: list[DroppedJob] = Field(default_factory=list)


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


class VerdictCounts(BaseModel):
    strong_match: int = 0
    review: int = 0
    not_suitable: int = 0


class GenerationMetrics(BaseModel):
    model: str
    assessed: int
    failed: int
    human_good: VerdictCounts
    human_not_fit: VerdictCounts
    strong_match_precision: float | None
    good_fit_recall: float | None
    good_fits_rejected: list[str]


class MissedJob(BaseModel):
    id: str
    title: str
    experienced_title: bool


class StageFunnel(BaseModel):
    good_fits: int
    lost_at_ingestion: int
    lost_at_retrieval: int
    not_assessed: int
    rejected_at_generation: int
    needs_review: int
    recommended: int


class ReasonCount(BaseModel):
    stage: str
    reason: str
    count: int
    labeled: int
    good_fits: int


class BoardCount(BaseModel):
    board: str
    collected: int
    dropped: int


class DuplicateMetrics(BaseModel):
    recorded: int
    judged: int
    same: int
    precision: float | None


class SearchTextJob(BaseModel):
    id: str
    title: str
    kept: int
    total: int


class SearchTextMetrics(BaseModel):
    jobs_checked: int
    quotes: int
    kept: int
    rate: float | None
    lowest: list[SearchTextJob]


class IngestionMetrics(BaseModel):
    available: bool
    complete: bool
    searches: int
    collected: int
    kept: int
    omitted: int
    by_reason: list[ReasonCount]
    by_board: list[BoardCount]
    dropped_recorded: int
    labeled: int
    good_fits: int
    duplicates: DuplicateMetrics
    search_text: SearchTextMetrics


class StageMetrics(BaseModel):
    verdicts_available: bool
    funnel: StageFunnel
    ingestion: IngestionMetrics
    retrieval_missed: list[MissedJob]
    generation: dict[str, GenerationMetrics]
    app: GenerationMetrics | None


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
    stages: StageMetrics
    limitations: list[str]


class ReplayRule(BaseModel):
    rule: str
    name: str
    shortlist_size: int
    # Share of the original shortlist this rule reproduces; the title-only rule
    # should be close to 1 if the replay is faithful.
    matches_original: float | None
    metrics: ExperimentMetrics
    good_fits_added: list[str]
    not_fits_added: list[str]
    unassessed_added: int


class ReplayResult(BaseModel):
    dataset_id: str
    embedding_model: str
    ranked_at: float
    searches: int
    top_k: int
    unranked: int
    rules: list[ReplayRule]
    limitations: list[str]
