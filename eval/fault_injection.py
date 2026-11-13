"""Fault injection (section 14.4).

Start from gold converted to the graph schema with correct spans and derivations, inject one fault at a time,
and report per check (Cv, Cs, rules) what was caught, missed, and falsely rejected on the unmodified gold.
Faults are tagged derivation-breaking (Cv should catch) or association-preserving (spans and derivations stay
valid; only the meaning checks can catch them).

python -m eval.fault_injection --cases case1 case2 case3 m01_control_tooth m18_two_problems --out eval/results/faults
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from collections import defaultdict
from pathlib import Path

from pipeline import normalize
from pipeline.graph import fill_speakers, rehash_all
from pipeline.overlays import sources_from_objects
from pipeline.relations import compute_target_relations
from pipeline.rules import RuleContext, run_rules
from pipeline.stage_runs import StageRunLog
from pipeline.storage import ROOT
from pipeline.trace import Tracer
from pipeline.transcribe import parse_text_transcript
from pipeline.verify import CheckLog, run_cv, summarize_all
from schemas.entities import ATTRIBUTE_MODELS, Derivation, Item, Problem, Relationship, Span, compare_table
from schemas.graph import Graph
from schemas.sources import QuickNote, QuickNotesSource, RolesOverlay, UtterancesSource

EVAL = ROOT / "eval"
FAULT_TRACE: list = [None]   # set by main(): Cs/Ce calls are traced to <out>/fault_traces.jsonl
QUALIFIERS = re.compile(r"\b(a little|a bit|slightly|mild|mildly|about|maybe|around|small|early|quickly|pretty fast|"
                        r"not|no|possible|probably)\b\s*", re.I)


# ---------------------------------------------------------------- gold -> graph

def case_dir(case_id: str) -> Path:
    return EVAL / ("matrix" if (EVAL / "matrix" / case_id).exists() else "cases") / case_id


def load_sources(case_id: str):
    d = case_dir(case_id)
    utts, roles = parse_text_transcript((d / "transcript.txt").read_text())
    notes = [l.strip() for l in (d / "quick_notes.txt").read_text().splitlines() if l.strip()]
    qn = QuickNotesSource(notes=[QuickNote(id=f"q{i + 1}", text=t) for i, t in enumerate(notes)])
    return sources_from_objects(UtterancesSource(provider="text", utterances=utts), qn,
                                roles=RolesOverlay(entries=roles, confirmed=True))


def _spans(g, sources) -> list[Span]:
    out = []
    for e in g["evidence"]:
        sid = e.get("utterance_id") or e.get("quick_note_id")
        st = "transcript" if e.get("utterance_id") else "quick_note"
        text = sources.source_text(st, sid)
        if text is not None:
            out.append(Span(source_type=st, source_id=sid, start=0, end=len(text), text=text))
    return out


def find_derivation(rule: str, value, spans, attribute: str) -> Derivation | None:
    """The shortest word window in an evidence span that the rule normalizes to the value."""
    best = None
    for i, s in enumerate(spans):
        words = re.findall(r"[#\w/.\-']+", s.text)
        for n in range(1, 7):
            for k in range(len(words) - n + 1):
                frm = " ".join(words[k:k + n]).strip(".,?!")
                if frm.lower() not in s.text.lower():
                    continue
                try:
                    got = normalize.apply(rule, frm)
                except normalize.NormalizationError:
                    continue
                if rule == "bp_reading":
                    got = int(got.split("/")[0 if attribute.endswith("systolic") else 1])
                if normalize.values_equal(got, value):
                    cand = Derivation.model_validate({"attribute": attribute, "rule": rule, "from": frm, "to": value,
                                                      "evidence_index": i})
                    if best is None or len(frm) < len(best.from_):
                        best = cand
            if best is not None:
                return best
    return best


def _negation(spans) -> Derivation | None:
    from pipeline.verify import NEGATION_CUES
    for i, s in enumerate(spans):
        m = NEGATION_CUES.search(s.text)
        if not m:
            continue
        # Concept in the same span (after the cue) or in the clinician's question directly before.
        if i > 0 and spans[i - 1].text.rstrip().endswith("?"):
            return Derivation.model_validate({"attribute": "assertion", "rule": "negation", "from": m.group(0),
                                              "to": "negated", "evidence_index": i,
                                              "concept": spans[i - 1].text.rstrip("?").strip(),
                                              "concept_evidence_index": i - 1})
        rest = s.text[m.end():].strip(" ,.;")
        if rest:
            return Derivation.model_validate({"attribute": "assertion", "rule": "negation", "from": m.group(0),
                                              "to": "negated", "evidence_index": i, "concept": rest.split(";")[0][:40].strip(),
                                              "concept_evidence_index": i})
    return None


def gold_graph(case_id: str):
    gold = json.loads((EVAL / "gold" / f"{case_id}.json").read_text())
    sources = load_sources(case_id)
    g = Graph(pipeline_mode="team", version=1)
    gaps: list[str] = []
    pid = {}
    n = {"pb": 0, "rl": 0, "it": 0}

    def nid(prefix):
        n[prefix] += 1
        return f"{prefix}_{n[prefix]}" if prefix != "it" else f"it_{n[prefix]:03d}"

    def derive(entity, path, rule, value, spans):
        d = find_derivation(rule, value, spans, path)
        if d is None:
            gaps.append(f"{entity.get('gid')}: no {rule} derivation for {path}={value!r}")
        return d

    for ge in [x for x in gold["entities"] if x["kind"] == "problem"]:
        spans = _spans(ge, sources)
        ka = ge["key_attributes"]
        derivs, target = [], ge["target"]
        if target is not None:
            d = derive(ge, "clinical_target.tooth", "spoken_tooth_number", target, spans)
            derivs += [d] if d else []
            target = target if d else None
        p = Problem(id=nid("pb"), key=ge["problem_key"], role=ka.get("role", "chief"), complaint_text=ka.get("complaint_text"),
                    complaint_location={"free_text": ka.get("complaint_location")}, clinical_target={"tooth": target},
                    assertion_source="patient_report", evidence=spans, derivations=derivs, owner="Br")
        pid[ge["problem_key"]] = p.id
        g.entities.append(p)
    options = {}
    for ge in [x for x in gold["entities"] if x["kind"] != "problem"]:
        spans = _spans(ge, sources)
        if not spans:
            gaps.append(f"{ge['gid']}: no evidence spans")
            continue
        derivs = []
        if ge["kind"] == "relationship":
            d = derive(ge, "tooth", "spoken_tooth_number", ge["target"], spans)
            if d is None:
                continue
            g.entities.append(Relationship(id=nid("rl"), problem_id=pid[ge["problem_key"]], tooth=ge["target"],
                                           relation_kind=ge["key_attributes"]["relation_kind"], owner="Br",
                                           assertion_source="clinician_observation", evidence=spans, derivations=[d]))
            continue
        t = ge["type"]
        model = ATTRIBUTE_MODELS[t]
        attrs = {k: v for k, v in {**ge["key_attributes"], **ge["status_fields"]}.items() if k in model.model_fields}
        if ge.get("action"):
            attrs["action"] = ge["action"]
        target = {"tooth": ge["target"]}
        if ge["target"] is not None:
            d = derive(ge, "target.tooth", "spoken_tooth_number", ge["target"], spans)
            if d:
                derivs.append(d)
            else:
                target["tooth"] = None
        if ge["key_attributes"].get("surface"):
            d = derive(ge, "target.surface", "surface_code", ge["key_attributes"]["surface"], spans)
            if d:
                derivs.append(d)
                target["surface"] = ge["key_attributes"]["surface"]
        table = compare_table("item", t)
        for k in list(attrs):
            rule = table[f"attributes.{k}"].get("rule")
            if rule and attrs[k] is not None:
                d = derive(ge, f"attributes.{k}", rule, attrs[k], spans)
                if d:
                    derivs.append(d)
                else:
                    attrs[k] = None
        if t == "vital_reading":
            attrs.setdefault("sequence", None)
        if t == "decision":
            opt = ge["key_attributes"].get("option")
            hit = None
            for oid, otext in options.items():
                if opt and set(opt.lower().split()) & set((otext or "").lower().split()):
                    hit = oid
            attrs.pop("option", None)
            attrs.update(option_id=hit, option_link="linked" if hit else "unknown")
        if t == "consent_element":
            attrs["link"] = "unknown"
        assertion = ge.get("assertion") or "present"
        if assertion in ("absent", "denied"):
            d = _negation(spans)
            if d:
                derivs.append(d)
            else:
                gaps.append(f"{ge['gid']}: no negation derivation")
        scope = ge.get("scope") or "problem"
        it = Item(id=nid("it"), type=t, scope=scope, problem_id=pid.get(ge["problem_key"]) if scope == "problem" else None,
                  target=target, attributes=attrs, assertion=assertion, time_context=ge.get("time_context") or "current",
                  assertion_source=ge.get("assertion_source") or "unknown", evidence=spans, derivations=derivs,
                  owner="gold", local_key=ge["gid"])
        if t == "option_discussed":
            options[it.id] = attrs.get("option")
        g.entities.append(it)
    for e in g.entities:
        fill_speakers(e, sources)
    rehash_all(g, sources.roles)
    return g, sources, gaps


# ---------------------------------------------------------------- faults

def _pick(g, pred):
    return next((e for e in g.active("item") if pred(e)), None)


def _other_tooth_mention(g, sources, avoid: set[int]):
    for u in sources.utterances.utterances:
        for m in re.finditer(r"(number\s+[a-z\-]+|#\d+|\b(?:" + "|".join(sorted(
                __import__("glossary").SPOKEN_TOOTH_NUMBERS, key=len, reverse=True)) + r")\b)", u.text, re.I):
            try:
                n = normalize.spoken_tooth_number(m.group(0))
            except normalize.NormalizationError:
                continue
            if n not in avoid:
                return u, m.group(0), n
    return None


def faults(g, sources):
    """Yield (name, tag, mutate) where mutate(graph) returns the ids of the changed/added entities or None."""
    def tooth_swap(gr):
        e = _pick(gr, lambda x: x.target.tooth is not None)
        if not e:
            return None
        e.target.tooth = e.target.tooth % 32 + 1
        return [e.id]

    def dose_change(gr):
        e = _pick(gr, lambda x: x.type in ("prescription", "medication") and x.attributes.get("strength"))
        if not e:
            return None
        num = float(e.attributes["strength"].split()[0])
        e.attributes["strength"] = f"{int(num / 2)} {e.attributes['strength'].split()[1]}"
        for d in e.derivations:
            if d.attribute == "attributes.strength":
                d.to = e.attributes["strength"]
        return [e.id]

    def negation_flip(gr):
        e = _pick(gr, lambda x: x.assertion == "present" and x.type in ("symptom", "finding"))
        if not e:
            return None
        e.assertion = "absent"
        return [e.id]

    def certainty_flip(gr):
        e = _pick(gr, lambda x: x.type == "diagnosis" and x.attributes.get("certainty"))
        if not e:
            return None
        e.attributes["certainty"] = "definite" if e.attributes["certainty"] == "possible" else "possible"
        if e.attributes["certainty"] == "possible":
            e.assertion = "possible"
        return [e.id]

    def time_flip(gr):
        e = _pick(gr, lambda x: x.time_context == "historical") or _pick(gr, lambda x: x.type in ("symptom", "medication"))
        if not e:
            return None
        e.time_context = "current" if e.time_context == "historical" else "historical"
        return [e.id]

    def number_on_wrong_tooth(gr):
        e = _pick(gr, lambda x: x.type == "finding" and x.target.tooth is not None)
        if not e:
            return None
        hit = _other_tooth_mention(gr, sources, {e.target.tooth})
        if not hit:
            return None
        u, words, tooth = hit
        e.evidence.append(Span(source_type="transcript", source_id=u.id, start=0, end=len(u.text), text=u.text))
        e.derivations = [d for d in e.derivations if d.attribute != "target.tooth"]
        e.derivations.append(Derivation.model_validate({"attribute": "target.tooth", "rule": "spoken_tooth_number",
                                                        "from": words, "to": tooth, "evidence_index": len(e.evidence) - 1}))
        e.target.tooth = tooth
        fill_speakers(e, sources)
        return [e.id]

    def wrong_problem(gr):
        probs = gr.active("problem")
        if len(probs) < 2:
            return None
        e = _pick(gr, lambda x: x.type == "finding" and x.scope == "problem" and x.problem_id != probs[0].id)
        if not e:
            return None
        e.problem_id = probs[0].id
        return [e.id]

    def dropped_qualifier(gr):
        for e in gr.active("item"):
            for k, v in e.attributes.items():
                meta = compare_table("item", e.type).get(f"attributes.{k}", {})
                if isinstance(v, str) and meta.get("compare") == "semantic" and QUALIFIERS.search(v):
                    e.attributes[k] = QUALIFIERS.sub("", v).strip() or v
                    if e.attributes[k] != v:
                        return [e.id]
        return None

    def misattributed(gr):
        e = _pick(gr, lambda x: x.assertion_source == "patient_report")
        if not e:
            return None
        e.assertion_source = "clinician_assessment"
        return [e.id]

    def false_control(gr):
        p = gr.chief()
        if p is None or p.clinical_target.tooth is None:
            return None
        hit = _other_tooth_mention(gr, sources, {p.clinical_target.tooth} | {r.tooth for r in gr.active("relationship")})
        if not hit:
            return None
        u, words, tooth = hit
        sp = Span(source_type="transcript", source_id=u.id, start=0, end=len(u.text), text=u.text)
        r = Relationship(id="rl_fault", problem_id=p.id, tooth=tooth, relation_kind="control", owner="Br",
                         assertion_source="clinician_observation", evidence=[sp],
                         derivations=[Derivation.model_validate({"attribute": "tooth", "rule": "spoken_tooth_number",
                                                                 "from": words, "to": tooth, "evidence_index": 0})])
        fill_speakers(r, sources)
        gr.entities.append(r)
        # A finding on that tooth, so the relationship would suppress the target flag if accepted.
        if not any(x.target.tooth == tooth for x in gr.active("item")):
            f = Item(id="it_fault", type="finding", scope="problem", problem_id=p.id, target={"tooth": tooth},
                     attributes={"observation": "examined"}, assertion_source="clinician_observation", evidence=[sp],
                     derivations=[Derivation.model_validate({"attribute": "target.tooth", "rule": "spoken_tooth_number",
                                                             "from": words, "to": tooth, "evidence_index": 0})],
                     owner="gold")
            fill_speakers(f, sources)
            gr.entities.append(f)
        return ["rl_fault"]

    return [("tooth_swap", "derivation-breaking", tooth_swap), ("dose_change", "derivation-breaking", dose_change),
            ("negation_flip", "derivation-breaking", negation_flip),
            ("possible_definite", "association-preserving", certainty_flip),
            ("historical_current", "association-preserving", time_flip),
            ("number_on_wrong_tooth", "association-preserving", number_on_wrong_tooth),
            ("finding_wrong_problem", "association-preserving", wrong_problem),
            ("dropped_qualifier", "association-preserving", dropped_qualifier),
            ("patient_as_clinician", "association-preserving", misattributed),
            ("false_control_relationship", "association-preserving", false_control)]


# ---------------------------------------------------------------- checking

class _Run:
    """What pipeline.compare.run_semantic needs, without a session."""

    def __init__(self, graph, sources, client=None):
        from pipeline.orchestrator import default_agents
        self.graph, self.sources, self.client = graph, sources, client
        self.agents = default_agents()
        self.mode, self.run_id, self.issues = "team", "fault", []
        self.tracer = Tracer(path=FAULT_TRACE[0])
        self.stage_log = StageRunLog()
        self.check_log = CheckLog()

    def agent(self, name):
        return self.agents[name](client=self.client, tracer=self.tracer)

    def record(self, stage, agent, status, error=None, started=None, extra=None, **_):
        return self.stage_log.record(stage, agent, status, error=error, started=started, run_id=self.run_id, extra=extra)


def check(graph, sources, entity_ids, log: CheckLog, client=None):
    from pipeline.compare import run_semantic
    targets = [e for e in graph.active() if e.id in entity_ids]
    run_cv(targets, sources, log)
    r = _Run(graph, sources, client)
    r.check_log = log
    config, _ = run_semantic(r, targets)
    summarize_all(graph, log, "team", config)
    compute_target_relations(graph, "team")
    flags, _ = run_rules(RuleContext(graph=graph, mode="team", rule_mode="synthetic_demo", sources=sources))
    return {(f.rule_id, tuple(sorted(f.entity_ids))) for f in flags}, r.tracer.totals()


def run_case(case_id: str, client=None) -> dict:
    base, sources, gaps = gold_graph(case_id)
    log = CheckLog()
    base_flags, cost = check(base, sources, {e.id for e in base.active()}, log, client)
    false_rej = {"Cv": [e.ref for e in base.active() if "fail" in (e.checks.span_valid, e.checks.normalization_valid)],
                 "Cs_fail": [e.ref for e in base.active() if e.checks.semantic_support == "fail"],
                 "Cs_unconfirmed": [e.ref for e in base.active() if e.checks.semantic_support == "unconfirmed"],
                 "entities": len(base.active())}
    base_checks = {e.id: e.checks.model_copy() for e in base.active()}
    results = []
    for name, tag, mutate in faults(base, sources):
        g = base.model_copy(deep=True)
        changed = mutate(g)
        if not changed:
            results.append({"fault": name, "tag": tag, "applicable": False})
            continue
        rehash_all(g, sources.roles)
        for e in g.active():
            if e.id in base_checks and e.id not in changed:
                e.checks = base_checks[e.id].model_copy()
        flog = CheckLog(records=list(log.records))
        flags, c = check(g, sources, set(changed) | {e.id for e in g.active() if e.id not in base_checks}, flog, client)
        for k in ("calls", "input_tokens", "output_tokens"):
            cost[k] += c[k]
        e = g.get(changed[0])
        new_flags = sorted(f[0] for f in flags - base_flags)
        cv = "fail" in (e.checks.span_valid, e.checks.normalization_valid)
        results.append({"fault": name, "tag": tag, "applicable": True, "entity": e.ref,
                        "Cv_caught": cv, "Cs": e.checks.semantic_support,
                        "rules_new_flags": new_flags,
                        "Cs_details": next((r["details"] for r in reversed(flog.records)
                                            if r["entity_id"] == e.id and r["check"] == "semantic_support"), None)})
    return {"case": case_id, "conversion_gaps": gaps, "false_rejections": false_rej, "faults": results, "cost": cost}


def write_report(rows, out: Path):
    L = ["# Fault injection report\n",
         "> Built from **draft gold (annotated_by: claude, not yet checked)** converted to the graph schema with "
         "whole-utterance spans and derivations found automatically. Cs is a real model call; Cv and rules are Python.\n"]
    L.append("## False rejections on unmodified gold\n\n| Case | Entities | Cv fail | Cs fail | Cs unconfirmed | Conversion gaps |\n|---|---|---|---|---|---|")
    tot = defaultdict(int)
    for r in rows:
        fr = r["false_rejections"]
        L.append(f"| {r['case']} | {fr['entities']} | {len(fr['Cv'])} | {len(fr['Cs_fail'])} | {len(fr['Cs_unconfirmed'])} | {len(r['conversion_gaps'])} |")
        for k in ("entities",):
            tot[k] += fr[k]
        tot["Cv"] += len(fr["Cv"])
        tot["Cs_fail"] += len(fr["Cs_fail"])
        tot["Cs_unc"] += len(fr["Cs_unconfirmed"])
    L.append(f"| **all** | {tot['entities']} | {tot['Cv']} | {tot['Cs_fail']} | {tot['Cs_unc']} | |\n")
    for tag in ("derivation-breaking", "association-preserving"):
        L.append(f"## {tag.capitalize()} faults\n\n| Fault | Applied in | Cv caught | Cs fail | Cs unconfirmed | Rules (new flag) | Missed by all |\n|---|---|---|---|---|---|---|")
        agg = defaultdict(lambda: defaultdict(int))
        for r in rows:
            for f in r["faults"]:
                if f["tag"] != tag or not f["applicable"]:
                    continue
                a = agg[f["fault"]]
                a["n"] += 1
                a["cv"] += f["Cv_caught"]
                a["cs_fail"] += f["Cs"] in ("fail", "not_assessed_due_to_failure")
                a["cs_unc"] += f["Cs"] == "unconfirmed"
                a["rules"] += bool(f["rules_new_flags"])
                a["missed"] += not (f["Cv_caught"] or f["Cs"] != "pass" or f["rules_new_flags"])
        T = defaultdict(int)
        for name, a in agg.items():
            L.append(f"| {name} | {a['n']} | {a['cv']} | {a['cs_fail']} | {a['cs_unc']} | {a['rules']} | {a['missed']} |")
            for k, v in a.items():
                T[k] += v
        L.append(f"| **total** | {T['n']} | {T['cv']} | {T['cs_fail']} | {T['cs_unc']} | {T['rules']} | {T['missed']} |\n")
    L.append("Association-preserving detection (Cs fail or unconfirmed) is the headline number for the meaning checks. "
             "`unconfirmed` means the entity is not accepted and is shown as not confirmed from evidence; it is "
             "counted separately from an outright mismatch.\n")
    L.append("## Per-fault detail\n")
    for r in rows:
        for f in r["faults"]:
            if f["applicable"]:
                L.append(f"- {r['case']} · {f['fault']} on {f['entity']}: Cv={'caught' if f['Cv_caught'] else 'pass'}, "
                         f"Cs={f['Cs']}, new flags={f['rules_new_flags'] or '—'}" +
                         (f" — {'; '.join(f['Cs_details'])[:200]}" if f.get("Cs_details") else ""))
            else:
                L.append(f"- {r['case']} · {f['fault']}: not applicable to this case")
    L.append("\n## Conversion gaps\n")
    for r in rows:
        for gap in r["conversion_gaps"]:
            L.append(f"- {r['case']}: {gap}")
    (out / "fault_report.md").write_text("\n".join(L) + "\n", "utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", default=["case1", "case2", "case3"])
    ap.add_argument("--out", default="eval/results/faults")
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    FAULT_TRACE[0] = out / "fault_traces.jsonl"
    rows = []
    for c in args.cases:
        rows.append(run_case(c))
        print(f"faults done: {c}", flush=True)
    (out / "faults.json").write_text(json.dumps(rows, indent=1, default=str))
    write_report(rows, out)
    print(f"report: {out / 'fault_report.md'}")


if __name__ == "__main__":
    main()
