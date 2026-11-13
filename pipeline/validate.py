"""Structural validation (section 6.9). Runs on every graph version before it is committed."""
from __future__ import annotations

import re

from pydantic import ValidationError

from schemas.entities import ITEM_SCOPES
from schemas.graph import Graph

ALLOWED_DOSE_UNITS = {"mg", "g", "mcg", "mL", "units", "%"}


class StructuralError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _tooth_ok(t) -> bool:
    return t is None or (isinstance(t, int) and not isinstance(t, bool) and 1 <= t <= 32)


def validate_entity(e) -> list[str]:
    """Entity-level checks (also used to filter a staging batch, section 6.10 step 2)."""
    errs: list[str] = []
    where = f"{e.id}@{e.version}"
    teeth = []
    if e.kind == "problem":
        teeth = [e.complaint_location.tooth, e.clinical_target.tooth]
    elif e.kind == "relationship":
        teeth = [e.tooth]
        if e.tooth is None:
            errs.append(f"{where}: relationship needs a tooth")
    else:
        teeth = [e.target.tooth]
        if e.scope not in ITEM_SCOPES[e.type]:
            errs.append(f"{where}: scope {e.scope} not allowed for {e.type}")
        if e.scope == "problem" and not e.problem_id:
            errs.append(f"{where}: problem-scoped item has no problem link")
        if e.scope == "encounter" and e.problem_id:
            errs.append(f"{where}: encounter item must not link a problem")
        a = e.attributes
        for key in ("strength", "dose"):
            v = a.get(key)
            if v is not None:
                m = re.fullmatch(r"\d+(\.\d+)?\s+(\S+)", str(v))
                if not m or m.group(2) not in ALLOWED_DOSE_UNITS:
                    errs.append(f"{where}: {key} {v!r} is not '<number> <unit>' with an allowed unit")
        if e.type == "vital_reading" and a.get("unit") != "mmHg":
            errs.append(f"{where}: vital unit must be mmHg")
    for t in teeth:
        if not _tooth_ok(t):
            errs.append(f"{where}: tooth {t!r} outside 1-32")
    human_spans = [s for s in e.evidence if s.source_type == "human_entry"]
    if e.owner == "human":
        if not e.evidence or len(human_spans) != len(e.evidence):
            errs.append(f"{where}: human-entry entity needs human-entry evidence only")
    elif human_spans:
        errs.append(f"{where}: source-backed entity cites human-entry evidence")
    elif not e.evidence:
        errs.append(f"{where}: source-backed entity has no evidence")
    return errs


def operational_reference_errors(graph: Graph, e) -> list[str]:
    """References an active entity needs to resolve to active, applicable entities."""
    errs: list[str] = []
    where = f"{e.id}@{e.version}"
    active = {x.id: x for x in graph.entities if x.status == "active"}

    def need(ref_id, kind, item_type=None, label="reference"):
        if not ref_id:
            return
        target = active.get(ref_id)
        if target is None:
            superseded = any(x.id == ref_id for x in graph.entities)
            errs.append(f"{where}: {label} {ref_id} is {'superseded' if superseded else 'missing'}")
        elif target.kind != kind or (item_type and target.type != item_type):
            errs.append(f"{where}: {label} {ref_id} is not a {item_type or kind}")

    if e.kind == "relationship":
        need(e.problem_id, "problem", label="problem link")
    elif e.kind == "item":
        if e.scope == "problem":
            need(e.problem_id, "problem", label="problem link")
        if e.type == "decision":
            need(e.attributes.get("option_id"), "item", "option_discussed", "option")
        if e.type == "consent_element":
            need(e.attributes.get("option_id"), "item", "option_discussed", "option")
            need(e.attributes.get("decision_id"), "item", "decision", "decision")
    return errs


def validate_graph(graph: Graph, *, require_chief: bool = True) -> list[str]:
    errs: list[str] = []
    # Pydantic schema, round-tripped.
    try:
        Graph.model_validate(graph.model_dump(mode="json", by_alias=True))
    except ValidationError as exc:
        errs.append(f"schema: {exc.errors()[:3]}")
        return errs
    seen: set[str] = set()
    active_ids: dict[str, int] = {}
    for e in graph.entities:
        if e.ref in seen:
            errs.append(f"duplicate entity version {e.ref}")
        seen.add(e.ref)
        if e.status == "active":
            active_ids[e.id] = active_ids.get(e.id, 0) + 1
        errs += validate_entity(e)
    errs += [f"{i}: more than one active version" for i, n in active_ids.items() if n > 1]
    for e in graph.entities:
        if e.status == "active":
            errs += operational_reference_errors(graph, e)
    chiefs = [p for p in graph.active("problem") if p.role == "chief"]
    if require_chief and len(chiefs) != 1:
        errs.append(f"exactly one chief problem required, found {len(chiefs)}")
    errs += _historical_reference_errors(graph, seen)
    errs += _supersession_cycle_errors(graph)
    return errs


def _historical_reference_errors(graph: Graph, refs: set[str]) -> list[str]:
    errs: list[str] = []
    for c in graph.conflicts:
        for p in c.participants:
            if f"{p.entity_id}@{p.version}" not in refs:
                errs.append(f"conflict {c.id}: participant {p.entity_id}@{p.version} does not exist")
        if c.resolution and c.status == "resolved":
            r = c.resolution
            if r.action == "keep_both" and not (r.explanation or "").strip():
                errs.append(f"conflict {c.id}: keep_both needs an explanation")
    for t in graph.tasks:
        for p in t.participants:
            if f"{p.entity_id}@{p.version}" not in refs:
                errs.append(f"task {t.id}: participant {p.entity_id}@{p.version} does not exist")
    sections = {s.section for s in graph.section_records}
    tasks = {t.id for t in graph.tasks}
    conflicts = {c.id for c in graph.conflicts}
    entity_ids = {e.id for e in graph.entities}
    for d in graph.dispositions:
        ok = {"entity": d.subject_id in entity_ids, "section": d.subject_id in sections,
              "task": d.subject_id in tasks, "conflict_resolution": d.subject_id in conflicts,
              "stage_run": True}[d.subject_type]
        if not ok:
            errs.append(f"disposition {d.id}: subject {d.subject_type} {d.subject_id} does not exist")
    for pc in graph.pending_changes:
        for p in pc.target_versions:
            if f"{p.entity_id}@{p.version}" not in refs:
                errs.append(f"pending change {pc.id}: target {p.entity_id}@{p.version} does not exist")
    return errs


def _supersession_cycle_errors(graph: Graph) -> list[str]:
    edges = {e.ref: e.superseded_by for e in graph.entities if e.superseded_by and "@" in (e.superseded_by or "")}
    errs = []
    for start in edges:
        cur, seen = start, set()
        while cur in edges:
            if cur in seen:
                errs.append(f"supersession cycle through {start}")
                break
            seen.add(cur)
            cur = edges[cur]
    return errs


def assert_valid(graph: Graph, **kw) -> None:
    errs = validate_graph(graph, **kw)
    if errs:
        raise StructuralError(errs)
