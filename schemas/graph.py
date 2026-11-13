"""The clinical snapshot (section 6). Execution history lives elsewhere and is not hashed here."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from schemas.conflicts import Conflict
from schemas.dispositions import Disposition, PendingChange, SectionRecord, Task
from schemas.entities import Entity


class Graph(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 0
    pipeline_mode: str = "team"
    frozen: bool = False
    stale: bool = False
    overlay_versions: dict[str, int] = Field(default_factory=dict)
    source_hashes: dict[str, str] = Field(default_factory=dict)
    entities: list[Entity] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    dispositions: list[Disposition] = Field(default_factory=list)
    tasks: list[Task] = Field(default_factory=list)
    section_records: list[SectionRecord] = Field(default_factory=list)
    pending_changes: list[PendingChange] = Field(default_factory=list)
    parent_version: Optional[int] = None

    # ---- lookups
    def active(self, kind: str | None = None):
        return [e for e in self.entities if e.status == "active" and (kind is None or e.kind == kind)]

    def get(self, entity_id: str, version: int | None = None):
        cands = [e for e in self.entities if e.id == entity_id]
        if version is not None:
            cands = [e for e in cands if e.version == version]
            return cands[0] if cands else None
        act = [e for e in cands if e.status == "active"]
        if act:
            return act[0]
        return max(cands, key=lambda e: e.version) if cands else None

    def active_items(self, *types: str):
        return [e for e in self.active("item") if not types or e.type in types]

    def chief(self):
        chiefs = [p for p in self.active("problem") if p.role == "chief"]
        return chiefs[0] if len(chiefs) == 1 else None

    def disposition(self, disp_id: str):
        return next((d for d in self.dispositions if d.id == disp_id), None)

    def task(self, task_id: str):
        return next((t for t in self.tasks if t.id == task_id), None)

    def conflict(self, conflict_id: str):
        return next((c for c in self.conflicts if c.id == conflict_id), None)
