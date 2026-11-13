"""Plain-language wording for the review page: no internal ids, no check jargon.

Technical text (ids, check names, rule ids) stays available for the collapsed "Details" sections.
"""
from __future__ import annotations

import re

from pipeline.render import entity_text
from pipeline.template import template

_ID = re.compile(r"\s*\(?\b(?:it_\d+|pb_\w+|rl_\w+|tk_\w+|st_\w+|cf_\w+|pc_\w+|ds_\w+|fl_\w+)\b\)?")
_PENDING = " (Rule pending dentist confirmation.)"
_UNCONFIRMED = " Depends on unconfirmed information."

TYPE_LABEL = {
    "history_change": "health history", "medication": "medication", "allergy": "allergy",
    "vital_reading": "blood pressure", "symptom": "symptom", "finding": "exam finding",
    "perio_measurement": "gum measurement", "radiograph": "x-ray", "diagnosis": "diagnosis",
    "option_discussed": "treatment option", "decision": "patient decision", "consent_element": "discussion point",
    "treatment_today": "treatment today", "prescription": "prescription", "referral": "referral",
    "next_visit": "next visit", "instruction": "instruction",
}
AGENT_LABEL = {
    "B0": "note extraction", "Br": "chief complaint", "B1": "medical history", "B2": "symptoms",
    "B3": "exam findings and x-rays", "B4": "assessment and plan", "Cs": "second read of the note",
    "Ce": "second read of the note", "Co": "missed-item check", "R2": "contradiction check",
    "E3": "clinical review questions", "Linker": "note assembly",
}
FIELD_LABEL = {
    "target.tooth": "tooth", "clinical_target.tooth": "problem tooth", "complaint_location.tooth": "tooth",
    "attributes.strength": "strength", "attributes.dose": "dose", "attributes.frequency_code": "how often",
    "attributes.frequency": "how often", "attributes.duration_days": "number of days", "attributes.drug": "drug",
    "attributes.substance": "allergy", "attributes.systolic": "blood pressure (top number)",
    "attributes.diastolic": "blood pressure (bottom number)", "assertion": "how it was stated",
    "time_context": "timing",
    "assertion_source": "who said it", "attributes.response": "test result", "attributes.lingering": "lingering",
    "attributes.certainty": "certainty", "attributes.decision": "decision", "target.surface": "surface",
}


def strip_ids(text: str) -> str:
    text = _ID.sub("", text or "")
    text = re.sub(r"\bQuick note q\d+\b", "The quick note", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def clean_message(msg: str) -> str:
    return strip_ids(msg.replace(_PENDING, "").replace(_UNCONFIRMED, ""))


def section_title(section_id: str) -> str:
    return next((s["title"] for s in template()["sections"] if s["id"] == section_id), section_id.replace("_", " "))


def describe(e, graph) -> str:
    """A short plain label for an entity, e.g. 'Exam finding: #14; cold; positive/felt'."""
    if e is None:
        return "an item that was removed"
    text = strip_ids(entity_text(e, graph)[0])
    if e.kind == "problem":
        return text
    if e.kind == "relationship":
        return text
    label = TYPE_LABEL.get(e.type, e.type).capitalize()
    where = " (from the quick note)" if e.evidence and all(s.source_type == "quick_note" for s in e.evidence) else ""
    if text.lower().startswith((label.lower(), "allergy", "bp ", "denies")):
        return f"{text}{where}"
    return f"{label}: {text}{where}"


def _value(v) -> str:
    if v is None:
        return "not stated"
    if isinstance(v, int) and not isinstance(v, bool):
        return f"#{v}" if v <= 32 else str(v)
    return str(v)


def why(e, check_log) -> str:
    """Why an entity needs confirming, from its latest failed check results, in plain words."""
    reasons = []
    for check in ("span_valid", "normalization_valid", "semantic_support"):
        rec = check_log.latest(e, check)
        if rec is None or rec["result"] in ("pass", "not_applicable"):
            continue
        details = rec.get("details") or []
        if rec["result"] == "not_assessed_due_to_failure":
            reasons.append("the automatic check couldn't run")
        elif rec["result"] == "unconfirmed":
            reasons.append("a second read couldn't confirm it from the nearby conversation")
        elif check == "span_valid":
            reasons.append("the quoted words don't match the transcript")
        elif check == "normalization_valid":
            for d in details:
                m = re.search(r"(\S+) = (.+?) has no valid (\w+) derivation", d)
                if m:
                    reasons.append(f"the {FIELD_LABEL.get(m.group(1), m.group(1).split('.')[-1])} "
                                   f"({m.group(2).strip(chr(39))}) isn't in the words it cites")
                elif "negation" in d:
                    reasons.append("it isn't clear the \"no\" refers to this")
            if not reasons:
                reasons.append("a number or name couldn't be traced to the words it cites")
        else:
            for d in details:
                for part in d.split("; "):
                    m = re.match(r"(\S+): producer (.+?) vs checker (.+)$", part)
                    if m:
                        field = FIELD_LABEL.get(m.group(1), m.group(1).split(".")[-1].replace("_", " "))
                        if m.group(1) == "problem":
                            reasons.append("a second read linked it to a different complaint")
                        else:
                            reasons.append(f"a second read says {field}: {_unq(m.group(3))} (the note says "
                                           f"{_unq(m.group(2))})")
                    elif "different" in part or "uncertain" in part:
                        reasons.append("a second read described it differently")
            if not reasons:
                reasons.append("a second read disagreed")
    seen, out = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return "; ".join(out[:3]) or "it needs a person to confirm it"


def _unq(v: str) -> str:
    v = v.strip()
    if v in ("None", "'None'"):
        return "nothing"
    v = v.strip("'\"")
    return f"#{v}" if v.isdigit() and 1 <= int(v) <= 32 else v


def conflict_title(c, graph) -> str:
    parts = [graph.get(p.entity_id, p.version) for p in c.participants]
    parts = [p for p in parts if p is not None]
    vitals = [p for p in parts if p.kind == "item" and p.type == "vital_reading"]
    if c.kind == "quick_note_vs_transcript" and vitals:
        said = [v for v in vitals if any(s.source_type == "transcript" for s in v.evidence)]
        written = [v for v in vitals if all(s.source_type == "quick_note" for s in v.evidence)]
        fmt = lambda v: f"{v.attributes.get('systolic')}/{v.attributes.get('diastolic')}"  # noqa: E731
        if said and written:
            return (f"Blood pressure doesn't match the quick note ({', '.join(fmt(v) for v in said)} said vs "
                    f"{', '.join(fmt(v) for v in written)} written)")
    if c.kind == "quick_note_vs_transcript":
        return f"The quick note and the conversation disagree about {c.subject or 'the same thing'}"
    if c.kind == "self_correction":
        later = f": the later statement was “{c.later_statement.text}”" if c.later_statement else ""
        return f"Someone corrected themselves about {c.subject or 'a detail'}{later}"
    return f"Two statements disagree about {c.subject or 'the same thing'}"


def task_title(t, graph) -> str:
    parts = [graph.get(p.entity_id, p.version) for p in t.participants]
    first = next((p for p in parts if p is not None), None)
    quote = f" “{t.evidence[0].text}”" if t.evidence else ""
    if t.kind == "check_failure" and first is not None:
        return f"Confirm: {describe(first, graph)}"
    if t.kind == "omission":
        return f"Possibly missed from the note:{quote}"
    if t.kind == "registry_issue":
        return f"Check the chief complaint and problem tooth{(': ' + describe(first, graph)) if first else ''}"
    if t.kind == "staged_record":
        return "Something the system found couldn't be added automatically"
    if t.kind == "human_override_check":
        return f"An earlier change may need re-checking: {describe(first, graph)}"
    if t.kind == "unknown_option_link":
        return "A decision isn't tied to a specific treatment option"
    if t.kind == "unmatched_contradiction":
        return f"Two statements disagree, and the note doesn't cover them:{quote}"
    if t.kind == "stage_failure":
        agent = next((a for a in AGENT_LABEL if f" {a} " in f" {t.reason} "), None)
        return f"Part of the automatic review didn't run ({AGENT_LABEL.get(agent, 'a step')})"
    return strip_ids(t.reason)


def flag_title(f, graph) -> str:
    rid = f.rule_id
    ents = [graph.get(i) for i in f.entity_ids]
    ents = [e for e in ents if e is not None]
    if rid == "unsupported_content" and ents:
        return f"Confirm: {describe(ents[0], graph)}"
    if rid == "open_conflict":
        c = graph.conflict(f.conflict_ids[0]) if f.conflict_ids else None
        if c is not None:
            return conflict_title(c, graph)
        t = graph.task(f.task_ids[0]) if f.task_ids else None
        return task_title(t, graph) if t else clean_message(f.message)
    if rid in ("open_review_task", "stage_failure"):
        t = graph.task(f.task_ids[0]) if f.task_ids else None
        return task_title(t, graph) if t else clean_message(f.message)
    if rid == "incomplete_section":
        m = re.match(r"Section (\w+)", f.message)
        return f"The {section_title(m.group(1)) if m else 'a'} section couldn't be filled in automatically"
    if rid == "allergy_rx":
        return "Allergy alert: " + clean_message(f.message)
    if rid in ("treatment_target_mismatch", "treatment_target_disagreement"):
        return "Tooth check: " + clean_message(f.message).replace("clinical target", "problem tooth")
    if rid == "bp_reading":
        return clean_message(f.message).replace("at level A", "is elevated").replace("at level B", "is very high")
    return clean_message(f.message)


def staged_label(rec) -> str:
    """What a staged (not added) record was, from the agent's raw output."""
    if rec is None:
        return "an item"
    raw = rec.raw or {}
    kind = TYPE_LABEL.get(raw.get("type"), raw.get("type")) if rec.kind == "item" else \
        {"problem": "chief complaint", "relationship": "related tooth"}.get(rec.kind, rec.kind)
    vals = [str(v) for v in (raw.get("attributes") or {}).values() if v not in (None, "", False, True)]
    if rec.kind == "problem":
        vals = [raw.get("complaint_text") or ""]
    quote = next((q.get("quote") for q in raw.get("evidence") or [] if q.get("quote")), None)
    main = ", ".join(v for v in vals if v)[:70]
    return f"{kind}: {main}" + (f" (\u201c{quote[:60]}\u201d)" if quote and not main else "")


def blocker_text(b: dict, graph, check_log, staging=None) -> str:
    k = b["kind"]
    if k == "no_graph":
        return "No note could be built yet: enter the chief complaint to continue"
    if k == "stale_outputs":
        return "The note is being updated; reload the page"
    if k == "section":
        return f"The {section_title(b['section'])} section couldn't be filled in automatically"
    if k == "check":
        e = graph.get(b["entity_id"])
        return f"Confirm: {describe(e, graph)} — {why(e, check_log)}"
    if k == "pending":
        p = next(p for p in graph.pending_changes if p.id == b["pending_id"])
        verb = {"add": "Add", "edit": "Change", "remove": "Remove", "replace": "Replace",
                "resolve_conflict": "Settle a disagreement"}[p.operation]
        target = graph.get(p.target_versions[0].entity_id, p.target_versions[0].version) if p.target_versions else None
        what = describe(target, graph) if target else _pending_add_label(p)
        return f"Assistant asked: {verb} — {what} (reason: {p.reason})"
    if k == "conflict":
        return conflict_title(graph.conflict(b["conflict_id"]), graph)
    if k == "staged":
        rec = staging.get(b["staged_id"]) if staging is not None else None
        return f"Couldn't be added automatically \u2014 add it by hand or discard: {staged_label(rec)}"
    if k == "task":
        return task_title(graph.task(b["task_id"]), graph)
    if k == "flag":
        return b.get("_flag_title") or "A high-priority alert needs review"
    return strip_ids(b["text"])


def _pending_add_label(p) -> str:
    c = p.proposed_content or {}
    t = c.get("type")
    attrs = c.get("attributes") or {}
    main = ", ".join(str(v) for v in attrs.values() if v not in (None, "", False))[:80]
    return f"{TYPE_LABEL.get(t, t or 'item')}: {main}" if t else "a new item"
