"""Validation models for saved profiles; independent of processing logic."""

from pydantic import BaseModel, Field, field_validator
from backend.schemas.resume import ResumeProfile
from backend.schemas.contracts import Preferences, DismissalPreference


class SavedProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    profile: ResumeProfile
    preferences: Preferences | None = None
    source_run_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")

    # Reject whitespace-only names after normalizing user input.
    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Enter a profile name.")
        return value


class SavedProfile(SavedProfileInput):
    id: str
    created_at: float
    updated_at: float
    resume_available: bool = False
    job_actions: dict[str, dict[str, bool]] = Field(default_factory=dict)

    dismissal_feedback: dict[str, DismissalPreference] = Field(default_factory=dict)
