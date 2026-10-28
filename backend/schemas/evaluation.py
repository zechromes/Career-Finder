"""Validation models for evaluation; independent of processing logic."""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class IdentifiedRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement: str
    importance: Literal["must_have", "nice_to_have", "unclear"]
    job_quote: str
    section: str
    type: Literal[
        "skill", "experience", "education", "eligibility", "responsibility", "other"
    ]


class ExtractedRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirements: list[IdentifiedRequirement]


class SharedRequirement(IdentifiedRequirement):
    requirement_id: str


class RequirementSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posting_hash: str
    extraction_version: str
    extraction_model: str
    requirements: list[SharedRequirement]


class RequirementVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement: str
    importance: Literal["must_have", "nice_to_have", "unclear"]
    requirement_id: str = ""
    section: str = ""
    type: Literal[
        "skill", "experience", "education", "eligibility", "responsibility", "other"
    ] = "other"
    verdict: Literal["met", "partial", "not_met", "unknown"]
    job_quote: str
    resume_quote: str = ""
    explanation: str = ""


class JobEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_verdicts: list[RequirementVerdict] = Field(
        default_factory=list,
        description="Return one verdict for every shared requirement_id, preserving its canonical fields exactly. Quote resume evidence verbatim. Missing resume evidence is unknown, not not_met.",
    )
    score: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Evidence-based fit score 0-100: 80-100 strong match, 40-79 review, 0-39 unsuitable. Not a probability.",
    )
    work_type: Literal["remote", "hybrid", "on-site", "unknown"] = Field(
        default="unknown",
        description="Work arrangement explicitly stated in the job. Unknown if absent.",
    )
    about_company: str = Field(
        default="",
        description="Company overview supported only by the job posting; empty if absent.",
    )
    candidate_requirements: list[str] = Field(
        default_factory=list,
        description="Copy requirement text from the shared criteria list; never independently identify additional requirements.",
    )
    salary: Optional[str] = Field(
        default=None,
        description="Salary explicitly stated in the posting, preserving currency, range, pay period and qualifiers. Never estimate; null if absent.",
    )
    experience_alignment: Literal["meets", "gap", "unknown"] = Field(
        default="unknown",
        description="Does professional experience and scope meet the job's mandatory requirements?",
    )
    minimum_professional_years: Optional[float] = Field(
        default=None,
        ge=0,
        description="Explicit mandatory minimum professional years; null if absent or only preferred.",
    )
    required_experience_evidence: str = Field(
        default="",
        description="Verbatim job text supporting the mandatory experience/seniority requirement, or empty if unknown.",
    )
    fit_category: Literal["strong_match", "review", "not_suitable"] = Field(
        default="review",
        description="Overall candidate suitability: strong_match, review, or not_suitable.",
    )
    mismatch_reason: str = Field(
        default="",
        description="Short reason for review or not_suitable, especially an experience or seniority mismatch.",
    )
    is_strong_fit: bool = Field(
        default=False,
        description="Is the candidate a strong fit for this role based purely on their technical stack and experience?",
    )
    match_rationale: str = Field(
        description="A 2-sentence evidence-based explanation of whether the candidate meets the role's experience and core requirements, including any gaps."
    )
    missing_skills: list[str] = Field(
        description="Specific technical skills required by the job that are missing from the resume."
    )
    apply_url: str = Field(
        description="The exact URL to apply for the job from the provided metadata."
    )


class ReferencedRequirement(BaseModel):
    """Extraction-only source coordinates; persisted criteria keep exact quotes."""

    model_config = ConfigDict(extra="forbid")
    requirement: str
    importance: Literal["must_have", "nice_to_have", "unclear"]
    type: Literal[
        "skill", "experience", "education", "eligibility", "responsibility", "other"
    ]
    source_start: int = Field(strict=True, ge=1)
    source_end: int = Field(strict=True, ge=1)
    section: str


class ReferencedRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirements: list[ReferencedRequirement]
