"""Scoring a candidate graph against gold (sections 14.2-14.4): problem-first matching, entities, flags, claims."""
from __future__ import annotations

from dataclasses import dataclass, field

from pipeline import normalize
from schemas.gold import GoldCase

NEGATED = {"absent", "denied"}
# Item types whose tooth is part of the clinical fact (findings, perio, radiographs, diagnoses, treatment items).
TOOTH_BEARING = ["finding", "perio_measurement", "radiograph", "diagnosis", "option_discussed", "treatment_today",
                 "next_visit"]
TEXT_KEYS = {"complaint_text", "complaint_location", "value", "description", "observation", "result_description",
             "finding", "diagnosis", "option", "procedure", "timing", "text", "content", "reason", "test", "reaction",
             "to", "purpose", "intensity", "risks", "benefits"}
CRITICAL = {"tooth": "tooth", "relation_kind": "relationship", "drug": "drug", "strength": "dose", "dose": "dose",
            "certainty": "certainty", "decision": "decision", "allergy_status": "allergy_status",
            "medication_status": "medication_status"}


def gold_ids(g) -> set[str]:
    return {e.utterance_id or e.quick_note_id for e in g.evidence if (e.utterance_id or e.quick_note_id)}


def prod_ids(e) -> set[str]:
    return {s.source_id for s in e.evidence if s.source_type in ("transcript", "quick_note")}


def _tooth(e):
    if e.kind == "problem":
        return e.clinical_target.tooth
    if e.kind == "relationship":
        return e.tooth
    return e.target.tooth


@dataclass
class Match:
    gold: dict
    produced: object | None
    dims: dict = field(default_factory=dict)      # dimension -> True/False/None(pending grader)
    pending: list = field(default_factory=list)   # (dim, gold text, produced text)


@dataclass
class CaseScore:
    case_id: str
    problem_map: dict
    merged: list
    split: list
    target_accuracy: tuple
    matches: list
    unmatched_produced: list
    flags: dict
    forbidden_hits: list
    expectations: list = field(default_factory=list)


def map_problems(gold: GoldCase, graph):
    gps = [g for g in gold.entities if g.kind == "problem"]
    pps = graph.active("problem")
    overlap = {(g.problem_key, p.id): len(gold_ids(g) & prod_ids(p)) for g in gps for p in pps}
    mapping, merged, split = {}, [], []
    for g in gps:
        best = max(pps, key=lambda p: (overlap[(g.problem_key, p.id)], p.role == g.key_attributes.get("role")),
                   default=None)
        if best is not None and (overlap[(g.problem_key, best.id)] > 0 or (len(gps) == 1 and len(pps) >= 1)):
            mapping[g.problem_key] = best.id
        hits = [p.id for p in pps if overlap[(g.problem_key, p.id)] > 0]
        if len(hits) > 1 and len(pps) > len(gps):
            split.append(g.problem_key)
    rev: dict[str, list] = {}
    for k, v in mapping.items():
        rev.setdefault(v, []).append(k)
    merged = [v for v, ks in rev.items() if len(ks) > 1]
    correct = sum(1 for g in gps if g.problem_key in mapping and
                  graph.get(mapping[g.problem_key]).clinical_target.tooth == g.target)
    return mapping, merged, split, (correct, len(gps))


def _produced_value(e, key, graph):
    if e.kind == "problem":
        if key == "complaint_location":
            loc = e.complaint_location
            return loc.free_text or (f"#{loc.tooth}" if loc.tooth else None)
        return getattr(e, key, None)
    if e.kind == "relationship":
        return getattr(e, key, None)
    if key == "surface":
        return e.target.surface
    if key == "option" and e.type == "decision":
        opt = graph.get(e.attributes.get("option_id")) if e.attributes.get("option_id") else None
        return opt.attributes.get("option") if opt else None
    return e.attributes.get(key)


def _same(key, g, p):
    if g is None:
        return p in (None, "", [])
    if p is None:
        return False
    if isinstance(g, bool) or isinstance(p, bool):
        return g == p
    if isinstance(g, (int, float)) and not isinstance(p, str):
        return float(g) == float(p)
    rule = {"strength": "dose", "dose": "dose", "frequency_code": "frequency", "drug": "drug_name",
            "substance": "drug_name", "surface": "surface_code"}.get(key)
    if rule:
        try:
            return normalize.values_equal(normalize.normalize_value(rule, g), normalize.normalize_value(rule, p))
        except normalize.NormalizationError:
            return str(g).lower() == str(p).lower()
    return normalize.values_equal(g, p)


def _pair_score(g, e, graph):
    score = len(gold_ids(g) & prod_ids(e)) * 2
    if g.target is not None and _tooth(e) == g.target:
        score += 2
    for k, v in g.key_attributes.items():
        if k not in TEXT_KEYS and _same(k, v, _produced_value(e, k, graph)):
            score += 1
    return score


def match_entities(gold: GoldCase, graph, mapping: dict, require_overlap=True):
    produced = [e for e in graph.active() if e.owner != "human"]
    used: set[str] = set()
    cands = []
    for g in gold.entities:
        for e in produced:
            if e.kind != g.kind or (g.kind == "item" and e.type != g.type):
                continue
            if g.kind == "item" and g.scope == "problem" and e.problem_id != mapping.get(g.problem_key) and \
                    mapping.get(g.problem_key) is not None and e.scope == "problem":
                continue
            if g.kind == "problem" and mapping.get(g.problem_key) != e.id:
                continue
            if require_overlap and not (gold_ids(g) & prod_ids(e)) and g.kind != "problem":
                continue
            cands.append((_pair_score(g, e, graph), g.gid, e.id, g, e))
    cands.sort(key=lambda c: -c[0])
    gold_done: dict[str, object] = {}
    for _, gid, eid, g, e in cands:
        if gid in gold_done or eid in used:
            continue
        gold_done[gid] = e
        used.add(eid)
    matches = []
    for g in gold.entities:
        e = gold_done.get(g.gid)
        m = Match(gold=g.model_dump(), produced=e)
        if e is not None:
            _dims(m, g, e, graph)
        matches.append(m)
    unmatched = [e for e in produced if e.id not in used]
    return matches, unmatched


def _dims(m: Match, g, e, graph):
    d = m.dims
    if g.target is not None or (_tooth(e) is not None and g.kind == "item"):
        d["tooth"] = _tooth(e) == g.target
    if g.target_relation and e.kind == "item":
        d["target_relation"] = e.target_relation == g.target_relation
    for k, v in g.key_attributes.items():
        if k == "role":
            d["role"] = e.role == v
            continue
        pv = _produced_value(e, k, graph)
        if k in TEXT_KEYS and isinstance(v, str):
            if pv in (None, ""):
                d[f"attr:{k}"] = False
            elif str(pv).strip().lower() == v.strip().lower():
                d[f"attr:{k}"] = True
            else:
                d[f"attr:{k}"] = None
                m.pending.append((f"attr:{k}", v, pv))
        else:
            d[f"attr:{k}"] = _same(k, v, pv)
    if g.assertion and e.kind == "item":
        d["assertion"] = e.assertion == g.assertion
        if g.assertion in NEGATED or e.assertion in NEGATED:
            d["negation"] = (g.assertion in NEGATED) == (e.assertion in NEGATED)
    if g.time_context and e.kind == "item":
        d["time_context"] = e.time_context == g.time_context
    if g.assertion_source:
        d["assertion_source"] = e.assertion_source == g.assertion_source
    if g.action:
        d["action"] = e.attributes.get("action") == g.action
    for k, v in g.status_fields.items():
        d[f"status:{k}"] = e.attributes.get(k) == v


def critical_bucket(dim: str) -> str | None:
    if dim == "tooth":
        return "tooth"
    if dim == "negation":
        return "negation"
    key = dim.split(":", 1)[-1]
    return CRITICAL.get(key)


def match_flags(gold: GoldCase, flags, tolerated: list[str], mode: str):
    produced = [f for f in flags if f.origin != "E3"]
    out = {"caught": [], "missed": [], "duplicates": [], "false_alarms": [], "tolerated": [], "questions":
           [f.rule_id for f in flags if f.origin == "E3"], "unmatched_detail": []}
    used = set()
    for gf in gold.expected_flags:
        gev = {e.utterance_id or e.quick_note_id for e in gf.evidence}
        hits = [f for f in produced if f.rule_id == gf.rule_id and f.id not in used and
                (gf.target is None or f.target in (None, gf.target)) and
                (not gev or gev & {s.source_id for s in f.evidence})]
        if hits:
            out["caught"].append(gf.rule_id)
            used.add(hits[0].id)
            for h in hits[1:]:
                out["duplicates"].append(h.rule_id)
                used.add(h.id)
        else:
            out["missed"].append(gf.rule_id)
    for f in produced:
        if f.id in used:
            continue
        out["unmatched_detail"].append({"rule_id": f.rule_id, "severity": f.severity, "message": f.message,
                                        "technical": f.rule_id in TECHNICAL_SAFEGUARDS,
                                        "evidence": sorted({s.source_id for s in f.evidence})})
        if f.rule_id in tolerated or f"{f.rule_id}:{mode}" in tolerated:
            out["tolerated"].append(f.rule_id)
        else:
            out["false_alarms"].append(f"{f.rule_id}{' (technical)' if f.rule_status == 'technical' and f.rule_id in TECHNICAL_SAFEGUARDS else ''}")
    return out


TECHNICAL_SAFEGUARDS = {"unsupported_content", "incomplete_section", "stage_failure", "open_conflict",
                        "open_review_task", "unknown_option_link", "pending_critical_correction",
                        "target_not_assessable"}


def forbidden(gold: GoldCase, note_md: str | None) -> list[str]:
    text = (note_md or "").lower()
    return [w for w in gold.forbidden_facts if w.lower() in text]


def check_expectations(expect: list[dict], graph, flags, note_md: str, sources, mode: str) -> list[dict]:
    out = []
    items = graph.active("item") if graph else []

    def ent_ok(e, c):
        if c.get("kind") and e.kind != c["kind"]:
            return False
        if c.get("type") and getattr(e, "type", None) != c["type"]:
            return False
        if "tooth" in c and _tooth(e) != c["tooth"]:
            return False
        if c.get("assertion_in") and e.assertion not in c["assertion_in"]:
            return False
        for k in ("certainty", "decision", "medication_status", "action", "option_link"):
            if k in c and e.attributes.get(k) != c[k]:
                return False
        if "relation_kind" in c and getattr(e, "relation_kind", None) != c["relation_kind"]:
            return False
        if "time_context" in c and e.time_context != c["time_context"]:
            return False
        if "assertion_source" in c and e.assertion_source != c["assertion_source"]:
            return False
        if "text_contains" in c and c["text_contains"].lower() not in " ".join(
                str(v) for v in (e.attributes.values() if e.kind == "item" else [])).lower():
            return False
        return True

    for c in expect:
        if c.get("modes") and mode not in c["modes"]:
            continue
        kind = c["check"]
        ents = graph.active() if graph else []
        if kind == "entity":
            ok = any(ent_ok(e, c) for e in ents)
        elif kind == "no_entity":
            ok = not any(ent_ok(e, c) for e in ents)
        elif kind == "count":
            ok = sum(1 for e in items if e.type == c["type"]) == c["n"]
        elif kind == "count_kind":
            ok = sum(1 for e in ents if e.kind == c["kind"]) == c["n"]
        elif kind == "flag_present":
            ok = any(f.rule_id == c["rule_id"] for f in flags)
        elif kind == "flag_absent":
            ok = not any(f.rule_id == c["rule_id"] for f in flags)
        elif kind == "flag_severity":
            ok = any(f.rule_id == c["rule_id"] and f.severity == c["severity"] for f in flags)
        elif kind == "conflict":
            cs = [x for x in (graph.conflicts if graph else []) if x.kind == c["kind"]]
            ok = bool(cs) and (not c.get("later_contains") or any(
                x.later_statement and c["later_contains"] in x.later_statement.text.lower() for x in cs))
        elif kind == "role":
            entry = sources.roles.entries.get(c["speaker"])
            ok = entry is not None and entry.role == c["role"]
        elif kind == "note_contains":
            ok = c["text"].lower() in (note_md or "").lower()
        elif kind == "note_lacks":
            ok = c["text"].lower() not in (note_md or "").lower()
        else:
            ok = False
        out.append({**c, "pass": ok})
    return out


def score_case(gold: GoldCase, graph, flags, note_md, sources, mode, expect=None, tolerated=()) -> CaseScore:
    mapping, merged, split, target_acc = map_problems(gold, graph)
    matches, unmatched = match_entities(gold, graph, mapping)
    return CaseScore(case_id=gold.case_id, problem_map=mapping, merged=merged, split=split, target_accuracy=target_acc,
                     matches=matches, unmatched_produced=unmatched,
                     flags=match_flags(gold, flags, list(tolerated), mode), forbidden_hits=forbidden(gold, note_md),
                     expectations=check_expectations(expect or [], graph, flags, note_md, sources, mode))


def apply_grades(score: CaseScore, grades: dict[str, str]) -> None:
    """Fill free-text dimensions from Grader verdicts (keyed '<gid>|<dim>'); 'uncertain' counts as wrong."""
    for m in score.matches:
        for dim, _, _ in m.pending:
            v = grades.get(f"{m.gold['gid']}|{dim}")
            m.dims[dim] = (v == "equivalent") if v is not None else None


def tooth_by_type(score) -> dict[str, list[int]]:
    """Tooth accuracy per gold item type, over matched tooth-bearing items whose gold names a tooth."""
    out: dict[str, list[int]] = {t: [0, 0] for t in TOOTH_BEARING}
    for m in score.matches:
        t = m.gold.get("type")
        if m.produced is None or t not in out or m.gold.get("target") is None or "tooth" not in m.dims:
            continue
        out[t][0] += bool(m.dims["tooth"])
        out[t][1] += 1
    return out
