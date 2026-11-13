"""Trace logging: one append-only record per model call (never contains API keys or full prompts)."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.storage import append_jsonl, now, read_jsonl


@dataclass
class Tracer:
    path: Path | None = None
    graph_version: int | None = None
    run_id: str | None = None
    records: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, **record) -> dict:
        record = {"timestamp": now(), "graph_version": self.graph_version, "run_id": self.run_id, **record}
        with self._lock:
            self.records.append(record)
        if self.path is not None:
            append_jsonl(self.path, record)
        return record

    def totals(self) -> dict:
        calls = [r for r in self.records if r.get("kind") == "model_call"]
        return {"calls": len(calls),
                "input_tokens": sum(r.get("input_tokens") or 0 for r in calls),
                "output_tokens": sum(r.get("output_tokens") or 0 for r in calls),
                "seconds": round(sum(r.get("seconds") or 0 for r in calls), 2)}


def session_tracer(session, graph_version=None, run_id=None) -> Tracer:
    return Tracer(path=session.path("traces.jsonl"), graph_version=graph_version, run_id=run_id)


def read_traces(session) -> list[dict]:
    return read_jsonl(session.path("traces.jsonl"))
