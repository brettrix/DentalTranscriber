"""Sources and overlays (section 5). Sources are immutable once written; overlays are versioned."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Utterance(Strict):
    id: str
    speaker: str
    start: Optional[float] = None
    end: Optional[float] = None
    text: str


class UtterancesSource(Strict):
    version: int = 1
    provider: str
    utterances: list[Utterance]


class QuickNote(Strict):
    id: str
    text: str


class QuickNotesSource(Strict):
    version: int = 1
    notes: list[QuickNote] = Field(default_factory=list)


class VisitMeta(Strict):
    version: int = 1
    date: Optional[str] = None
    provider: Optional[str] = None
    assistant: Optional[str] = None
    visit_type: str = "limited exam"


class RoleEntry(Strict):
    role: Literal["Dentist", "Assistant", "Patient", "Other"]
    set_by: str


class RolesOverlay(Strict):
    version: int = 1
    entries: dict[str, RoleEntry] = Field(default_factory=dict)
    confirmed: bool = False


class Correction(Strict):
    id: str
    utterance_id: str
    start: int
    end: int
    raw_text: str
    proposed_text: str
    category: Literal["formatting", "term", "critical"]
    status: Literal["proposed", "accepted", "rejected", "pending_human", "confirmed_by_human"]
    confirmed_by: Optional[str] = None
    confirmed_without_audio: bool = False
    version: int = 1


class CorrectionsOverlay(Strict):
    version: int = 1
    corrections: list[Correction] = Field(default_factory=list)
