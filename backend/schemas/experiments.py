"""Bounded, isolated retrieval and job-assessment experiments."""

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator, StrictBool
from backend.schemas.contracts import JobResult

Provider = Literal["claude", "gpt", "gemini"]
Embedding = Literal["text-embedding-3-small", "text-embedding-3-large"]


class ExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    phase: Literal["retrieval", "generation", "both"] = "both"
    embedding_models: list[Embedding] = Field(
        default_factory=lambda: ["text-embedding-3-small"], max_length=2
    )
    providers: list[Provider] = Field(default_factory=lambda: ["gpt"], max_length=3)
    top_k: int = Field(default=5, ge=1, le=20)
    labels: dict[str, StrictBool] = Field(default_factory=dict, max_length=500)

    @model_validator(mode="after")
    def selections(self):
        if self.phase != "generation" and not self.embedding_models:
            raise ValueError("Choose at least one embedding model.")
        if self.phase != "retrieval" and not self.providers:
            raise ValueError("Choose at least one generation model.")
        if len(set(self.embedding_models)) != len(self.embedding_models) or len(
            set(self.providers)
        ) != len(self.providers):
            raise ValueError("Model selections must be unique.")
        return self


class ExperimentSource(BaseModel):
    id: str
    name: str
    job_count: int


class ExperimentJob(BaseModel):
    id: str
    title: str
    company: str = ""
    description: str


class ExperimentDataset(BaseModel):
    source_id: str
    fingerprint: str
    scope: str
    jobs: list[ExperimentJob]


class ExperimentModel(BaseModel):
    value: str
    label: str
    model_id: str


class ExperimentOptions(BaseModel):
    generation_models: list[ExperimentModel]
    embedding_models: list[str]


class ExperimentMetrics(BaseModel):
    label_coverage: float
    observed_recall_at_k: float | None = None
    precision_on_labeled: float | None = None
    missed_labeled_positives: list[str] = Field(default_factory=list)
    unlabeled_selected: int = 0


class RetrievalTrial(BaseModel):
    model: str
    seconds: float
    ranked_ids: list[str]
    metrics: ExperimentMetrics
    error: str | None = None


class GenerationTrial(BaseModel):
    provider: str
    model: str
    seconds: float
    input_ids: list[str]
    results: list[JobResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metrics: ExperimentMetrics


class ExperimentResult(BaseModel):
    id: str
    status: Literal["running", "complete", "partial", "failed", "cancelled"]
    source_id: str
    created_at: float
    fingerprint: str
    scope: str
    phase: str
    top_k: int
    pool_size: int
    settings: ExperimentRequest
    message: str
    retrieval: list[RetrievalTrial] = Field(default_factory=list)
    generation: list[GenerationTrial] = Field(default_factory=list)
