"""Flags (9.4): construction with inputs hashes, the flag merger, and human flag actions."""
from __future__ import annotations

from pipeline.storage import atomic_write_json, hash_obj, now, read_json
from schemas.flags import Flag, FlagAction


def make_flag(rule_id: str, cfg: dict, *, severity: str, message: str, graph, entities=(), conflict_ids=(),
              task_ids=(), evidence=(), safety_critical: bool | None = None, precautionary: bool = False,
              origin: str = "E2", rule_hash: str = "", target: int | None = None, problem_id: str | None = None,
              question: bool | None = None, rule_status: str | None = None) -> Flag:
    ents = list(entities)
    evidence = list(evidence) or [s for e in ents for s in e.evidence[:2]]
    conflicts = [graph.conflict(c) for c in conflict_ids]
    tasks = [graph.task(t) for t in task_ids]
    inputs = {"rule": rule_id, "rule_hash": rule_hash, "entities": sorted(e.ref for e in ents),
              "entity_hashes": sorted(f"{e.content_hash}:{e.support_hash}" for e in ents),
              "conflicts": sorted(f"{c.id}:{c.status}" for c in conflicts if c),
              "tasks": sorted(f"{t.id}:{t.inputs_hash}" for t in tasks if t),
              "evidence": sorted(f"{s.source_id}:{s.start}-{s.end}" for s in evidence), "target": target,
              "severity": severity}
    stable = hash_obj([rule_id, sorted(e.id for e in ents), sorted(conflict_ids), sorted(task_ids), target,
                       problem_id])[:12]
    status = rule_status or ("technical" if cfg.get("class") == "technical" else cfg.get("status", "pending"))
    return Flag(id=f"fl_{stable}", origin=origin, rule_id=rule_id, rule_version=str(cfg.get("version", "1")),
                rule_status=status, severity=severity,
                safety_critical=cfg.get("safety_critical", False) if safety_critical is None else safety_critical,
                precautionary=precautionary, question=cfg.get("question", False) if question is None else question,
                message=message, entity_ids=[e.id for e in ents], entity_refs=[e.ref for e in ents],
                conflict_ids=list(conflict_ids), task_ids=list(task_ids), evidence=evidence,
                graph_version=graph.version, inputs_hash=hash_obj(inputs), target=target, problem_id=problem_id)


RULE_FAMILY = {
    "treatment_target_mismatch": "target", "treatment_target_disagreement": "target",
    "unexplained_other_tooth": "target", "complaint_location_differs": "target",
    "quick_note_target_conflict": "quick_note", "quick_note_complaint_mismatch": "quick_note",
    "quick_note_tooth_unclear": "quick_note", "open_conflict": "conflict", "open_review_task": "task",
    "stage_failure": "task", "unknown_option_link": "task",
}


def merge_flags(flags: list[Flag]) -> list[Flag]:
    """Group flags that cite the same entities and rule family. Every original flag is kept; none is deleted
    or downgraded. Exact duplicates (same id) collapse to one."""
    by_id: dict[str, Flag] = {}
    for f in flags:
        by_id.setdefault(f.id, f)
    out = list(by_id.values())
    groups: dict[tuple, str] = {}
    for f in out:
        key = (RULE_FAMILY.get(f.rule_id, f.rule_id), tuple(sorted(f.entity_ids)) or tuple(sorted(f.task_ids)))
        groups.setdefault(key, f"gr_{hash_obj(list(key))[:8]}")
        f.group_id = groups[key]
    sev = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda f: (sev[f.severity], not f.safety_critical, f.rule_id, f.id))


# ---------------------------------------------------------------- human actions on flags

class FlagActions:
    """flag_actions.json, keyed by flag inputs_hash: actions carry over only while the inputs are unchanged."""

    def __init__(self, path=None):
        self.path = path
        self.data: dict[str, list[dict]] = read_json(path, {}) if path is not None else {}

    def add(self, flag: Flag, action: str, by_role: str, reason: str = "") -> FlagAction:
        act = FlagAction(action=action, by_role=by_role, reason=reason, timestamp=now())
        self.data.setdefault(flag.inputs_hash, []).append(act.model_dump())
        if self.path is not None:
            atomic_write_json(self.path, self.data)
        return act

    def apply(self, flags: list[Flag]) -> list[Flag]:
        for f in flags:
            f.history = [FlagAction(**a) for a in self.data.get(f.inputs_hash, [])]
        return flags


def flag_state(flag: Flag) -> str:
    """open | for_dentist | dismissed_by_assistant | dismissed_by_dentist | resolved."""
    state = "open"
    for a in flag.history:
        if a.action == "dismiss":
            state = "dismissed_by_dentist" if a.by_role == "Dentist" else "dismissed_by_assistant"
        elif a.action == "for_dentist" and state == "open":
            state = "for_dentist"
        elif a.action == "resolve":
            state = "resolved"
    return state


def session_flag_actions(session) -> FlagActions:
    return FlagActions(session.path("flag_actions.json"))
