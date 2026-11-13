"""Stage F status (section 12)."""
from __future__ import annotations

from collections import Counter

from pipeline.stage_runs import TERMINAL

TERMINAL_CHECKS = {"pass", "fail", "not_applicable", "not_assessed_due_to_failure", "unconfirmed"}


def compute_status(graph, stage_runs: list[dict], flags, mode: str, rule_mode: str, expected_stages: list[str]) -> dict:
    recorded = {(r["stage"], r["agent"]) for r in stage_runs if r["status"] in TERMINAL}
    missing = [s for s in expected_stages if tuple(s.split("/", 1)) not in recorded]
    processing_finished = not missing
    counts = {k: Counter() for k in ("span_valid", "normalization_valid", "semantic_support")}
    unfinished = []
    if graph is not None:
        for e in graph.active():
            if e.is_human:
                continue
            for k in counts:
                v = getattr(e.checks, k)
                counts[k][v] += 1
                if v not in TERMINAL_CHECKS:
                    unfinished.append(f"{e.ref}:{k}")
    checks_finished = graph is not None and not unfinished
    open_conflicts = [c.id for c in graph.conflicts if c.status == "open"] if graph else []
    open_tasks = [t.id for t in graph.tasks if t.status == "open"] if graph else []
    incomplete = [s.section for s in graph.section_records if s.status in ("failed", "not_run")] if graph else []
    return {
        "processing_finished": processing_finished,
        "missing_stage_runs": missing,
        "checks_finished": checks_finished,
        "unfinished_checks": unfinished,
        "check_counts": {k: dict(v) for k, v in counts.items()},
        "ready_for_review": processing_finished and checks_finished,
        "high_flags": sum(1 for f in flags if f.severity == "high"),
        "safety_critical_flags": sum(1 for f in flags if f.safety_critical),
        "open_conflicts": len(open_conflicts),
        "open_tasks": len(open_tasks),
        "incomplete_sections": incomplete,
        "failed_stages": [f"{r['stage']}/{r['agent']}" for r in stage_runs if r["status"] == "failed"],
        "verification_level": "span-checked (meaning not checked)" if mode == "baseline"
        else "span-checked and meaning-checked",
        "rule_mode": rule_mode,
    }
