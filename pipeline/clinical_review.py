"""E3 orchestration: Python finds runnable rule instances; the agent writes the questions (section 9.3)."""
from __future__ import annotations

import re
from functools import lru_cache

import yaml

from pipeline.dispositions import accepted
from pipeline.flags import make_flag
from pipeline.render import entity_text
from pipeline.rules import PENDING_LABEL, PRECAUTION, RULES_DIR
from pipeline.storage import atomic_write_json, hash_obj, read_json, sha256_text

PULPAL = re.compile(r"pulpitis|necros|necrot|apical periodontitis|abscess|pulp", re.I)
SRP = re.compile(r"scaling and root planing|\bSRP\b|deep clean", re.I)
PERIO_FINDING = re.compile(r"bleed|calculus|tartar|recession|attachment loss|bone loss|pocket", re.I)


@lru_cache(maxsize=1)
def review_rules() -> dict:
    return yaml.safe_load((RULES_DIR / "clinical_review_rules.yaml").read_text("utf-8"))


def rule_active(rule: dict, rule_mode: str) -> bool:
    return rule_mode == "synthetic_demo" or rule.get("status") == "approved"


def _line(e, graph) -> str:
    return f"{e.id}: {e.type if e.kind == 'item' else e.kind} — {entity_text(e, graph)[0]}"


def runnable_instances(graph, rule_mode: str) -> tuple[list[dict], list[str]]:
    rules = {r["id"]: r for r in review_rules()["rules"]}
    notices, out = [], []
    items = graph.active("item")
    for rid, rule in rules.items():
        if not rule_active(rule, rule_mode):
            notices.append(f"Clinical review rule {rid} not active: pending dentist approval")
            continue
        for p in graph.active("problem"):
            on = [i for i in items if i.problem_id == p.id]
            ents = []
            if rid == "perio_rationale":
                recs = [i for i in on if i.type in ("option_discussed", "next_visit", "treatment_today")
                        and SRP.search(" ".join(str(v) for v in i.attributes.values() if isinstance(v, str)))
                        and i.assertion_source == "clinician_assessment"]
                support = [i for i in items if i.type == "perio_measurement" or
                           (i.type == "radiograph" and i.attributes.get("bone_loss")) or
                           (i.type == "finding" and PERIO_FINDING.search(
                               " ".join(str(v) for v in i.attributes.values() if isinstance(v, str))))]
                if recs and not support:
                    ents = recs
            elif rid == "endo_findings_review":
                dx = [i for i in on if i.type == "diagnosis" and i.assertion_source == "clinician_assessment"
                      and PULPAL.search(i.attributes.get("diagnosis") or "")]
                if dx:
                    ents = dx + [i for i in on if i.type in ("symptom", "finding", "radiograph")]
            elif rid == "diagnosis_without_findings":
                dx = [i for i in on if i.type == "diagnosis" or
                      (i.type == "option_discussed" and i.attributes.get("recommended_by_clinician"))]
                if dx and not any(i.type in ("finding", "radiograph") for i in on):
                    ents = dx
            if ents:
                out.append({"rule_id": rid, "version": str(rule["version"]), "description": rule["description"],
                            "template": rule["question_template"], "severity": rule["severity"],
                            "status": rule["status"], "problem_id": p.id, "entity_objs": ents,
                            "entities": [_line(e, graph) for e in ents]})
    return out, notices


def _inputs_hash(instances) -> str:
    return hash_obj([{"rule": r["rule_id"], "v": r["version"],
                      "e": sorted(f"{e.ref}:{e.content_hash}:{e.support_hash}" for e in r["entity_objs"])}
                     for r in instances] + [sha256_text((RULES_DIR / "clinical_review_rules.yaml").read_bytes())])[:16]


def run_e3(session, graph, sources, mode, rule_mode, *, client=None, agents=None, tracer=None, record, run_id=None,
           retry: bool = False):
    instances, notices = runnable_instances(graph, rule_mode)
    if not instances:
        record("E", "E3", "not_applicable")
        return [], notices
    ih = _inputs_hash(instances)
    cache_path = session.path("outputs", f"e3_{ih}.json")
    cached = read_json(cache_path)
    prior = _latest_run(session, ih)
    if prior is not None and prior["status"] == "failed" and not retry:
        # No retry loops: a failed E3 is re-run only by an explicit Retry or when its own inputs change.
        accepted_ = _accepted_failure(graph, prior)
        notices.append("No clinical review questions: E3 failed" +
                       (" and the failure was accepted." if accepted_ else " (Retry available; see task)."))
        return [], notices
    if cached is None:
        from agents.e3_clinical_review import E3ClinicalReviewAgent
        cls = (agents or {}).get("E3", E3ClinicalReviewAgent)
        try:
            from pipeline.trace import Tracer
            out = cls(client=client, tracer=tracer or Tracer()).review(
                [{k: v for k, v in r.items() if k != "entity_objs"} for r in instances])
            cached = out.model_dump(mode="json")
            atomic_write_json(cache_path, cached)
            _record(record, "succeeded", ih)
        except Exception as exc:  # noqa: BLE001
            _record(record, "failed", ih, error=f"{type(exc).__name__}: {str(exc)[:200]}")
            notices.append("No clinical review questions: E3 failed (see task).")
            return [], notices
    else:
        _record(record, "succeeded", ih, extra={"cached": True})
    flags = []
    by_rule = {r["rule_id"]: r for r in instances}
    for q in cached["questions"]:
        inst = by_rule.get(q["rule_id"])
        if inst is None:
            continue
        valid = {e.id: e for e in inst["entity_objs"]}
        ents = [valid[i] for i in q["entity_ids"] if i in valid] or inst["entity_objs"][:1]
        precaution = any(not accepted(graph, e, mode) for e in ents)
        msg = q["question"] + (f" {PRECAUTION}" if precaution else "") + \
            (f" ({PENDING_LABEL})" if inst["status"] == "pending" else "")
        flags.append(make_flag(q["rule_id"], {"version": inst["version"], "class": "clinical",
                                              "status": inst["status"]},
                               severity=inst["severity"], message=msg, graph=graph, entities=ents, origin="E3",
                               question=True, precautionary=precaution, problem_id=inst["problem_id"],
                               rule_hash=ih, safety_critical=False))
    return flags, notices


def _record(record, status, ih, error=None, extra=None):
    record("E", "E3", status, error=error, extra={"e3_inputs": ih, **(extra or {})})


def _latest_run(session, ih):
    from pipeline.stage_runs import session_stage_log
    runs = [r for r in session_stage_log(session).runs if r["stage"] == "E" and r["agent"] == "E3"
            and r.get("e3_inputs") == ih]
    return runs[-1] if runs else None


def _accepted_failure(graph, run) -> bool:
    """True if this failed E3 run's task was completed with `accepted`."""
    task = next((t for t in graph.tasks if t.stage_run_id == run["id"]), None)
    if task is None or task.status != "completed":
        return False
    disp = graph.disposition(task.disposition_id) if task.disposition_id else None
    return disp is not None and disp.completion == "accepted"
