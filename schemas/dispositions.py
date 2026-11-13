"""Dispositions (6.7), human-review tasks (6.8), section records (6.5), pending changes (11.1)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from schemas.conflicts import Participant
from schemas.entities import Span


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Disposition(Strict):
    id: str
    subject_type: Literal["entity", "section", "task", "stage_run", "conflict_resolution"]
    subject_id: str
    subject_hashes: dict[str, Any]
    kind: Literal["human_entered", "human_reviewed", "dentist_confirmed", "section_reviewed", "task_completed"]
    by_role: Literal["Dentist", "Assistant", "System"]
    reason: str = ""
    timestamp: str
    outcome: Optional[Literal["completed", "not_discussed"]] = None      # section_reviewed
    completion: Optional[Literal["corrected", "accepted", "not_applicable"]] = None  # task_completed
    cites: list[str] = Field(default_factory=list)


class Task(Strict):
    id: str
    kind: str
    reason: str
    evidence: list[Span] = Field(default_factory=list)
    participants: list[Participant] = Field(default_factory=list)
    rule_hash: Optional[str] = None
    inputs_hash: str
    created_by_stage: str
    status: Literal["open", "completed"] = "open"
    disposition_id: Optional[str] = None
    severity: Literal["low", "medium", "high"] = "medium"
    staging_ids: list[str] = Field(default_factory=list)
    section: Optional[str] = None
    stage_run_id: Optional[str] = None


class SectionRecord(Strict):
    section: str
    owner: str
    status: Literal["completed", "failed", "not_run"]
    entities: int = 0
    version: int = 1


class PendingChange(Strict):
    id: str
    operation: Literal["add", "edit", "remove", "replace", "resolve_conflict"]
    target_versions: list[Participant] = Field(default_factory=list)
    proposed_content: Optional[dict] = None
    conflict_id: Optional[str] = None
    by_role: Literal["Assistant"]
    reason: str
    timestamp: str
    status: Literal["pending", "accepted", "rejected"] = "pending"
