"""T: effective target relations (Stage D, section 6.2)."""
from __future__ import annotations

from pipeline.dispositions import relationship_eligible


def eligible_relationships(graph, mode: str) -> list:
    return [r for r in graph.active("relationship") if relationship_eligible(graph, r, mode)]


def compute_target_relations(graph, mode: str) -> None:
    eligible = eligible_relationships(graph, mode)
    for item in graph.active("item"):
        if item.scope != "problem" or item.target.tooth is None:
            item.target_relation = None
            continue
        problem = graph.get(item.problem_id)
        if problem is not None and problem.clinical_target.tooth == item.target.tooth:
            item.target_relation = "matches_target"
            continue
        rel = next((r for r in eligible if r.problem_id == item.problem_id and r.tooth == item.target.tooth), None)
        item.target_relation = rel.relation_kind if rel else "unknown"
