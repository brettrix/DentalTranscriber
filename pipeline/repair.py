"""Issues and the single bounded repair round (section 10)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from pipeline.storage import hash_obj


@dataclass
class Issue:
    kind: str                        # check_fail | unresolved_link | omission | unmatched_contradiction | semantic_mismatch | semantic_unconfirmed
    owner: str                       # agent that owns the fix (B0, B1-B4) or "registry"
    details: str
    entity_id: str | None = None
    entity_version: int | None = None
    attribute: str | None = None
    check: str | None = None
    evidence: list[dict] = field(default_factory=list)
    suggested_type: str | None = None
    section: str | None = None
    origin: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            key = [self.kind, self.entity_id or sorted(f"{e.get('source_id')}:{e.get('quote') or e.get('text')}"
                                                       for e in self.evidence), self.attribute or self.check]
            self.id = "is_" + hash_obj(key)[:12]

    def for_agent(self) -> dict:
        d = {"issue_id": self.id, "kind": self.kind, "details": self.details}
        if self.entity_id:
            d["entity_id"] = self.entity_id
        if self.attribute:
            d["attribute"] = self.attribute
        if self.evidence:
            d["evidence"] = self.evidence
        if self.suggested_type:
            d["suggested_type"] = self.suggested_type
        return d

    def to_dict(self) -> dict:
        return asdict(self)


def dedupe(issues: list[Issue]) -> list[Issue]:
    seen, out = set(), []
    for i in issues:
        if i.id not in seen:
            seen.add(i.id)
            out.append(i)
    return out


def spans_overlap(a_start, a_end, b_start, b_end) -> bool:
    if None in (a_start, a_end, b_start, b_end):
        return True
    return a_start < b_end and b_start < a_end


def covered_by(graph, source_type: str, source_id: str, start=None, end=None) -> list:
    """Active entities whose evidence overlaps the given span."""
    out = []
    for e in graph.active():
        for s in e.evidence:
            if s.source_type == source_type and s.source_id == source_id and spans_overlap(s.start, s.end, start, end):
                out.append(e)
                break
    return out


def cv_issues(graph, cv_results: dict, owner_of) -> list[Issue]:
    issues = []
    for e in graph.active():
        res = cv_results.get(e.ref)
        if not res:
            continue
        for check, (result, details) in res.items():
            if result == "fail":
                issues.append(Issue(kind="check_fail", owner=owner_of(e), entity_id=e.id, entity_version=e.version,
                                    check=check, details="; ".join(details)[:1500], origin="Cv"))
    return issues


def owner_for_entity(entity, mode: str) -> str:
    """Registry entities are never auto-repaired (section 8): their issues go to human review."""
    if entity.kind in ("problem", "relationship"):
        return "registry"
    return entity.owner or ("B0" if mode == "baseline" else "unknown")


def owner_for_type(item_type: str | None, mode: str) -> str:
    from schemas.entities import TEAM_OWNER_BY_TYPE
    if item_type in ("problem", "relationship"):
        return "registry"
    if mode == "baseline":
        return "B0"
    return TEAM_OWNER_BY_TYPE.get(item_type or "", "B4") if item_type else "unassigned"
