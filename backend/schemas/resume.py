"""Validation models for resume; independent of processing logic."""

from typing import List, Literal
from pydantic import BaseModel, Field, model_validator


class ResumeDocumentCheck(BaseModel):
    """Document classification, separate from candidate profile evidence."""

    document_type: Literal["resume", "not_resume", "uncertain"] = Field(
        description="Whether the document presents an individual's resume/CV, is another document type, or cannot be identified reliably."
    )


class ResumeSection(BaseModel):
    heading: str = Field(description="The section heading exactly as the resume writes it.")
    entries: list[str] = Field(
        default_factory=list,
        description="Each item in the section as 'Title | Context | Month Year – Month Year | Details', keeping only the parts the resume gives, with its tools, scope and outcomes.",
    )


class SkillGroup(BaseModel):
    name: str = Field(description="A short area of work, for example 'LLM applications', 'Backend' or 'Data analysis'.")
    skills: list[str] = Field(default_factory=list, description="Skills from tech_skills, written exactly as listed there.")
    query: str = Field(
        default="",
        description=(
            "One 15-35 word sentence a job ad would use for this kind of work, for example "
            "'Build and deploy backend REST APIs using Python, FastAPI and PostgreSQL.' Name the "
            "mainstream tools employers list and describe niche models or tools by their category "
            "('U-Net' becomes 'image segmentation models'). Leave out project, dataset and domain "
            "details, team words such as 'collaboratively', and work the resume does not show."
        ),
    )


class EntryEvidence(BaseModel):
    entry: str = Field(description="One work_history, sections or education entry, copied exactly as written there.")
    type: Literal["job", "internship", "project", "hackathon", "education", "other"] = Field(
        default="other",
        description="What kind of experience the entry is. Paid employment is 'job'; personal, academic or employer-unspecified projects are 'project'.",
    )
    end: str = Field(
        default="",
        description="When the entry ended as YYYY-MM, 'present' if ongoing, or empty if the entry gives no date.",
    )
    summary: str = Field(
        default="",
        description="One sentence written like a job-posting responsibility, using only what the entry says. No company, product or award names, dates, money figures, or notes such as 'context not specified'.",
    )
    hard_skills: list[str] = Field(
        default_factory=list,
        description="Programming languages, frameworks, libraries, platforms, tools and techniques the entry shows were used, named the way job postings list requirements. Include the language a named framework or library is written in. Leave out features or results of what was built, metrics and task descriptions, and anything the entry does not support.",
    )
    soft_skills: list[str] = Field(
        default_factory=list,
        description="Soft skills the entry shows through a described action, each named with the common term job postings use (for example 'Mentoring' for 'mentored two interns'), not a coined phrase. Never list one without such an action.",
    )


class ExtractedProfile(BaseModel):
    """What the extraction model fills from the resume."""

    section_headings: list[str] = Field(
        default_factory=list,
        description="Every section heading in the resume, in order, exactly as written. List them before filling the other fields so no section is skipped.",
    )
    name: str = ""
    headline: str = ""
    work_history: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    sections: list[ResumeSection] = Field(
        default_factory=list,
        description="Every other resume section under its own heading, for example Projects, Certifications, Publications, Volunteering, Awards, Research, Leadership or Languages. Leave out what is already in work_history, education, skills or the summary, and contact details. Evidence of skills, never of employment years.",
    )
    tech_skills: List[str] = Field(
        default_factory=list,
        description="List of Familiar Programming Languages or Frameworks (e.g. Python, C++, JavaScript, Java, ReactJS, NodeJS)",
    )
    skill_groups: list[SkillGroup] = Field(
        default_factory=list,
        description="Every tech_skills entry placed in exactly one group of related skills, so each group describes one kind of work.",
    )
    keyword_queries: list[str] = Field(
        default_factory=list,
        description="One or two lines of 6-12 space-separated terms from tech_skills for exact matching against job ads, most important first, for example 'Python FastAPI React PostgreSQL Docker'. Use names employers list; no soft skills, no terms the resume does not support.",
    )
    soft_skills: List[str] = Field(
        default_factory=list,
        description="List of Soft skills (e.g. Responsibility, Curiosity, Leadership)",
    )
    entry_evidence: list[EntryEvidence] = Field(
        default_factory=list,
        description="One item per work_history, sections and education entry: what was done there and the hard and soft skills it demonstrates.",
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
        description="Three to six realistic job titles to search for now, inferred from the whole resume (work history, sections, education and skills) at the candidate's career level, for example 'Graduate Data Analyst' or 'Junior Python Developer', including common variants employers use for the same work. Include a stated interest only when the resume supports it.",
    )
    target_roles_reason: str = Field(
        default="",
        description="One or two sentences on why these job titles fit, citing the resume evidence and career level.",
    )
    profile: str = Field(
        default="",
        description="A brief summary of candidate's professional bacground and academic focus",
    )

    @model_validator(mode="before")
    @classmethod
    def projects_become_a_section(cls, data):
        """Older saved profiles kept projects in their own list."""
        if isinstance(data, dict) and "projects" in data:
            data = dict(data)
            projects = data.pop("projects") or []
            sections = list(data.get("sections") or [])
            headings = {
                str(item.get("heading", "") if isinstance(item, dict) else item.heading)
                .strip()
                .lower()
                for item in sections
            }
            if projects and "projects" not in headings:
                sections.insert(0, {"heading": "Projects", "entries": projects})
            data["sections"] = sections
        return data


class ResumeProfile(ExtractedProfile):
    # The original resume text, kept so evaluators can quote what extraction missed.
    # Set by the application, never by the extraction model.
    source_text: str = ""


class ResumeIntake(BaseModel):
    document_type: Literal["resume", "not_resume", "uncertain"]
    profile: ExtractedProfile | None
