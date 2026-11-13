"""Revision-bound approval (11.2). Full gates are in approval_matrix(); this module also revokes on change."""
from __future__ import annotations

from pipeline.storage import atomic_write_json, now, read_json
from schemas.approval import ApprovalState


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
    from pipeline.storage import read_json as rj
    graph = load_graph(session)
    sources = load_sources(session)
    latest = rj(session.path("outputs", "latest.json"), {}) or {}
    return {"snapshot_version": graph.version if graph else None,
            "snapshot_hash": snapshot_hash(graph) if graph else None,
            "note_hash": (latest.get("note") or {}).get("note_hash"),
            "render_config_hash": render_config_hash(),
            "overlay_versions": sources.overlay_versions,
            "source_hashes": sources.hashes,
            "rule_file_hashes": rule_file_hashes(),
            "rule_mode": session.meta().get("rule_mode")}


def binding_mismatches(record, binding: dict) -> list[str]:
    out = []
    for key in ("snapshot_version", "snapshot_hash", "note_hash", "render_config_hash", "overlay_versions",
                "source_hashes", "rule_file_hashes", "rule_mode"):
        if getattr(record, key) != binding.get(key):
            out.append(key)
    return out


def revoke_if_changed(session, reason: str = "") -> bool:
    """Any change to sources, overlays, snapshot, rule files or render configuration returns the session to draft."""
    state = load_state(session)
    if state.state == "draft" or not state.records:
        return False
    last = state.records[-1]
    mism = binding_mismatches(last, current_binding(session))
    if not mism:
        return False
    state.revoked.append({"from_state": state.state, "reason": reason, "changed": mism, "timestamp": now()})
    state.state = "draft"
    save_state(session, state)
    return True
