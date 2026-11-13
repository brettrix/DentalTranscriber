"""Conflicts (section 6.6)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from schemas.entities import Span


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Participant(Strict):
    entity_id: str
    version: int


class Resolution(Strict):
    action: Literal["select", "supersede", "keep_both", "replace"]
    active_entity_id: Optional[str] = None       # select
    superseded_entity_id: Optional[str] = None   # supersede
    replacement_entity_id: Optional[str] = None  # replace (a human-entry item)
    explanation: Optional[str] = None            # keep_both (required)
    resolver_role: Literal["Dentist", "Assistant"]
    reason: str
    participant_versions: list[Participant]
    timestamp: str
    pending_change_id: Optional[str] = None      # assistant resolution of critical content awaiting the dentist


class Conflict(Strict):
    id: str
    kind: Literal["quick_note_vs_transcript", "self_correction", "contradiction"]
    participants: list[Participant]
    evidence: list[Span]
    later_statement: Optional[Span] = None
    subject: Optional[str] = None
    status: Literal["open", "resolved"] = "open"
    resolution: Optional[Resolution] = None
    origin: str = "R2"
