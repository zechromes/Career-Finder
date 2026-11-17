"""Public API schemas; OpenAPI is the source for generated frontend types."""

from typing import Literal
from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    computed_field,
    field_validator,
    model_validator,
)
from backend.schemas.resume import ResumeProfile
from backend.schemas.evaluation import RequirementVerdict
from backend.schemas.tailored_resume import TailoredResume


# Expose requirement evidence together with the code-verified quote flags.
class VerifiedRequirement(RequirementVerdict):
    job_evidence_verified: bool = False
    resume_evidence_verified: bool = False
    # Older saved assessments hold one quote; new ones keep the first verified quote here.
    resume_quote: str = ""
    resume_quotes_verified: list[bool] = Field(default_factory=list)


# Validate search filters and shortlist size at the API boundary.
class Preferences(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=20)
    locations: list[str] = Field(default_factory=list, max_length=20)
    platforms: list[
        Literal["linkedin", "indeed", "seek", "google", "adzuna"]
    ] = Field(
        default_factory=lambda: ["linkedin"], min_length=1
    )

    @field_validator("platforms", mode="before")
    @classmethod
    def remove_retired_feeds(cls, value):
        if isinstance(value, list):
            value = [
                site for site in value if site not in ("greenhouse", "lever", "glassdoor")
            ]
            if not value:
                raise ValueError(
                    "Select at least one supported job board: LinkedIn, Indeed, SEEK, Google Jobs or Adzuna."
                )
        return value

    work_type: Literal["any", "remote", "hybrid", "on-site"] = "any"
    seniority: Literal[
        "auto", "any", "graduate", "entry", "junior", "mid", "senior"
    ] = "auto"
    exclusions: list[str] = Field(default_factory=list, max_length=30)
    posted_days_old: Literal[0, 1, 7, 30] = 7
    # -1 is Automatic: every job for pools up to 200, otherwise the top 100. 0 is every job.
    top_k: int = Field(default=-1, ge=-1, le=10000)
    evaluation_model: Literal["gemini", "claude", "gpt"] = "claude"


# Accept preference changes while retaining the existing workspace profile.
class FindMoreRequest(BaseModel):
    preferences: Preferences


# Pair a confirmed candidate profile with the initial search preferences.
class ProfileConfirmation(BaseModel):
    profile: ResumeProfile
    preferences: Preferences


# Represent a single provider’s status, assessment, and safe failure details.
class ModelEvaluation(BaseModel):
    model_config = ConfigDict(extra="allow")
    provider: str = ""
    evaluation_model_id: str = ""
    status: Literal["pending", "complete", "failed", "skipped"] = "pending"
    error: str = ""
    score: int | None = None
    fit_category: Literal["strong_match", "review", "not_suitable"] = "review"
    rationale: str = ""
    rule_exception: str = ""
    mismatch_reason: str = ""
    score_method: str = ""
    requirement_set_id: str = ""
    requirement_extraction_model: str = ""
    requirement_extraction_version: str = ""
    requirement_verdicts: list[VerifiedRequirement] = Field(default_factory=list)
    candidate_requirements: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    about_company: str = ""
    salary: str | None = None


# Define the public job snapshot, including evidence and per-provider assessments.
class JobResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    # Present once a tailored resume was generated for this job.
    tailored_resume: TailoredResume | None = None
    completed_models: int = 0
    agreement_count: int = 0
    shortlist_rank: int | None = None
    provisional_score: int | None = None
    assessment_summary: str = ""
    model_evaluations: dict[str, ModelEvaluation] = Field(default_factory=dict)
    jobId: str = ""
    title: str = ""
    company: str = ""
    company_logo: str = ""
    location: str = ""
    source: str = ""
    added_at: str | None = None
    posted_at: str = ""
    apply_url: str = ""
    score: int | None = Field(default=None, ge=0, le=100)
    score_method: str = ""
    requirement_set_id: str = ""
    requirement_extraction_model: str = ""
    requirement_extraction_version: str = ""
    requirement_verdicts: list[VerifiedRequirement] = Field(default_factory=list)
    fit_category: Literal["strong_match", "review", "not_suitable"] = "review"
    verification: Literal["unverified"] = "unverified"
    work_type: Literal["remote", "hybrid", "on-site", "unknown"] = "unknown"
    rationale: str = ""
    mismatch_reason: str = ""
    missing_skills: list[str] = Field(default_factory=list)
    job_description: str = ""
    description_available: bool | None = None
    about_company: str = ""
    candidate_requirements: list[str] = Field(default_factory=list)
    salary: str | None = None
    evaluation_model_id: str = ""

    # Expose the posting date under the frontend-compatible alias.
    @computed_field
    @property
    def postedAt(self) -> str:
        return self.posted_at

    # Expose the application URL under the frontend-compatible alias.
    @computed_field
    @property
    def applyUrl(self) -> str:
        return self.apply_url

    # Expose the fit category through the event contract alias.
    @computed_field
    @property
    def verdict(self) -> str:
        return self.fit_category

    # Expose missing skills through the frontend-compatible alias.
    @computed_field
    @property
    def missingSkills(self) -> list[str]:
        return self.missing_skills


# Expose an actionable assessment failure without storing raw provider responses.
class EvaluationError(BaseModel):
    provider: str = ""
    title: str = ""
    company: str = ""
    company_logo: str = ""
    apply_url: str = ""
    category: str = ""
    message: str = ""
    skipped: bool = False


# One search's time and scope, oldest first.
class SearchRecord(BaseModel):
    at: str
    platforms: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)


# Describe the authoritative workspace state consumed by polling and streaming clients.
class RunSnapshot(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    runId: str = ""
    saved_profile_id: str | None = None
    saved_profile_name: str = ""
    profile_save_error: str | None = None
    status: Literal["running", "awaiting_search", "complete", "error", "cancelled"]
    phase: int = 0
    phases: dict[str, Literal["pending", "active", "done", "failed"]] = Field(
        default_factory=dict
    )
    profile: ResumeProfile | None = None
    search_inputs: dict = Field(default_factory=dict)
    message: str = ""
    error: str | None = None
    last_search_added: int = 0
    searches: list[SearchRecord] = Field(default_factory=list)
    jobs_found: int = 0
    jobs_screened: int = 0
    evaluation_total: int = 0
    evaluated_jobs: int = 0
    evaluation_failed: int = 0
    # A targeted retry's own progress (model assessments); 0 when no retry is running.
    retry_total: int = 0
    retry_done: int = 0
    displayed_jobs: int = 0
    excluded_jobs: int = 0
    recommendations: list[JobResult] = Field(default_factory=list)
    excluded_recommendations: list[JobResult] = Field(default_factory=list)
    evaluation_errors: list[EvaluationError] = Field(default_factory=list)
    scrape_errors: list[str] = Field(default_factory=list)
    skipped_models: list[str] = Field(default_factory=list)
    busy_boards: list[str] = Field(default_factory=list)
    evaluation_model_id: str = ""
    evaluation_model: str = ""
    revision: int = 0
    worker_active: bool = False


# Return both identifier spellings used by supported API clients.
class RunCreated(BaseModel):
    id: str
    runId: str


# Describe a selectable provider and its configured model.
class ModelOption(BaseModel):
    model_id: str = ""
    value: str
    label: str


class ApiKeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str = Field(max_length=500)


class ApiKeyStatus(BaseModel):
    provider: str
    label: str
    source: Literal["settings", "env"] | None
    hint: str


class DismissalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["role", "location", "seniority", "salary", "other"]
    minimum_salary: float | None = Field(
        default=None, gt=0, le=10000000, allow_inf_nan=False
    )
    currency: Literal["AUD", "USD", "GBP", "EUR", "CAD", "NZD"] | None = None
    period: Literal["year", "hour"] | None = None

    @model_validator(mode="after")
    def salary_details(self):
        if self.reason == "salary":
            if (
                self.minimum_salary is None
                or self.currency is None
                or self.period is None
            ):
                raise ValueError(
                    "Salary feedback needs a minimum, currency and pay period."
                )
        elif any(
            value is not None
            for value in (self.minimum_salary, self.currency, self.period)
        ):
            raise ValueError("Salary details apply only to salary feedback.")
        return self


class DismissalPreference(DismissalInput):
    title: str = ""
    location: str = ""
    seniority: str = ""


class JobActionUpdate(BaseModel):
    key: str = Field(min_length=1, max_length=4096)
    action: Literal["saved", "dismissed", "applied"]
    value: bool
    dismissal: DismissalInput | None = None

    @model_validator(mode="after")
    def dismissal_only(self):
        if self.dismissal is not None and (
            self.action != "dismissed" or not self.value
        ):
            raise ValueError("Dismissal feedback requires a dismissed job.")
        return self


class JobActions(BaseModel):
    actions: dict[str, dict[Literal["saved", "dismissed", "applied"], bool]] = Field(
        default_factory=dict
    )

    dismissal_feedback: dict[str, DismissalPreference] = Field(default_factory=dict)
