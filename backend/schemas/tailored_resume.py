"""A resume rewritten for one job from the candidate's own resume; nothing is added."""

from pydantic import BaseModel, Field


class TailoredEntry(BaseModel):
    # The position title, degree or project name; organisation and location as the resume
    # states them. Older saved resumes hold everything in heading, with the other two empty.
    heading: str
    organization: str = ""
    location: str = ""
    dates: str = ""
    bullets: list[str] = Field(default_factory=list)


class TailoredSection(BaseModel):
    title: str
    entries: list[TailoredEntry] = Field(default_factory=list)


class TailoredResumeDraft(BaseModel):
    """What the model writes."""

    name: str = ""
    headline: str = ""
    contact: list[str] = Field(default_factory=list)
    # Career profile: 3 to 5 tailored summary points.
    profile_points: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    sections: list[TailoredSection] = Field(default_factory=list)
    # Job requirements the resume shows no evidence for; never written into the resume.
    gaps: list[str] = Field(default_factory=list)


class TailoredResume(TailoredResumeDraft):
    # A paragraph summary from resumes generated before the career profile existed.
    summary: str = ""
    # Lines naming a skill or figure the original resume does not contain; check before use.
    unverified: list[str] = Field(default_factory=list)
    model: str = ""
    generated_at: float = 0


class TailoredResumeRequest(BaseModel):
    key: str = Field(min_length=1, max_length=4096)
