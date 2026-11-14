"""L Linker (Python): ids and versions (6.5), references, hashes, structural validation, batch commits (6.10)."""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field

from pydantic import ValidationError

from agents.io import ItemOut, ProblemOut, RelationshipOut
from pipeline.graph import fill_speakers, new_id, next_ids, rehash
from pipeline.storage import atomic_write_json, now, read_json
from pipeline.validate import operational_reference_errors, validate_entity, validate_graph
from pipeline.verify import locate_span
from schemas.entities import Derivation, Item, Problem, Relationship, Span
from schemas.graph import Graph


@dataclass
class StagedRecord:
    id: str
    owner: str
    kind: str
    raw: dict
    entity: dict | None = None
    errors: list[str] = field(default_factory=list)
    status: str = "staged"           # staged | committed | discarded | converted
    task_id: str | None = None
    run_id: str | None = None
    created: str = field(default_factory=now)
    discard_reason: str | None = None


class Staging:
    """staging.json: everything an extractor returned, before and after commit."""

    def __init__(self, path=None):
        self.path = path
        self.records: list[StagedRecord] = []
        self.tasks: list[dict] = []   # pre-graph tasks (e.g. a stage failure while no graph can commit)
        if path is not None:
            data = read_json(path, {"records": [], "tasks": []})
            self.records = [StagedRecord(**r) for r in data.get("records", [])]
            self.tasks = data.get("tasks", [])

    def save(self):
        if self.path is not None:
            atomic_write_json(self.path, {"records": [asdict(r) for r in self.records], "tasks": self.tasks})

    def add(self, rec: StagedRecord):
        self.records.append(rec)

    def open_records(self) -> list[StagedRecord]:
        return [r for r in self.records if r.status == "staged" and not self.legacy_applied_revision(r)]

    @staticmethod
    def legacy_applied_revision(r: StagedRecord) -> bool:
        """Sessions created before the staging fix left applied repair revisions marked "staged" (a revision has
        the existing entity's id, a converted entity, and no errors). They were committed or identical, so they
        are not open; current code marks them committed/unchanged when it applies them."""
        return r.status == "staged" and bool(r.raw.get("id")) and r.entity is not None and not r.errors

    def get(self, sid: str) -> StagedRecord | None:
        return next((r for r in self.records if r.id == sid), None)


def session_staging(session) -> Staging:
    return Staging(session.path("staging.json"))


# ---------------------------------------------------------------- conversion

def _spans(quotes, sources) -> list[Span]:
    out = []
    for q in quotes:
        version = {"transcript": sources.utterances.version, "quick_note": sources.quick_notes.version}.get(
            q.source_type, sources.visit_meta.version)
        span = Span(source_type=q.source_type, source_id=q.source_id, source_version=version, text=q.quote)
        locate_span(span, sources)
        out.append(span)
    return out


def _derivations(ds) -> list[Derivation]:
    return [Derivation.model_validate(d.model_dump(by_alias=True)) for d in ds]


class KeyMap:
    """Local keys (namespaced 'Br:P1') and existing ids -> graph ids."""

    def __init__(self, graph: Graph):
        self.graph = graph
        self.map: dict[str, str] = {}

    def resolve(self, ref: str | None, owner: str, registry_owner: str) -> str | None:
        if not ref:
            return None
        if self.graph.get(ref) is not None:
            return ref
        for candidate in (ref, f"{owner}:{ref}", f"{registry_owner}:{ref}"):
            if candidate in self.map:
                return self.map[candidate]
        # Keys from an earlier batch (e.g. a repair call naming its own problem key 'P1').
        for candidate in (f"{owner}:{ref}", f"{registry_owner}:{ref}", ref):
            hit = next((e.id for e in self.graph.entities if e.status == "active" and e.local_key == candidate), None)
            if hit:
                return hit
        return None


def _match_previous(entity, previous: Graph | None, taken: set[str]):
    """Section 6.5: same kind/type, problem, target and overlapping evidence keep their id."""
    if previous is None:
        return None
    ev = {(s.source_type, s.source_id) for s in entity.evidence}
    best, best_overlap = None, 0
    for p in previous.entities:
        if p.kind != entity.kind or p.id in taken or p.owner == "human":
            continue
        if entity.kind == "item":
            if p.type != entity.type or p.problem_id != entity.problem_id or p.target.tooth != entity.target.tooth:
                continue
        elif entity.kind == "relationship":
            if p.problem_id != entity.problem_id or p.tooth != entity.tooth:
                continue
        else:
            if p.role != entity.role:
                continue
        overlap = len(ev & {(s.source_type, s.source_id) for s in p.evidence})
        if overlap > best_overlap:
            best, best_overlap = p, overlap
    return best


def _assign_version(entity, previous: Graph | None) -> None:
    if previous is None:
        return
    versions = [p for p in previous.entities if p.id == entity.id]
    if not versions:
        return
    latest = max(versions, key=lambda p: p.version)
    if latest.content_hash == entity.content_hash and latest.support_hash == entity.support_hash:
        entity.version = latest.version
    else:
        entity.version = latest.version + 1


def convert_outputs(outputs: list[tuple[str, object]], sources, graph: Graph, previous: Graph | None,
                    registry_owner: str, run_id: str | None = None,
                    human_chief_id: str | None = None) -> tuple[list, list[StagedRecord]]:
    """Agent outputs -> candidate entities (problems first). Returns (entities, staged records)."""
    keymap = KeyMap(graph)
    counters = next_ids(graph)
    if previous is not None:
        for k, v in next_ids(previous).items():
            counters[k] = max(counters[k], v)
    taken = {e.id for e in graph.entities}
    entities, staged = [], []

    def stage(owner, kind, out, entity=None, errors=None):
        rec = StagedRecord(id=f"st_{uuid.uuid4().hex[:10]}", owner=owner, kind=kind,
                           raw=out.model_dump(mode="json", by_alias=True),
                           entity=entity.model_dump(mode="json", by_alias=True) if entity is not None else None,
                           errors=errors or [], run_id=run_id)
        staged.append(rec)
        return rec

    ordered = ([(o, x, "problem") for o, out in outputs for x in getattr(out, "problems", [])] +
               [(o, x, "relationship") for o, out in outputs for x in getattr(out, "relationships", [])] +
               [(o, x, "item") for o, out in outputs for x in getattr(out, "items", [])])
    # Options before decisions/consent so their keys resolve in one pass; order otherwise doesn't matter.
    ordered.sort(key=lambda t: {"problem": 0, "relationship": 1, "item": 2}[t[2]] * 10 +
                 (0 if t[2] == "item" and t[1].type == "option_discussed" else
                  2 if t[2] == "item" and t[1].type in ("decision",) else
                  3 if t[2] == "item" and t[1].type == "consent_element" else 1))
    for owner, out, kind in ordered:
        if kind == "problem" and out.role == "chief" and human_chief_id:
            # A human-entered chief problem stands; the extractor's chief key resolves to it.
            keymap.map[f"{owner}:{out.key}"] = human_chief_id
            rec = stage(owner, kind, out, errors=["chief problem already entered by a human"])
            rec.status = "superseded_by_human"
            continue
        try:
            entity = _build(kind, owner, out, sources, keymap, registry_owner)
        except (ValidationError, ValueError) as exc:
            msg = exc.errors()[:4] if isinstance(exc, ValidationError) else str(exc)
            stage(owner, kind, out, errors=[f"conversion: {msg}"])
            continue
        if kind == "item" and label_only_quick_note(entity, sources):
            # "Tx: #3" only says which tooth; it is not a record that something was done or planned. The tooth
            # still reaches the tooth checks, which read the quick notes themselves. Kept in staging, not open.
            rec = stage(owner, kind, out, errors=["quick-note label only identifies a tooth; no item is created"])
            rec.status = "label_only"
            continue
        fill_speakers(entity, sources)
        if out.id and any(e.id == out.id for e in graph.entities):
            entity.id = out.id
        else:
            rehash(entity, sources.roles, graph)
            prev = _match_previous(entity, previous, taken)
            entity.id = prev.id if prev is not None else new_id(counters, kind)
        taken.add(entity.id)
        keymap.map[f"{owner}:{out.key}"] = entity.id
        entities.append(entity)
        stage(owner, kind, out, entity)
        # Make the entity visible to later reference checks in this conversion.
        graph_view_add(graph, entity)
    for e in entities:
        graph_view_remove(graph, e)
    return entities, staged


def graph_view_add(graph: Graph, entity) -> None:
    graph.entities.append(entity)


def graph_view_remove(graph: Graph, entity) -> None:
    graph.entities = [x for x in graph.entities if x is not entity]


# Words that say nothing about a reaction: hedges, fillers and "none stated" placeholders.
_NOT_A_REACTION = re.compile(
    r"^(?:(?:i|we)\s+(?:think|guess|believe|suppose)(?:\s+so)?|maybe|probably|possibly|perhaps|(?:i'?m\s+)?not\s+sure"
    r"|unsure|(?:i\s+)?(?:don'?t|do\s+not|can'?t|cannot)\s+(?:know|remember|recall)|unknown|unspecified"
    r"|not\s+(?:stated|specified|given|mentioned|reported|known)|none(?:\s+(?:stated|reported|given))?|n/?a"
    r"|no\s+(?:reaction|problems?)(?:\s+(?:stated|reported|since))?|\?+)[\s.,!?]*$", re.I)


_TOOTH_ONLY = r"\s*(?:#\s?\d{1,2}|tooth\s+#?\s?\d{1,2})\s*\.?\s*$"


def label_only_quick_note(entity, sources) -> bool:
    """True for a treatment-type item whose only evidence is quick-note lines of the form "<label>: <tooth>"
    (Tx:, Tooth:, Dx:). Such a line names the tooth and nothing else."""
    import glossary
    from schemas.entities import TREATMENT_BEARING
    if entity.type not in TREATMENT_BEARING or not entity.evidence:
        return False
    labels = [re.escape(k) for k, v in glossary.QUICK_NOTE_LABELS.items() if v == "clinical_target"]
    pattern = re.compile(rf"^\s*(?:{'|'.join(labels)}){_TOOTH_ONLY}", re.I)
    notes = {q.id: q.text for q in sources.quick_notes.notes}
    return all(s.source_type == "quick_note" and pattern.match(notes.get(s.source_id, "")) for s in entity.evidence)


def clean_attributes(item_type: str, attributes: dict) -> dict:
    """Deterministic tidy-up of extractor output: an allergy `reaction` stays empty unless a reaction was stated."""
    if item_type == "allergy":
        reaction = attributes.get("reaction")
        if isinstance(reaction, str) and (not reaction.strip() or _NOT_A_REACTION.match(reaction.strip())):
            attributes["reaction"] = None
    return attributes


def _build(kind: str, owner: str, out, sources, keymap: KeyMap, registry_owner: str):
    common = dict(id=out.id or "tmp", owner=owner, local_key=f"{owner}:{out.key}",
                  evidence=_spans(out.evidence, sources), derivations=_derivations(out.derivations),
                  assertion_source=out.assertion_source)
    if kind == "problem":
        assert isinstance(out, ProblemOut)
        return Problem(key=f"{owner}:{out.key}", role=out.role, complaint_text=out.complaint_text,
                       complaint_location=out.complaint_location.model_dump(),
                       clinical_target=out.clinical_target.model_dump(), **common)
    if kind == "relationship":
        assert isinstance(out, RelationshipOut)
        pid = keymap.resolve(out.problem_key, owner, registry_owner)
        if pid is None:
            raise ValueError(f"relationship problem_key {out.problem_key!r} does not resolve")
        return Relationship(problem_id=pid, tooth=out.tooth, relation_kind=out.relation_kind, note=out.note, **common)
    assert isinstance(out, ItemOut)
    attributes = clean_attributes(out.type, dict(out.attributes))
    pid = keymap.resolve(out.problem_key, owner, registry_owner)
    if out.problem_key and pid is None:
        raise ValueError(f"problem_key {out.problem_key!r} does not resolve")
    from schemas.entities import ITEM_SCOPES
    scopes = ITEM_SCOPES[out.type]
    scope = "problem" if (pid and "problem" in scopes) else ("encounter" if "encounter" in scopes else "problem")
    if scope == "encounter":
        pid = None
    if out.type == "decision":
        oid = keymap.resolve(out.option_key, owner, registry_owner)
        if out.option_key and oid is None:
            raise ValueError(f"option_key {out.option_key!r} does not resolve")
        attributes["option_id"] = oid
        attributes["option_link"] = "linked" if oid else "unknown"
    if out.type == "consent_element":
        oid = keymap.resolve(out.option_key, owner, registry_owner)
        did = keymap.resolve(out.decision_key, owner, registry_owner)
        if (out.option_key and oid is None) or (out.decision_key and did is None):
            raise ValueError("consent element link does not resolve")
        attributes["option_id"], attributes["decision_id"] = oid, did
        attributes["link"] = "linked" if (oid or did) else "unknown"
    return Item(type=out.type, scope=scope, problem_id=pid, target=out.target.model_dump(), attributes=attributes,
                assertion=out.assertion, time_context=out.time_context, **common)


# ---------------------------------------------------------------- batch commit (6.10)

def commit_batch(graph: Graph, entities: list, staged: list[StagedRecord], sources, previous: Graph | None = None,
                 *, require_chief: bool = True, overrides: dict | None = None) -> tuple[list, list[StagedRecord]]:
    """Commit the closed, valid subset in one transaction. Returns (committed entities, uncommitted records).
    Mutates `graph` only on success."""
    by_ref = {id(e): rec for e, rec in zip(entities, [r for r in staged if r.entity is not None])}
    candidates = list(entities)
    removed_reasons: dict[int, list[str]] = {}
    # Step 2a: entity-level checks.
    for e in list(candidates):
        errs = validate_entity(e)
        if errs:
            removed_reasons[id(e)] = errs
            candidates.remove(e)
    # Step 2b: close under operational references, repeatedly.
    changed = True
    while changed:
        changed = False
        trial = graph.model_copy(deep=False)
        trial.entities = list(graph.entities) + candidates
        for e in list(candidates):
            errs = operational_reference_errors(trial, e)
            if errs:
                removed_reasons[id(e)] = errs
                candidates.remove(e)
                changed = True
    # Hashes need the committed problems (support_hash includes the linked problem's hashes).
    trial = graph.model_copy(deep=False)
    trial.entities = list(graph.entities) + candidates
    for e in candidates:
        if e.kind == "problem":
            rehash(e, sources.roles, trial)
    for e in candidates:
        if e.kind != "problem":
            rehash(e, sources.roles, trial)
        _assign_version(e, previous)
    # 6.11: a regenerated entity a human removed or edited is committed as superseded by that assertion.
    for e in candidates:
        a = (overrides or {}).get(e.id)
        if a is not None:
            e.status = "superseded"
            e.superseded_by = f"human:{a['id']}"
            e.supersede_reason = f"{a['operation']} by {a['by_role']}: {a['reason']}"
    # Step 3: whole-graph constraints.
    errs = validate_graph(trial, require_chief=require_chief)
    uncommitted = [r for r in staged if r.entity is None and r.status == "staged"]
    if errs:
        for e in entities:
            rec = by_ref.get(id(e))
            if rec is not None:
                rec.errors = removed_reasons.get(id(e), []) + [f"batch not committed: {'; '.join(errs[:3])}"]
                uncommitted.append(rec)
        return [], uncommitted
    # Step 4: commit.
    graph.entities.extend(candidates)
    for e in entities:
        rec = by_ref.get(id(e))
        if rec is None:
            continue
        if e in candidates:
            rec.status = "committed"
            rec.entity = e.model_dump(mode="json", by_alias=True)
        else:
            rec.errors = removed_reasons.get(id(e), ["removed"])
            uncommitted.append(rec)
    return candidates, uncommitted


def apply_revisions(graph: Graph, revised: list, sources) -> list:
    """Repair outputs that carry an existing id: the new version supersedes the current one.
    Returns the entities that actually changed."""
    changed = []
    for new in revised:
        old = graph.get(new.id)
        if old is None or old.status != "active":
            continue
        trial = graph.model_copy(deep=False)
        trial.entities = [x for x in graph.entities if x is not old] + [new]
        new.owner = old.owner
        new.version = old.version
        rehash(new, sources.roles, trial)
        if new.content_hash == old.content_hash and new.support_hash == old.support_hash:
            continue
        new.version = max(x.version for x in graph.entities if x.id == old.id) + 1
        old.status = "superseded"
        old.superseded_by = new.ref
        old.supersede_reason = "repaired"
        graph.entities.append(new)
        changed.append(new)
    return changed
