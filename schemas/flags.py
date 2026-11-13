"""Flags (section 9.4)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from schemas.entities import Span


class FlagAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["dismiss", "for_dentist", "resolve", "comment"]
    by_role: Literal["Dentist", "Assistant"]
    reason: str = ""
    timestamp: str


class Flag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    origin: str
    rule_id: str
    rule_version: str = "1"
    rule_status: Literal["pending", "approved", "technical"] = "technical"
    severity: Literal["low", "medium", "high"]
    safety_critical: bool = False
    precautionary: bool = False
    question: bool = False
    message: str
    entity_ids: list[str] = Field(default_factory=list)
    entity_refs: list[str] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    evidence: list[Span] = Field(default_factory=list)
    graph_version: int
    inputs_hash: str = ""
    history: list[FlagAction] = Field(default_factory=list)
    group_id: Optional[str] = None
    target: Optional[int] = None
    problem_id: Optional[str] = None
