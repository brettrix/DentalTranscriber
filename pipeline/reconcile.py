"""Stage D reconciliation (Python; derived records only): R1, R2 linking, carried resolutions, link tasks."""
from __future__ import annotations

from pipeline.repair import covered_by
from pipeline.storage import hash_obj
from pipeline.tasks import add_task, make_task
from pipeline.verify import locate_span
from schemas.conflicts import Conflict, Participant
from schemas.entities import Span


def _sid(s: Span) -> str:
    return f"{s.source_type}:{s.source_id}:{s.start}-{s.end}"


def conflict_id(kind: str, evidence: list[Span]) -> str:
    return "cf_" + hash_obj([kind, sorted(_sid(s) for s in evidence)])[:12]


def _only(entity, source_type: str) -> bool:
    return bool(entity.evidence) and all(s.source_type == source_type for s in entity.evidence)


def _participants(entities) -> list[Participant]:
    seen, out = set(), []
    for e in entities:
        if e.id not in seen:
            seen.add(e.id)
            out.append(Participant(entity_id=e.id, version=e.version))
    return out


def r1_conflicts(graph) -> list[Conflict]:
    """Quick-note vs transcript disagreements on the same subject."""
    out: list[Conflict] = []
    items = graph.active("item")
    qn = [i for i in items if _only(i, "quick_note")]
    tr = [i for i in items if any(s.source_type == "transcript" for s in i.evidence)]
    for q in qn:
        if q.type == "vital_reading":
            readings = [t for t in tr if t.type == "vital_reading"]
            qv = (q.attributes.get("systolic"), q.attributes.get("diastolic"))
            if readings and all((t.attributes.get("systolic"), t.attributes.get("diastolic")) != qv for t in readings):
                out.append(_conflict("quick_note_vs_transcript", [q] + readings, "blood pressure"))
        elif q.type == "allergy":
            qs, qstat = q.attributes.get("substance"), q.attributes.get("allergy_status")
            for t in (t for t in tr if t.type == "allergy"):
                ts, tstat = t.attributes.get("substance"), t.attributes.get("allergy_status")
                blanket_denial = (qstat == "denied" and qs is None and tstat != "denied") or \
                                 (tstat == "denied" and ts is None and qstat != "denied")
                if blanket_denial or (qs and qs == ts and qstat != tstat):
                    out.append(_conflict("quick_note_vs_transcript", [q, t], f"allergy {qs or ts or ''}".strip()))
        elif q.type == "medication":
            for t in (t for t in tr if t.type == "medication"):
                if q.attributes.get("drug") and q.attributes.get("drug") == t.attributes.get("drug") and \
                        q.attributes.get("medication_status") != t.attributes.get("medication_status"):
                    out.append(_conflict("quick_note_vs_transcript", [q, t], f"medication {q.attributes['drug']}"))
    return out


def _conflict(kind, entities, subject, later: Span | None = None, evidence: list[Span] | None = None) -> Conflict:
    ev = evidence if evidence is not None else [s for e in entities for s in e.evidence]
    return Conflict(id=conflict_id(kind, ev), kind=kind, participants=_participants(entities), evidence=ev,
                    later_statement=later, subject=subject, origin="R1" if kind == "quick_note_vs_transcript" else "R2")


def r2_spans(finding, sources) -> tuple[Span, Span]:
    spans = []
    for q in (finding["first"], finding["second"]):
        version = sources.utterances.version if q["source_type"] == "transcript" else sources.quick_notes.version
        s = Span(source_type=q["source_type"], source_id=q["source_id"], source_version=version, text=q["quote"])
        locate_span(s, sources)
        spans.append(s)
    return spans[0], spans[1]


def r2_uncovered(graph, findings, sources) -> list[tuple[dict, list[Span]]]:
    """R2 results with a statement no entity covers (they become omission issues before repair)."""
    out = []
    for f in findings:
        a, b = r2_spans(f, sources)
        missing = [s for s in (a, b) if not covered_by(graph, s.source_type, s.source_id, s.start, s.end)]
        if missing:
            out.append((f, missing))
    return out


def link_r2(graph, findings, sources, previous=None) -> list[Conflict]:
    conflicts = []
    for f in findings:
        a, b = r2_spans(f, sources)
        ents = covered_by(graph, a.source_type, a.source_id, a.start, a.end) + \
            covered_by(graph, b.source_type, b.source_id, b.start, b.end)
        later = {"first": a, "second": b}.get(f.get("later"))
        if ents:
            conflicts.append(_conflict(f["kind"], ents, f.get("subject"), later=later, evidence=[a, b]))
        else:
            add_task(graph, make_task("unmatched_contradiction",
                                      f"{f['kind'].replace('_', ' ')} about {f.get('subject')}: no entity covers it",
                                      evidence=[a, b], created_by_stage="D", severity="high"), previous)
    return conflicts


def add_conflicts(graph, conflicts: list[Conflict], previous=None) -> None:
    """Add conflicts once each; a previous resolution carries over while participants and evidence are unchanged."""
    existing = {c.id for c in graph.conflicts}
    covered_sets = {frozenset(p.entity_id for p in c.participants) for c in graph.conflicts}
    for c in conflicts:
        pset = frozenset(p.entity_id for p in c.participants)
        if c.id in existing or (c.origin == "R2" and pset in covered_sets and len(pset) > 1):
            continue
        prior = previous.conflict(c.id) if previous is not None else None
        if prior is not None and prior.status == "resolved" and prior.resolution is not None:
            same_parts = sorted((p.entity_id, p.version) for p in prior.participants) == \
                sorted((p.entity_id, p.version) for p in c.participants)
            same_ev = sorted(_sid(s) for s in prior.evidence) == sorted(_sid(s) for s in c.evidence)
            if same_parts and same_ev:
                c.status, c.resolution = "resolved", prior.resolution
        graph.conflicts.append(c)
        existing.add(c.id)
        covered_sets.add(pset)


def link_tasks(graph, previous=None) -> None:
    """Unknown option links become low-severity human-review tasks; never an invented option."""
    for d in graph.active_items("decision"):
        if d.attributes.get("option_link") == "unknown":
            add_task(graph, make_task("unknown_option_link", "Decision has no linked option",
                                      participants=[d], evidence=d.evidence[:1], created_by_stage="D",
                                      severity="low"), previous)
