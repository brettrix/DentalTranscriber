"""Dispositions (6.7) and acceptance/eligibility (9.0)."""
from __future__ import annotations

import uuid

from pipeline.storage import now
from schemas.dispositions import Disposition
from schemas.entities import is_critical


def entity_hashes(entity) -> dict:
    return {"content_hash": entity.content_hash, "support_hash": entity.support_hash}


def bound_dispositions(graph, entity, kinds=None) -> list[Disposition]:
    """Dispositions on this entity whose bound hashes match its current hashes."""
    out = []
    for d in graph.dispositions:
        if d.subject_type == "entity" and d.subject_id == entity.id and d.subject_hashes == entity_hashes(entity):
            if kinds is None or d.kind in kinds:
                out.append(d)
    return out


def checks_pass(entity, mode: str) -> bool:
    c = entity.checks
    ok = {"pass", "not_applicable"}
    if c.span_valid not in ok or c.normalization_valid not in ok:
        return False
    if entity.is_human:
        return True
    return c.semantic_support == ("not_applicable" if mode == "baseline" else "pass")


def satisfying_disposition(graph, entity) -> Disposition | None:
    """Approval matrix 11.3: critical types need dentist_confirmed; others human_reviewed or dentist_confirmed."""
    kinds = {"dentist_confirmed"} if is_critical(entity) else {"dentist_confirmed", "human_reviewed"}
    ds = bound_dispositions(graph, entity, kinds)
    return ds[-1] if ds else None


def accepted(graph, entity, mode: str) -> bool:
    if entity.status != "active":
        return False
    if entity.is_human:
        return bool(bound_dispositions(graph, entity, {"human_entered", "dentist_confirmed"}))
    return checks_pass(entity, mode) or satisfying_disposition(graph, entity) is not None


def relationship_eligible(graph, rel, mode: str) -> bool:
    """6.2: accepted, and (a relationship can suppress target flags) accepted through a passing semantic check
    or a dentist_confirmed disposition. In baseline mode only dentist-confirmed relationships are eligible."""
    if rel.status != "active":
        return False
    confirmed = bool(bound_dispositions(graph, rel, {"dentist_confirmed"}))
    if mode == "baseline":
        return confirmed
    return confirmed or (checks_pass(rel, mode) and rel.checks.semantic_support == "pass")


def make_disposition(subject_type: str, subject_id: str, subject_hashes: dict, kind: str, by_role: str,
                     reason: str = "", **extra) -> Disposition:
    return Disposition(id=f"ds_{uuid.uuid4().hex[:10]}", subject_type=subject_type, subject_id=subject_id,
                       subject_hashes=subject_hashes, kind=kind, by_role=by_role, reason=reason, timestamp=now(),
                       **extra)


def add_entity_disposition(graph, entity, kind: str, by_role: str, reason: str = "") -> Disposition:
    d = make_disposition("entity", entity.id, entity_hashes(entity), kind, by_role, reason)
    graph.dispositions.append(d)
    entity.dispositions.append(d.id)
    return d


def section_reviewed(graph, section: str) -> Disposition | None:
    rec = next((s for s in graph.section_records if s.section == section), None)
    for d in reversed(graph.dispositions):
        if d.subject_type == "section" and d.subject_id == section and d.kind == "section_reviewed":
            if rec is None or d.subject_hashes.get("record_version") == rec.version:
                return d
    return None
