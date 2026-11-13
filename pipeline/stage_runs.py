"""Stage run records (section 10.1): execution history, kept outside the snapshot and its hash."""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.storage import atomic_write_json, now, read_json

TERMINAL = {"succeeded", "failed", "blocked", "not_applicable"}
_lock = threading.Lock()


@dataclass
class StageRunLog:
    path: Path | None = None
    runs: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.path is not None:
            self.runs = read_json(self.path, [])

    def record(self, stage: str, agent: str, status: str, *, inputs_hash: str = "", started: str | None = None,
               error: str | None = None, blocked_by: str | None = None, run_id: str | None = None,
               extra: dict | None = None) -> dict:
        assert status in TERMINAL, status
        rec = {"id": f"sr_{uuid.uuid4().hex[:10]}", "stage": stage, "agent": agent, "status": status,
               "blocked_by": blocked_by, "error": error, "inputs_hash": inputs_hash,
               "started": started or now(), "finished": now(), "run_id": run_id, **(extra or {})}
        with _lock:
            self.runs.append(rec)
            if self.path is not None:
                atomic_write_json(self.path, self.runs)
        return rec

    def for_run(self, run_id: str) -> list[dict]:
        return [r for r in self.runs if r.get("run_id") == run_id]

    def latest(self, run_id: str, stage: str, agent: str | None = None) -> dict | None:
        cands = [r for r in self.for_run(run_id) if r["stage"] == stage and (agent is None or r["agent"] == agent)]
        return cands[-1] if cands else None

    def get(self, run_record_id: str) -> dict | None:
        return next((r for r in self.runs if r["id"] == run_record_id), None)


def session_stage_log(session) -> StageRunLog:
    return StageRunLog(path=session.path("stage_runs.json"))
