"""Graph hashing (6.1), snapshot hashing, and versioned graph storage."""
from __future__ import annotations

from pydantic import TypeAdapter

from pipeline.storage import Session, atomic_write_json, hash_obj, read_json
from schemas.entities import Entity, Item, Problem, Relationship
from schemas.graph import Graph

ENTITY_ADAPTER = TypeAdapter(Entity)

_CONTENT_FIELDS = {
    "problem": ["kind", "role", "complaint_text", "complaint_location", "clinical_target", "assertion_source"],
    "relationship": ["kind", "problem_id", "tooth", "relation_kind", "note", "assertion_source"],
    "item": ["kind", "type", "scope", "problem_id", "target", "attributes", "assertion", "time_context",
             "assertion_source"],
}


def content_of(entity) -> dict:
    data = entity.model_dump(mode="json", by_alias=True)
    return {k: data[k] for k in _CONTENT_FIELDS[entity.kind]}


def content_hash(entity) -> str:
    return hash_obj(content_of(entity))


def support_of(entity, roles_overlay, problem=None) -> dict:
    data = entity.model_dump(mode="json", by_alias=True)
    speakers = sorted(set(entity.speaker_ids))
    roles = {s: (roles_overlay.entries[s].model_dump() if s in roles_overlay.entries else None) for s in speakers}
    corrections = sorted({(s.correction_id, s.correction_version) for s in entity.evidence if s.correction_id})
    out = {"evidence": data["evidence"], "derivations": data["derivations"], "roles": roles,
           "corrections": [list(c) for c in corrections]}
    if problem is not None:
        out["problem"] = {"id": problem.id, "content_hash": problem.content_hash, "support_hash": problem.support_hash}
    return out


def linked_problem(entity, graph: Graph | None):
    if graph is None:
        return None
    pid = getattr(entity, "problem_id", None)
    if entity.kind == "item" and entity.scope != "problem":
        return None
    if not pid:
        return None
    return graph.get(pid)


def support_hash(entity, roles_overlay, problem=None) -> str:
    return hash_obj(support_of(entity, roles_overlay, problem))


def fill_speakers(entity, sources) -> None:
    """speaker_ids and roles come from the cited utterances and the role overlay, never from an agent."""
    speakers: list[str] = []
    for span in entity.evidence:
        if span.source_type == "transcript":
            u = sources.utterance(span.source_id)
            if u and u.speaker not in speakers:
                speakers.append(u.speaker)
    entity.speaker_ids = speakers
    roles: list[str] = []
    for s in speakers:
        r = sources.role_of(s) or "Unknown"
        if r not in roles:
            roles.append(r)
    entity.roles = roles


def rehash(entity, roles_overlay, graph: Graph | None) -> None:
    entity.content_hash = content_hash(entity)
    entity.support_hash = support_hash(entity, roles_overlay, linked_problem(entity, graph))


def rehash_all(graph: Graph, roles_overlay) -> None:
    """Problems first, then relationships and items (their support hash includes the problem's hashes)."""
    for e in graph.entities:
        if e.kind == "problem":
            rehash(e, roles_overlay, graph)
    for e in graph.entities:
        if e.kind != "problem":
            rehash(e, roles_overlay, graph)


_SNAPSHOT_EXCLUDE = {"frozen", "parent_version"}


def snapshot_hash(graph: Graph) -> str:
    data = graph.model_dump(mode="json", by_alias=True, exclude=_SNAPSHOT_EXCLUDE)
    return hash_obj(data)


# ---------------------------------------------------------------- storage

def save_graph(session: Session, graph: Graph) -> Graph:
    """Commit a new graph version (the caller has already run structural validation)."""
    latest = session.meta().get("graph_version", 0)
    graph = graph.model_copy(deep=True)
    graph.parent_version = latest or None
    graph.version = latest + 1
    atomic_write_json(session.path("graphs", f"graph_v{graph.version}.json"), graph)
    session.update_meta(graph_version=graph.version, graph_hash=snapshot_hash(graph))
    return graph


def overwrite_graph(session: Session, graph: Graph) -> None:
    """Rewrite an existing version file in place: only for marking a whole version stale or frozen."""
    atomic_write_json(session.path("graphs", f"graph_v{graph.version}.json"), graph)


def load_graph(session: Session, version: int | None = None) -> Graph | None:
    v = version or session.meta().get("graph_version")
    if not v:
        return None
    data = read_json(session.path("graphs", f"graph_v{v}.json"))
    return Graph.model_validate(data) if data else None


def next_ids(graph: Graph) -> dict[str, int]:
    counters = {"pb": 0, "rl": 0, "it": 0}
    for e in graph.entities:
        prefix, _, num = e.id.partition("_")
        if prefix in counters and num.isdigit():
            counters[prefix] = max(counters[prefix], int(num))
    return counters


def new_id(counters: dict[str, int], kind: str) -> str:
    prefix = {"problem": "pb", "relationship": "rl", "item": "it"}[kind]
    counters[prefix] += 1
    return f"{prefix}_{counters[prefix]}" if prefix != "it" else f"it_{counters[prefix]:03d}"


__all__ = ["content_hash", "support_hash", "rehash", "rehash_all", "snapshot_hash", "save_graph", "load_graph",
           "fill_speakers", "ENTITY_ADAPTER", "Item", "Problem", "Relationship"]
