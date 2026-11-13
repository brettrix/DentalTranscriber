"""Revision-bound approval (11.2) and the approval matrix (11.3)."""
from __future__ import annotations

import json

from pipeline.dispositions import satisfying_disposition, section_reviewed
from pipeline.flags import flag_state
from pipeline.storage import atomic_write_bytes, atomic_write_json, now, read_json
from schemas.approval import ApprovalRecord, ApprovalState
from schemas.entities import is_critical
from schemas.flags import Flag

BANNER = "Prototype — test data only. Do not use with real patient information."
EXEMPT_TASK_STAGES = {"E"}  # an E3 failure means no review questions; the dentist *may* accept its task


def load_state(session) -> ApprovalState:
    return ApprovalState.model_validate(read_json(session.path("approval.json"), {}))


def save_state(session, state: ApprovalState) -> None:
    atomic_write_json(session.path("approval.json"), state)


def current_binding(session) -> dict:
    """What an approval binds to, recomputed from the session as it stands now."""
    from pipeline.graph import load_graph, snapshot_hash
    from pipeline.overlays import load_sources
    from pipeline.render import render_config_hash
    from pipeline.rules import rule_file_hashes
    graph = load_graph(session)
    sources = load_sources(session)
    latest = read_json(session.path("outputs", "latest.json"), {}) or {}
    return {"snapshot_version": graph.version if graph else None,
            "snapshot_hash": snapshot_hash(graph) if graph else None,
            "note_hash": (latest.get("note") or {}).get("note_hash"),
            "render_config_hash": render_config_hash(),
            "overlay_versions": sources.overlay_versions,
            "source_hashes": sources.hashes,
            "rule_file_hashes": rule_file_hashes(),
            "rule_mode": session.meta().get("rule_mode")}


BOUND_KEYS = ("snapshot_version", "snapshot_hash", "note_hash", "render_config_hash", "overlay_versions",
              "source_hashes", "rule_file_hashes", "rule_mode")


def binding_mismatches(record, binding: dict) -> list[str]:
    return [k for k in BOUND_KEYS if getattr(record, k) != binding.get(k)]


def revoke_if_changed(session, reason: str = "") -> bool:
    """Any change to sources, overlays, the snapshot, rule files or render configuration returns to draft."""
    state = load_state(session)
    if state.state == "draft" or not state.records:
        return False
    mism = binding_mismatches(state.records[-1], current_binding(session))
    if not mism:
        return False
    state.revoked.append({"from_state": state.state, "reason": reason, "changed": mism, "timestamp": now()})
    state.state = "draft"
    save_state(session, state)
    return True


# ---------------------------------------------------------------- the matrix

def _context(session):
    from pipeline.graph import load_graph
    from pipeline.linker import session_staging
    graph = load_graph(session)
    latest = read_json(session.path("outputs", "latest.json"), {}) or {}
    flags = [Flag.model_validate(f) for f in latest.get("flags", [])]
    from pipeline.flags import session_flag_actions
    session_flag_actions(session).apply(flags)
    return graph, flags, session_staging(session), latest


def blockers(session, target: str) -> list[str]:
    """What still blocks `assistant_review_complete` (target='assistant') or `dentist_approved` ('dentist')."""
    graph, flags, staging, latest = _context(session)
    out: list[str] = []
    if graph is None:
        return ["no candidate graph (a valid registry with a chief problem is required)"]
    if latest.get("graph_version") != graph.version or not latest.get("note"):
        out.append("derived outputs are not current for this graph version")
    mode = graph.pipeline_mode
    # Incomplete sections: both levels need a section_reviewed disposition.
    for s in graph.section_records:
        if s.status in ("failed", "not_run") and section_reviewed(graph, s.section) is None:
            out.append(f"section {s.section} is {s.status.replace('_', ' ')}: record a section review")
    # Failed or unassessed checks.
    flag_by_entity = {}
    for f in flags:
        for eid in f.entity_ids:
            flag_by_entity.setdefault((f.rule_id, eid), f)
    for e in graph.active():
        c = e.checks
        bad = any(v in ("fail", "not_assessed_due_to_failure") for v in
                  (c.span_valid, c.normalization_valid, c.semantic_support))
        if not bad or satisfying_disposition(graph, e) is not None:
            continue
        critical = is_critical(e)
        if target == "assistant":
            f = flag_by_entity.get(("unsupported_content", e.id))
            marked = f is not None and flag_state(f) == "for_dentist"
            if not critical:
                from pipeline.dispositions import bound_dispositions
                if not bound_dispositions(graph, e, {"human_reviewed", "dentist_confirmed"}):
                    out.append(f"{e.id}: failed/unassessed check needs a human review or correction")
            elif not marked:
                out.append(f"{e.id}: failed/unassessed critical check — confirm, correct, or mark for dentist")
        else:
            out.append(f"{e.id}: failed/unassessed check needs "
                       f"{'dentist confirmation' if critical else 'a human review or dentist confirmation'} "
                       f"or correction")
    # Pending critical changes.
    pend = [p for p in graph.pending_changes if p.status == "pending"]
    if target == "dentist":
        out += [f"pending change {p.id} ({p.operation}) needs the dentist to accept or reject it" for p in pend]
    # Conflicts.
    for c in graph.conflicts:
        open_ = c.status == "open" or (c.resolution is not None and c.resolution.pending_change_id and
                                       any(p.id == c.resolution.pending_change_id and p.status == "pending"
                                           for p in graph.pending_changes))
        if open_:
            if target == "dentist":
                out.append(f"conflict {c.id} must be resolved")
            elif not _marked(flags, conflict_id=c.id):
                out.append(f"conflict {c.id}: resolve or mark for dentist")
    # Staged records.
    last_run = session.meta().get("last_run")
    for r in [r for r in staging.open_records() if r.run_id == last_run]:
        if target == "dentist":
            out.append(f"staged record {r.id} must be converted to a human entry or discarded with a reason")
        elif not _marked(flags, task_id=r.task_id):
            out.append(f"staged record {r.id}: convert, discard, or mark for dentist")
    # Tasks.
    for t in graph.tasks:
        if t.status != "open":
            continue
        if t.kind == "stage_failure" and t.created_by_stage in EXEMPT_TASK_STAGES:
            continue
        if t.kind == "staged_record":
            continue  # covered by the staged-record row
        if target == "dentist":
            out.append(f"task {t.id} ({t.kind}) must be completed")
        elif not _marked(flags, task_id=t.id):
            out.append(f"task {t.id} ({t.kind}): complete or mark for dentist")
    # Flags.
    for f in flags:
        st = flag_state(f)
        if f.severity != "high" or f.rule_id in ("unsupported_content", "open_conflict", "open_review_task",
                                                  "incomplete_section"):
            continue  # those rows are checked above from the graph itself
        if f.safety_critical:
            if target == "assistant" and st not in ("for_dentist", "resolved", "dismissed_by_dentist"):
                out.append(f"safety-critical flag {f.rule_id}: correct or mark for dentist")
            if target == "dentist" and st not in ("dismissed_by_dentist", "resolved"):
                out.append(f"safety-critical flag {f.rule_id}: correct the entities or dismiss with a reason "
                           f"(Dentist)")
        else:
            ok = ("for_dentist", "resolved", "dismissed_by_dentist", "dismissed_by_assistant")
            if target == "dentist":
                ok = ("resolved", "dismissed_by_dentist", "dismissed_by_assistant")
            if st not in ok:
                out.append(f"high flag {f.rule_id}: resolve or dismiss with a reason")
    return out


def _marked(flags, *, conflict_id=None, task_id=None) -> bool:
    for f in flags:
        if (conflict_id and conflict_id in f.conflict_ids) or (task_id and task_id in f.task_ids):
            if flag_state(f) in ("for_dentist", "resolved"):
                return True
    return False


# ---------------------------------------------------------------- transitions

class ApprovalBlocked(RuntimeError):
    def __init__(self, reasons):
        super().__init__("; ".join(reasons[:5]))
        self.reasons = reasons


def _record(session, kind: str, role: str, for_dentist=()) -> ApprovalRecord:
    from pipeline.stage_runs import session_stage_log
    b = current_binding(session)
    runs = session_stage_log(session).for_run(session.meta().get("last_run") or "")
    return ApprovalRecord(kind=kind, approver_role=role, timestamp=now(),
                          execution_record_ids=[r["id"] for r in runs], for_dentist=list(for_dentist),
                          **{k: b[k] for k in BOUND_KEYS})


def approve_assistant(session, role: str = "Assistant") -> ApprovalState:
    revoke_if_changed(session, "re-check before assistant review")
    reasons = blockers(session, "assistant")
    if reasons:
        raise ApprovalBlocked(reasons)
    state = load_state(session)
    state.records.append(_record(session, "assistant_review_complete", role))
    state.state = "assistant_review_complete"
    save_state(session, state)
    return state


def approve_dentist(session) -> ApprovalState:
    revoke_if_changed(session, "re-check before dentist approval")
    state = load_state(session)
    if state.state not in ("assistant_review_complete",):
        raise ApprovalBlocked(["assistant review must be complete first"])
    reasons = blockers(session, "dentist")
    if reasons:
        raise ApprovalBlocked(reasons)
    state.records.append(_record(session, "dentist_approved", "Dentist"))
    state.state = "dentist_approved"
    save_state(session, state)
    return state


class ExportRefused(RuntimeError):
    pass


def export(session) -> str:
    """Re-check every bound hash against the approval; refuse on mismatch."""
    state = load_state(session)
    if state.state != "dentist_approved" or not state.records:
        raise ExportRefused("not dentist-approved")
    rec = state.records[-1]
    mism = binding_mismatches(rec, current_binding(session))
    if mism:
        revoke_if_changed(session, "export hash check")
        raise ExportRefused(f"changed since approval: {', '.join(mism)}")
    graph, flags, _, latest = _context(session)
    open_flags = [{"rule_id": f.rule_id, "severity": f.severity, "message": f.message, "state": flag_state(f)}
                  for f in flags]
    overrides = []
    for e in graph.active():
        d = satisfying_disposition(graph, e)
        if d is not None and any(v in ("fail", "not_assessed_due_to_failure") for v in
                                 (e.checks.span_valid, e.checks.normalization_valid, e.checks.semantic_support)):
            overrides.append({"entity_id": e.id, "overridden_by": f"{d.kind} ({d.by_role}): {d.reason}"})
    meta = {"banner": BANNER, "approval": rec.model_dump(), "verification_level": latest["note"]["verification_level"],
            "flags": open_flags, "overrides": overrides, "notices": latest.get("notices", [])}
    path = session.path("exports", f"note_v{rec.snapshot_version}.md")
    body = f"> {BANNER}\n\n{latest['markdown']}\n\n---\nExport metadata:\n```json\n{json.dumps(meta, indent=2)}\n```\n"
    atomic_write_bytes(path, body.encode("utf-8"))
    state.records.append(_record(session, "exported", "Dentist"))
    state.state = "exported"
    state.export_path = str(path)
    save_state(session, state)
    return str(path)


def force_approve_for_test(session, role: str = "Dentist") -> None:
    """Tests only: record an approval bound to the current state without checking the matrix."""
    state = load_state(session)
    state.records.append(_record(session, "dentist_approved", role))
    state.state = "dentist_approved"
    save_state(session, state)
