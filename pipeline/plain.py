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
    text = re.sub(r"\bhistorical\b", "in the past", _ID.sub("", text or ""))
    text = text.replace("in the past (in the past)", "in the past")
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
                reasons += _semantic_reasons(d)
            if not reasons:
                reasons.append("a second read disagreed")
    seen, out = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return "; ".join(out[:3]) or "it needs a person to confirm it"


_V = r"('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|[^\s;)]+)"
_DIFF = re.compile(rf"([\w. -]+?): (?:different|uncertain) \(producer {_V} vs checker {_V}\)")
_MISMATCH = re.compile(rf"([\w.]+): producer {_V} vs checker {_V}")
_NONE = re.compile(rf"free-text details: producer {_V}, checker found none")


def _field(path: str) -> str:
    return FIELD_LABEL.get(path, path.split(".")[-1].replace("_", " "))


def _semantic_reasons(detail: str) -> list[str]:
    """Plain reasons from one semantic-check detail string (values may themselves contain '; ')."""
    out, taken = [], []
    for m in _DIFF.finditer(detail):
        taken.append(m.span())
        what = "" if m.group(1).strip() == "free-text details" else f" the {_field(m.group(1).strip())} as"
        out.append(f"a second read described{what} \u201c{_unq(m.group(3))}\u201d "
                   f"(the note says \u201c{_unq(m.group(2))}\u201d)")
    for m in _NONE.finditer(detail):
        taken.append(m.span())
        out.append(f"a second read found nothing to support \u201c{_unq(m.group(1))}\u201d")
    for m in _MISMATCH.finditer(detail):
        if any(a <= m.start() < b for a, b in taken):
            continue
        if m.group(1) == "problem":
            out.append("a second read linked it to a different complaint")
        else:
            out.append(f"a second read says {_field(m.group(1))}: {_unq(m.group(3))} (the note says {_unq(m.group(2))})")
    if "no equivalence verdict" in detail:
        out.append("the wording comparison didn't finish")
    return out


VALUE_LABEL = {"patient_report": "the patient", "clinician_assessment": "the dentist's assessment",
               "clinician_observation": "the dentist's exam", "test_response": "a test result",
               "clinician_instruction": "the dentist's instruction", "assistant_record": "the assistant's note",
               "historical": "in the past", "current": "now", "planned": "planned", "present": "yes",
               "absent": "not there", "denied": "patient said no", "possible": "possible"}


def _unq(v: str) -> str:
    v = v.strip()
    if v.strip("'\"") in VALUE_LABEL:
        return VALUE_LABEL[v.strip("'\"")]
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
        return bp_title(f, graph)
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


def bp_title(f, graph) -> str:
    """Only the readings over the threshold, where each came from, and whether it is confirmed."""
    from pipeline.dispositions import accepted
    from pipeline.rules import rule_config
    cfg = rule_config()["rules"]["bp_reading"]
    readings = [graph.get(i) for i in f.entity_ids]
    readings = [r for r in readings if r is not None and r.kind == "item" and r.type == "vital_reading"]
    if not readings:
        return "No blood pressure reading was recorded"
    parts, worst = [], 0
    for r in readings:
        sbp, dbp = r.attributes.get("systolic") or 0, r.attributes.get("diastolic") or 0
        level = 2 if (sbp >= cfg["level_b"]["systolic"] or dbp >= cfg["level_b"]["diastolic"]) else \
            1 if (sbp >= cfg["level_a"]["systolic"] or dbp >= cfg["level_a"]["diastolic"]) else 0
        if not level:
            continue
        worst = max(worst, level)
        src = "from the quick note" if all(s.source_type == "quick_note" for s in r.evidence) else "said in the visit"
        conf = "" if accepted(graph, r, graph.pipeline_mode) else ", not confirmed"
        label = f" {r.attributes['label']}" if r.attributes.get("label") else ""
        parts.append(f"{sbp}/{dbp}{label} ({src}{conf})")
    if not parts:
        return clean_message(f.message)
    verb = "are" if len(parts) > 1 else "is"
    return f"{' and '.join(parts)} {verb} {'very high' if worst == 2 else 'elevated'}"


# ---------------------------------------------------------------- review cards

CRITICAL_PATHS = ("tooth", "drug", "dose", "strength", "frequency", "duration", "systolic", "diastolic", "score",
                  "probing", "recession", "attachment", "assertion", "decision", "diagnosis", "certainty",
                  "allergy_status", "medication_status", "prescription_status", "response", "lingering")
TAGS = [("tooth", "Tooth"), ("drug", "Medicine"), ("dose", "Medicine"), ("strength", "Medicine"),
        ("frequency", "Medicine"), ("duration", "Medicine"), ("systolic", "Blood pressure"),
        ("diastolic", "Blood pressure"), ("assertion", "Yes / no"), ("negation", "Yes / no"),
        ("decision", "Decision"), ("diagnosis", "Diagnosis"), ("certainty", "Diagnosis"),
        ("allergy_status", "Allergy"), ("substance", "Allergy"), ("medication_status", "Medicine"),
        ("time_context", "Timing"), ("assertion_source", "Who said it"), ("problem", "Complaint"),
        ("response", "Test result"), ("lingering", "Test result"), ("score", "Number")]


def _failed_paths(e, check_log) -> tuple[list[str], set[str]]:
    """(attribute paths named in failed checks, failing check names)."""
    paths, failing = [], set()
    for check in ("span_valid", "normalization_valid", "semantic_support"):
        rec = check_log.latest(e, check)
        if rec is None or rec["result"] in ("pass", "not_applicable"):
            continue
        failing.add(f"{check}:{rec['result']}")
        for d in rec.get("details") or []:
            for m in _DIFF.finditer(d):
                paths.append(m.group(1).strip())
            for _m in _NONE.finditer(d):
                paths.append("free-text details")
            for m in _MISMATCH.finditer(d):
                paths.append(m.group(1))
            for m in re.finditer(r"([\w.]+) = .+? has no valid", d):
                paths.append(m.group(1))
            if "negation" in d:
                paths.append("negation")
    return paths, failing


def wording_only(e, check_log) -> bool:
    """True when the only disagreement is wording: the second read failed, the quote and value checks passed,
    and nothing changed to a tooth, drug, dose, number, negation, decision, diagnosis or allergy status."""
    paths, failing = _failed_paths(e, check_log)
    if failing != {"semantic_support:fail"} or not paths:
        return False
    for p in paths:
        if p == "free-text details":
            continue
        if any(k in p for k in CRITICAL_PATHS) or p in ("problem", "time_context", "assertion_source"):
            return False
    return True


def check_tag(e, check_log) -> str:
    paths, failing = _failed_paths(e, check_log)
    if any(f.startswith("span_valid:fail") for f in failing):
        return "Quote"
    for p in paths:
        for key, tag in TAGS:
            if key in p:
                return tag
    if any(f.endswith("unconfirmed") for f in failing):
        return "Not confirmed"
    if any(f.endswith("not_assessed_due_to_failure") for f in failing):
        return "Not checked"
    return "Wording"


DENTIST_ONLY = {"allergy": "allergies", "medication": "medications", "prescription": "prescriptions",
                "vital_reading": "blood pressure readings", "diagnosis": "diagnoses", "decision": "decisions",
                "consent_element": "discussion points"}


def dentist_only_hint(e) -> str:
    """Why an assistant can't confirm a critical item, in one line."""
    if e is None:
        return ""
    if e.kind == "problem":
        what = "the chief complaint"
    elif e.kind == "relationship":
        what = "related teeth"
    else:
        what = DENTIST_ONLY.get(e.type) or ("tooth numbers" if e.target.tooth is not None else "this item")
    return f"Only the dentist can confirm {what}."


def short_title(e, graph) -> str:
    if e is None:
        return "Removed item"
    if e.kind == "problem":
        return "Chief complaint"
    if e.kind == "relationship":
        return f"Related tooth #{e.tooth}"
    a = e.attributes
    main = next((str(a[k]) for k in ("drug", "substance", "diagnosis", "test", "observation", "option", "procedure",
                                     "aspect", "description", "text", "decision", "element", "to") if a.get(k)), "")
    if e.type == "vital_reading":
        main = f"{a.get('systolic')}/{a.get('diastolic')}"
    tooth = f" · #{e.target.tooth}" if e.target.tooth else ""
    label = TYPE_LABEL.get(e.type, e.type).capitalize()
    main = main.replace("_", " ")
    return f"{label}{tooth}" + (f" · {main[:40]}" if main else "")


def quotes(entities, sources) -> str:
    """The exact words the entities cite, with who said them."""
    out, seen = [], set()
    for e in entities:
        for s in e.evidence:
            key = (s.source_type, s.source_id, s.text)
            if key in seen:
                continue
            seen.add(key)
            if s.source_type == "transcript":
                u = sources.utterance(s.source_id)
                who = sources.role_of(u.speaker) if u else None
                out.append(f"“{s.text}” — {who or 'speaker'}")
            elif s.source_type == "quick_note":
                out.append(f"Quick note: “{s.text}”")
            elif s.source_type == "human_entry":
                out.append(s.text)
    return "\n".join(out) or "(no words cited)"


def _raw_quotes(raw: dict, sources) -> str:
    out = []
    for q in raw.get("evidence") or []:
        if q.get("source_type") == "transcript":
            u = sources.utterance(q.get("source_id"))
            who = sources.role_of(u.speaker) if u else None
            out.append(f"“{q.get('quote')}” — {who or 'speaker'}")
        elif q.get("source_type") == "quick_note":
            out.append(f"Quick note: “{q.get('quote')}”")
    return "\n".join(out) or "(no words cited)"


def group_blockers(items: list[dict], graph) -> list[list[dict]]:
    """A failed check and the review tasks about the same entity are one card."""
    from pipeline.human import ENTITY_TASKS
    groups: dict = {}
    for i, b in enumerate(items):
        key = b.get("entity_id")
        if not key and b["kind"] == "task":
            t = graph.task(b["task_id"])
            if t.kind in ENTITY_TASKS and t.participants:
                key = t.participants[0].entity_id
        groups.setdefault(key or f"_{i}", []).append(b)
    return list(groups.values())


def build_cards(items, graph, check_log, staging, sources, role: str, flag_by_id: dict) -> list[dict]:
    """Cards for the review page: title, tag, two info boxes, and the choices with the actions each one takes."""
    cards = []
    ask = role == "Assistant"
    for group in group_blockers(items, graph):
        b = next((x for x in group if x["kind"] == "check"), group[0])
        flag_ids = [x["flag_id"] for x in group if x.get("flag_id")]
        task_ids = [x["task_id"] for x in group if x.get("task_id")]
        ask_op = [{"op": "flag", "flag_id": f, "action": "for_dentist"} for f in flag_ids]
        key = "|".join(sorted(str(x.get("entity_id") or x.get("conflict_id") or x.get("task_id") or x.get("section")
                                  or x.get("pending_id") or x.get("staged_id") or x.get("flag_id") or x["kind"])
                              for x in group))
        card = {"key": key, "kind": b["kind"], "hidden": False, "default": None, "options": [], "details": [],
                "comments": _comments([flag_by_id.get(f) for f in flag_ids])}
        k = b["kind"]
        if k == "check" or (k == "task" and graph.task(b["task_id"]).kind in ("check_failure", "registry_issue",
                                                                            "human_override_check")):
            eid = b.get("entity_id") or graph.task(b["task_id"]).participants[0].entity_id
            e = graph.get(eid)
            critical = b.get("critical", True)
            card.update(title=short_title(e, graph), tag=check_tag(e, check_log),
                        left=("Note says", describe(e, graph)), right=("Said in the visit", quotes([e], sources)))
            confirm = [{"op": "confirm", "entity_id": eid, "kind": "dentist_confirmed" if role == "Dentist"
                        else "human_reviewed"}]
            if role == "Dentist" or not critical:
                card["options"].append(("ok", "Looks right", confirm))
            else:
                card["hint"] = dentist_only_hint(e)
            card["options"].append(("remove", "Remove from note", [{"op": "remove", "entity_id": eid}]))
            if ask and ask_op:
                card["options"].append(("ask", "Ask dentist", ask_op))
            if e is not None and wording_only(e, check_log):
                card["hidden"] = True
                card["default"] = "ok" if (role == "Dentist" or not critical) else ("ask" if ask_op else None)
            card["details"] = [f"{x['text']}" for x in group] + [
                f"{c}: {', '.join((check_log.latest(e, c) or {}).get('details') or [])}" for c in
                ("span_valid", "normalization_valid", "semantic_support") if e is not None and check_log.latest(e, c)]
        elif k == "conflict":
            c = graph.conflict(b["conflict_id"])
            parts = [p for p in (graph.get(x.entity_id, x.version) for x in c.participants) if p is not None]
            written = [p for p in parts if p.evidence and all(s.source_type == "quick_note" for s in p.evidence)]
            said = [p for p in parts if p not in written]
            if c.kind == "quick_note_vs_transcript" and written and said:
                left = ("Quick note says", "\n".join(describe(p, graph) for p in written))
                right = ("Said in the visit", quotes(said, sources))
            else:
                ev = c.evidence
                later = c.later_statement or (ev[1] if len(ev) > 1 else None)
                first = next((s for s in ev if later is None or s.source_id != later.source_id), ev[0] if ev else None)
                left = ("First said", f"“{first.text}”" if first else "")
                right = ("Then said", f"“{later.text}”" if later else "")
            title = conflict_title(c, graph).split(" (")[0]
            card.update(title=title, tag="Disagreement", left=left, right=right)
            for j, p in enumerate([p for p in parts if p.status == "active"][:2]):
                label = f"Keep {p.attributes.get('systolic')}/{p.attributes.get('diastolic')}" \
                    if p.kind == "item" and p.type == "vital_reading" else f"Keep {short_title(p, graph)[:28]}"
                card["options"].append((f"keep{j}", label, [{"op": "resolve", "conflict_id": c.id, "action": "select",
                                                             "active_entity_id": p.id}]))
            card["options"].append(("both", "Both are right", [{"op": "resolve", "conflict_id": c.id,
                                                                "action": "keep_both"}]))
            if ask and ask_op:
                card["options"].append(("ask", "Ask dentist", ask_op))
            card["details"] = [b["text"], conflict_title(c, graph)]
        elif k == "section":
            card.update(title=f"{section_title(b['section'])}: not filled in", tag="Section",
                        left=("Note says", "This section is empty because it couldn't be filled in automatically."),
                        right=("In the visit", "Check the conversation for anything that belongs here."))
            card["options"] = [("nd", "Not discussed", [{"op": "section", "section": b["section"],
                                                        "outcome": "not_discussed"}]),
                               ("rv", "I reviewed it", [{"op": "section", "section": b["section"],
                                                        "outcome": "completed"}])]
            card["details"] = [b["text"]]
        elif k == "pending":
            p = next(x for x in graph.pending_changes if x.id == b["pending_id"])
            target = graph.get(p.target_versions[0].entity_id, p.target_versions[0].version) if p.target_versions else None
            verb = {"add": "add", "edit": "change", "remove": "remove", "replace": "replace",
                    "resolve_conflict": "settle a disagreement"}[p.operation]
            card.update(title=f"Assistant asks to {verb}", tag="Needs dentist",
                        left=("Note says", describe(target, graph) if target else "(not in the note)"),
                        right=("Assistant proposes", f"{_pending_add_label(p) if p.operation == 'add' else verb.capitalize()}"
                                                     f" — {p.reason}"))
            card["options"] = [("accept", "Accept", [{"op": "pending", "pending_id": p.id, "accept": True}]),
                               ("reject", "Reject", [{"op": "pending", "pending_id": p.id, "accept": False}])]
            card["details"] = [b["text"]]
        elif k == "staged":
            rec = staging.get(b["staged_id"]) if staging is not None else None
            card.update(title=f"Not added: {staged_label(rec)[:55]}", tag="Not in note",
                        left=("Note says", "(not in the note)"),
                        right=("Said in the visit", _raw_quotes(rec.raw if rec else {}, sources)))
            if rec is not None and rec.entity:
                data = {k2: v for k2, v in rec.entity.items() if k2 not in ("id",)}
                card["options"].append(("add", "Add to note", [{"op": "add_staged", "staged_id": rec.id, "data": data}]))
            card["options"].append(("discard", "Leave it out", [{"op": "discard", "staged_id": b["staged_id"]}]))
            if ask and ask_op:
                card["options"].append(("ask", "Ask dentist", ask_op))
            card["details"] = [b["text"]] + ([f"errors: {'; '.join(rec.errors)}"] if rec else [])
        elif k == "task":
            t = graph.task(b["task_id"])
            dentist_only = t.kind == "stage_failure" and t.created_by_stage == "C" and \
                any(f" {a} " in f" {t.reason} " for a in ("Co", "R2"))
            missed = t.kind in ("omission", "unmatched_contradiction")
            card.update(title=task_title(t, graph).split(":")[0], tag="Possibly missed" if missed else "Check",
                        left=("Note says", "(not in the note)" if missed else task_title(t, graph)),
                        right=("Said in the visit", "\n".join(f"“{s.text}”" for s in t.evidence)
                               or "(nothing quoted)"))
            if role == "Dentist" or not dentist_only:
                card["options"].append(("done", "Not needed" if missed else "Checked", [
                    {"op": "task", "task_id": tid} for tid in task_ids or [t.id]]))
            if ask and ask_op:
                card["options"].append(("ask", "Ask dentist", ask_op))
            card["details"] = [b["text"], t.reason]
        elif k == "flag":
            f = flag_by_id.get(b["flag_id"])
            ents = [e for e in (graph.get(i) for i in (f.entity_ids if f else [])) if e is not None]
            title = flag_title(f, graph) if f else "Alert"
            card.update(title=title.split(": ")[0] if title.startswith(("Allergy alert", "Tooth check")) else title[:60],
                        tag="Safety" if b.get("safety") else "Alert",
                        left=("Note says", describe(ents[0], graph) if ents else title),
                        right=("Said in the visit", quotes(ents, sources) if ents else ""))
            if f is not None and (role == "Dentist" or not f.safety_critical):
                card["options"].append(("dismiss", "Reviewed, OK", [{"op": "flag", "flag_id": f.id, "action": "dismiss"}]))
            if ask and f is not None:
                card["options"].append(("ask", "Ask dentist", [{"op": "flag", "flag_id": f.id, "action": "for_dentist"}]))
            card["details"] = [b["text"], f.message if f else ""]
        else:
            continue
        if card["options"]:
            cards.append(card)
    return cards


DEFAULT_REASON = "Reviewed by the {role} against the transcript"


def _comments(flags) -> list[str]:
    """Comments a reviewer typed when sending an item on (e.g. the assistant's note to the dentist)."""
    out = []
    for f in flags:
        for h in (f.history if f is not None else []):
            if h.reason and not h.reason.startswith("Reviewed by the ") and h.action in ("for_dentist", "comment"):
                line = f"{h.by_role}: {h.reason}"
                if line not in out:
                    out.append(line)
    return out


# ---------------------------------------------------------------- errors in plain words

_ERRORS = [
    (r"no graph yet", "The note hasn't been built yet."),
    (r"stale|being processed|already being", "This visit is still being updated. Wait a moment and try again."),
    (r"only the Dentist|accepted by the Dentist", "Only the dentist can do that."),
    (r"needs a reason|needs an explanation", "Add a short comment saying why, then try again."),
    (r"not an active entity|is not active|no such|no open staged|no pending|no longer applies",
     "That item has already changed. Reload the page to see the latest note."),
    (r"unsupported audio type", "That file type isn't supported. Use a wav, mp3, m4a or flac recording."),
    (r"over 50 MB", "That recording is too large (over 50 MB). Record or upload a shorter one."),
    (r"over 30 minutes", "That recording is too long (over 30 minutes)."),
    (r"no role prefix|no utterances found|has two roles",
     "The transcript needs a speaker at the start of each line, like “DENTIST: …” or “PATIENT: …”."),
    (r"DEEPGRAM_API_KEY|ANTHROPIC_API_KEY|api[_ ]key",
     "Transcription isn't set up on this computer yet. Ask your admin to add the API keys."),
    (r"Deepgram error", "The recording couldn't be transcribed. Check the recording and try again."),
]


def friendly_error(exc: BaseException, doing: str = "do that") -> str:
    """One plain sentence for the person at the screen; never the exception's own text."""
    name, text = type(exc).__name__, str(exc)
    if name == "ApprovalBlocked":
        reasons = getattr(exc, "reasons", [])
        if any("assistant review must be complete" in r for r in reasons):
            return "The assistant needs to finish their review first."
        if any("derived outputs are not current" in r or "no candidate graph" in r for r in reasons):
            return "The note isn't ready yet. Reload the page and try again."
        n = len(reasons)
        return f"Answer the {n} item{'' if n == 1 else 's'} above first."
    if name == "ExportRefused":
        return "The note changed after it was approved, so the dentist needs to approve it again."
    if name == "RealCallsDisabled":
        return ("This computer is in practice mode, so it can't transcribe or write notes from new visits. "
                "Ask your admin to turn on live processing.")
    if name == "RolesNotConfirmed":
        return "Tell us who is speaking first."
    if name == "SessionBusy":
        return "This visit is still being processed. Wait a moment and try again."
    if name == "StructuralError":
        return "That change doesn't fit the note (something required is missing). Check the fields and try again."
    for pattern, message in _ERRORS:
        if re.search(pattern, text, re.I):
            return message
    return f"Couldn't {doing}. Nothing was changed. Try again, or ask your admin to check the technical log."
