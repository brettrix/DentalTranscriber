"""Gold annotation schema (section 14.2), separate from the graph schema."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class GoldEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    utterance_id: Optional[str] = None
    quick_note_id: Optional[str] = None
    time_range: Optional[list[float]] = None


class GoldEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gid: str
    kind: str
    type: Optional[str] = None
    problem_key: Optional[str] = None
    scope: Optional[str] = None
    target: Optional[int] = None
    target_relation: Optional[str] = None
    key_attributes: dict[str, Any] = Field(default_factory=dict)
    assertion: Optional[str] = None
    time_context: Optional[str] = None
    assertion_source: Optional[str] = None
    action: Optional[str] = None
    status_fields: dict[str, Any] = Field(default_factory=dict)
    evidence: list[GoldEvidence] = Field(default_factory=list)
    note: Optional[str] = None


class GoldFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str
    problem_key: Optional[str] = None
    target: Optional[int] = None
    meaning: str
    evidence: list[GoldEvidence] = Field(default_factory=list)


class GoldCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    annotated_by: str
    checked_by: Optional[str] = None
    entities: list[GoldEntity]
    expected_flags: list[GoldFlag] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    expected_decision: Optional[str] = None
    notes: Optional[str] = None
