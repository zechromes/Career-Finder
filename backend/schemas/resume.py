"""Validation models for resume; independent of processing logic."""

from typing import List, Literal
from pydantic import BaseModel, Field


class ResumeDocumentCheck(BaseModel):
    """Document classification, separate from candidate profile evidence."""

    document_type: Literal["resume", "not_resume", "uncertain"] = Field(
        description="Whether the document presents an individual's resume/CV, is another document type, or cannot be identified reliably."
    )


class ResumeProfile(BaseModel):
    name: str = ""
    headline: str = ""
    work_history: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    tech_skills: List[str] = Field(
        default_factory=list,
        description="List of Familiar Programming Languages or Frameworks (e.g. Python, C++, JavaScript, Java, ReactJS, NodeJS)",
    )
    soft_skills: List[str] = Field(
        default_factory=list,
        description="List of Soft skills (e.g. Responsibility, Curiosity, Leadership)",
    )
    years_of_experience: float | None = Field(
        default=None,
        ge=0,
        description="Completed years of paid professional employment, excluding degree duration, coursework and personal/academic projects. Avoid double-counting overlapping dates. Do not round internships up to full years.",
    )
    career_level: Literal["graduate", "entry", "junior", "mid", "senior", "unknown"] = (
        Field(
            default="unknown",
            description="Career level supported by professional scope and tenure, not degree level or technology keywords.",
        )
    )
    experience_evidence: List[str] = Field(
        default_factory=list,
        description="Brief resume evidence for employment tenure and responsibility; explicitly identify internships and academic work.",
    )
    preferred_domains: List[str] = Field(
        default_factory=list,
        description="Domain of Interest (e.g. AI Engineer, Software Engineer, Full Stack Web Developer)",
    )
    profile: str = Field(
        default="",
        description="A brief summary of candidate's professional bacground and academic focus",
    )


class ResumeIntake(BaseModel):
    document_type: Literal["resume", "not_resume", "uncertain"]
    profile: ResumeProfile | None
