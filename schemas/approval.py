"""Approval records (section 11.2)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["assistant_review_complete", "dentist_approved", "exported"]
    snapshot_version: int
    snapshot_hash: str
    note_hash: str
    render_config_hash: str
    overlay_versions: dict[str, int]
    source_hashes: dict[str, str]
    rule_file_hashes: dict[str, str]
    rule_mode: str
    execution_record_ids: list[str] = Field(default_factory=list)
    approver_role: Literal["Dentist", "Assistant"]
    timestamp: str
    for_dentist: list[str] = Field(default_factory=list)


class ApprovalState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["draft", "assistant_review_complete", "dentist_approved", "exported"] = "draft"
    records: list[ApprovalRecord] = Field(default_factory=list)
    revoked: list[dict] = Field(default_factory=list)
    export_path: Optional[str] = None
