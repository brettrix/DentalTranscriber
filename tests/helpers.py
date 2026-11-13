"""Small builders for synthetic graphs used by rule and invariant tests."""
from __future__ import annotations

from pipeline.graph import rehash_all
from pipeline.overlays import sources_from_objects
from pipeline.relations import compute_target_relations
from pipeline.rules import RuleContext, run_rules
from schemas.entities import Item, Problem, Relationship, Span
from schemas.graph import Graph
from schemas.sources import QuickNote, QuickNotesSource, RolesOverlay, RoleEntry, Utterance, UtterancesSource

UTTS = UtterancesSource(provider="text", utterances=[Utterance(id=f"u{i}", speaker="S0", text=f"line {i}")
                                                       for i in range(1, 40)])
ROLES = RolesOverlay(confirmed=True, entries={"S0": RoleEntry(role="Dentist", set_by="test")})


def span(uid="u1"):
    return Span(source_type="transcript", source_id=uid, start=0, end=6, text="line " + uid[1:])


def passed(mode="baseline"):
    return {"span_valid": "pass", "normalization_valid": "pass",
            "semantic_support": "not_applicable" if mode == "baseline" else "pass"}


def problem(id="pb_1", target=14, complaint_tooth=None, complaint_text="upper left", role="chief", mode="baseline", **kw):
    return Problem(id=id, key=id, role=role, owner="B0", complaint_text="pain",
                   complaint_location={"free_text": complaint_text, "tooth": complaint_tooth},
                   clinical_target={"tooth": target}, evidence=[span()], checks=passed(mode),
                   assertion_source="clinician_assessment", **kw)


def rel(id="rl_1", tooth=3, kind="control", problem_id="pb_1", mode="team", semantic="pass"):
    c = passed(mode)
    if mode == "team":
        c["semantic_support"] = semantic
    return Relationship(id=id, problem_id=problem_id, tooth=tooth, relation_kind=kind, owner="Br",
                        evidence=[span("u2")], checks=c, assertion_source="clinician_observation")


_n = [100]


def item(itype, tooth=None, problem_id="pb_1", mode="baseline", checks=None, id=None, uid="u3", **attrs):
    from schemas.entities import ITEM_SCOPES
    scope = "problem" if (problem_id and "problem" in ITEM_SCOPES[itype]) else "encounter"
    _n[0] += 1
    assertion = attrs.pop("assertion", "present")
    return Item(id=id or f"it_{_n[0]}", type=itype, scope=scope, problem_id=problem_id if scope == "problem" else None,
                target={"tooth": tooth}, attributes=attrs, owner="B0", evidence=[span(uid)],
                checks=checks or passed(mode), assertion=assertion, assertion_source="clinician_assessment")


def graph(*entities, mode="baseline", conflicts=(), tasks=(), section_records=(), dispositions=()):
    g = Graph(pipeline_mode=mode, entities=list(entities), conflicts=list(conflicts), tasks=list(tasks),
              section_records=list(section_records), dispositions=list(dispositions), version=1)
    rehash_all(g, ROLES)
    compute_target_relations(g, mode)
    return g


def sources(quick_notes=()):
    qn = QuickNotesSource(notes=[QuickNote(id=f"q{i + 1}", text=t) for i, t in enumerate(quick_notes)])
    return sources_from_objects(UTTS, qn, roles=ROLES)


def flags_for(g, mode="baseline", rule_mode="synthetic_demo", quick_notes=(), stage_runs=(), pending_corrections=()):
    ctx = RuleContext(graph=g, mode=mode, rule_mode=rule_mode, sources=sources(quick_notes),
                      stage_runs=list(stage_runs), pending_corrections=list(pending_corrections))
    return run_rules(ctx)


def rule_ids(flags):
    return [f.rule_id for f in flags]
