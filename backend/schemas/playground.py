"""Playground responses: one pipeline stage run on its own, never saved."""

from typing import Literal

from pydantic import BaseModel, Field

from backend.schemas.resume import ResumeProfile


class UnsupportedEntry(BaseModel):
    field: str
    entry: str
    found_share: float


class UploadCheck(BaseModel):
    source_text_available: bool
    missing_fields: list[str]
    empty_sections: list[str]
    entries_checked: int
    unsupported_entries: list[UnsupportedEntry]
    skills_not_in_resume: list[str]
    years_check: str


class UploadPlayground(BaseModel):
    profile: ResumeProfile
    check: UploadCheck


class PlaygroundJob(BaseModel):
    title: str
    company: str
    location: str
    board: str
    posted_at: str
    url: str
    description_chars: int
    # Sent back to the retrieval stage; the playground keeps no server-side copy.
    description: str = ""


class DropCount(BaseModel):
    stage: str
    reason: str
    board: str
    count: int


class DroppedJob(BaseModel):
    title: str
    company: str
    location: str
    board: str
    posted_at: str = ""
    stage: str
    reason: str
    url: str


class IngestionPlayground(BaseModel):
    status: str
    messages: list[str]
    collected: dict[str, int]
    counts: list[DropCount]
    jobs: list[PlaygroundJob]
    dropped: list[DroppedJob]


class RetrievalRequest(BaseModel):
    profile: ResumeProfile
    queries: list[str] = Field(min_length=1, max_length=20)
    jobs: list[PlaygroundJob] = Field(min_length=1, max_length=1000)
    # -1 is Automatic: every job for pools up to 200, otherwise the top 100.
    top_k: Literal[-1, 0, 15, 50, 100] = -1
    seniority: Literal["auto", "any"] = "auto"
    # Matches the real search default (ranking.DEFAULT_QUERY_BUILDER).
    query_builder: Literal["evidence", "skills", "legacy", "hyde"] = "hyde"


class RetrievalQuery(BaseModel):
    text: str
    weight: float


class RankedJob(BaseModel):
    rank: int
    title: str
    company: str
    location: str
    board: str
    url: str
    above_level: bool


class RetrievalPlayground(BaseModel):
    queries: list[RetrievalQuery]
    ranked: list[RankedJob]
    total_jobs: int
