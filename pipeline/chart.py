"""Chart-note wording: the same checked graph as the E0 renderer, written the way a dental chart note reads.

This is presentation only. `pipeline.render` stays the canonical, hashed and graded note; nothing here changes it.
The Review page, the PDF and Word exports and "Copy as text" all read from `chart_sections`.
"""
from __future__ import annotations

import re

from pipeline.render import CONSENT_ELEMENTS, INCOMPLETE, _dose_unless_strength, entity_text

SYMPTOM = {"onset": "Onset", "duration": "Duration", "quality": "Quality", "trigger": "Triggered by",
           "lingering": "Lingering", "severity": "Severity", "swelling": "Swelling", "night_pain": "Night pain",
           "spontaneous_pain": "Spontaneous pain", "prior_treatment": "Prior treatment", "location": "Location",
           "biting_pain": "Pain on biting", "other": ""}
XRAY = {"PA": "PA", "BWX": "BWX", "FMX": "Full-mouth X-rays", "pano": "Panoramic X-ray"}
XRAY_ACTION = {"discussed": "discussed, not taken", "planned": "planned", "declined": "declined by patient",
               "not_needed": "not needed"}
ELEMENT = {"risks_discussed": "Risks", "benefits_discussed": "Benefits", "alternatives_discussed": "Alternatives",
           "consequences_of_refusal_discussed": "What happens without treatment",
           "questions_answered": "Patient's questions answered"}
DECISION = {"accepted": "Patient accepted", "declined": "Patient declined", "deferred": "Patient wants to wait",
            "undecided": "Patient undecided", "monitor": "Monitor"}
RELATION = {"control": "comparison tooth", "referred_from": "where the pain is referred from",
            "adjacent_examined": "neighboring tooth", "secondary_problem": "second problem"}
# Spelled out the first time they appear in a note, abbreviated after that.
ABBREVIATIONS = [("BWX", "bitewing X-rays (BWX)"), ("PA", "periapical X-ray (PA)")]


_NO_SUBSTANCE = re.compile(r"\b(none|no known|nkda|nka|no allerg\w*|denies|n/?a)\b", re.I)


def no_substance(wording) -> bool:
    """True when an allergy's verbatim wording names nothing ("Allergy: none", "NKDA"), so it is no substance."""
    text = re.sub(r"^\s*allerg(?:y|ies)\s*[:\-]?\s*", "", wording or "", flags=re.I).strip()
    return not text or bool(_NO_SUBSTANCE.search(text))


def _cap(text: str) -> str:
    text = (text or "").strip()
    return text[:1].upper() + text[1:] if text else text


def _list(*parts) -> str:
    return ", ".join(str(p).strip() for p in parts if p not in (None, "", False, []))


def _tooth(e) -> str:
    if e.target.tooth is None:
        return ""
    return f"#{e.target.tooth}" + (f" {e.target.surface}" if e.target.surface else "")


def _with_tooth(text: str, e) -> str:
    """Add the tooth unless the words already name it."""
    tooth = _tooth(e)
    return text if not tooth or re.search(rf"#\s?{e.target.tooth}\b", text) else f"{text} {tooth}"


def _relation(e) -> str:
    rel = e.target_relation
    if not rel or rel in ("matches_target", "unknown"):
        return ""  # an unexplained other tooth is raised as a tooth-check alert, not written into the note
    return f" ({RELATION.get(rel, rel.replace('_', ' '))})"


def _negated(e) -> bool:
    return e.assertion in ("absent", "denied")


def _symptom(e) -> str:
    a = e.attributes
    label, value = SYMPTOM.get(a.get("aspect") or "other", ""), (a.get("value") or "").strip()
    score = a.get("score")
    if a.get("aspect") == "severity" and score is not None:
        value = _list(f"{score:g}/10", value)
    elif score is not None and f"{score:g}" not in value:
        value = _list(value, f"{score:g}")
    if _negated(e):
        if value.lower().startswith(("no ", "denies", "none", "not ")):
            return _cap(value)
        return "No " + (value or label.lower() or "symptom") if not label or not value else \
            f"No {label.lower()} ({value})"
    if e.assertion == "possible":
        label = f"Possible {label.lower()}".strip()
    if not label:
        return _cap(value)
    if not value or value.lower() in ("yes", "present", label.lower()):
        return label
    return f"{label}: {value}"


def _finding(e) -> str:
    a = e.attributes
    result = {"present": "positive", "absent": "negative", "uncertain": "unclear"}.get(a.get("response"))
    linger = {True: "lingering", False: "not lingering"}.get(a.get("lingering"))
    seconds = f"{a['duration_s']:g} seconds" if a.get("duration_s") is not None else None
    what = a.get("test") or a.get("observation") or ""
    if a.get("test") and a.get("observation"):
        what = f"{a['test']} ({a['observation']})"
    if a.get("test") and result:
        what = f"{what} test {result}" if " test" not in what.lower() and len(what.split()) <= 2 else f"{what}: {result}"
    elif result and not a.get("test"):
        what = _list(what, result)
    body = _list(what, a.get("intensity"), linger, seconds)
    if a.get("result_description"):
        body = f"{body} — {a['result_description']}" if body else a["result_description"]
    if _negated(e) and not body.lower().startswith(("no ", "not ", "none")) and not result:
        body = f"No {body}"
    where = _tooth(e) + _relation(e)
    return f"{where}: {body}" if where else _cap(body)


def chart_line(e, graph) -> str:
    """One entity as a chart-note line."""
    if e.kind == "problem":
        tooth = f"#{e.clinical_target.tooth}" if e.clinical_target.tooth else e.clinical_target.free_text
        points = e.complaint_location.free_text or (f"#{e.complaint_location.tooth}" if e.complaint_location.tooth else "")
        text = _cap(e.complaint_text or "Not stated")
        if e.role != "chief":
            text = f"Also: {text[:1].lower() + text[1:]}"
        text += f" \u2014 tooth {tooth}" if tooth else " \u2014 no tooth identified yet"
        if points and points.lower() not in text.lower():
            text += f" (patient points to {points})"
        return text
    if e.kind == "relationship":
        return f"#{e.tooth}: {e.relation_kind.replace('_', ' ')}" + (f" — {e.note}" if e.note else "")
    a, t = e.attributes, e.type
    possible = "Possible " if e.assertion == "possible" else ""
    if t == "symptom":
        text = _symptom(e)
    elif t == "finding":
        text = _finding(e)
    elif t == "history_change":
        text = _cap(a.get("description") or "No changes reported")
        if _negated(e) and not text.lower().startswith(("no ", "none", "denies", "not ")):
            text = f"No {text[:1].lower() + text[1:]}"
    elif t == "medication":
        status = {"discontinued": "stopped", "historical": "in the past", "unknown": "status not stated"}.get(
            a.get("medication_status"))
        text = _list(f"{_cap(a.get('drug') or a.get('original_wording') or 'Medication')} {a.get('strength') or ''}".strip(),
                     _dose_unless_strength(a), a.get("route"), a.get("frequency"))
        text = ("No " + text[:1].lower() + text[1:] if _negated(e) else possible + text) + (f" ({status})" if status else "")
    elif t == "allergy":
        substance = a.get("substance") or (None if no_substance(a.get("original_wording")) else a["original_wording"])
        if a.get("allergy_status") == "denied" or (_negated(e) and not substance):
            text = f"No allergy to {substance}" if substance else "No known allergies"
        else:
            status = {"uncertain": "patient not sure", "disputed": "disputed",
                      "reported_resolved": "patient reports it has resolved"}.get(a.get("allergy_status"))
            text = f"{possible}Allergy: {substance or 'not specified'}" + \
                   (f" ({a['reaction']})" if a.get("reaction") else "") + (f" — {status}" if status else "")
    elif t == "vital_reading":
        text = f"BP {a.get('systolic')}/{a.get('diastolic')} mmHg" + (f" ({a['label']})" if a.get("label") else "")
    elif t == "perio_measurement":
        text = _list(f"{_tooth(e)} {a.get('site') or ''}".strip(),
                     a.get("probing_depth_mm") is not None and f"probing depth {a['probing_depth_mm']:g} mm",
                     a.get("bleeding") is not None and ("bleeding on probing" if a["bleeding"] else "no bleeding"),
                     a.get("recession_mm") is not None and f"recession {a['recession_mm']:g} mm",
                     a.get("attachment_loss_mm") is not None and f"attachment loss {a['attachment_loss_mm']:g} mm")
    elif t == "radiograph":
        head = f"{XRAY.get(a.get('type'), 'X-ray')} {_tooth(e) or a.get('target') or ''}".strip() + _relation(e)
        action = XRAY_ACTION.get(a.get("action"))
        detail = _list(a.get("finding"),
                       a.get("bone_loss") is not None and ("bone loss" if a["bone_loss"] else "no bone loss"))
        text = head + (f" ({action})" if action else "") + (f": {detail}" if detail else "")
    elif t == "diagnosis":
        hedge = "Possible " if (a.get("certainty") == "possible" or possible) else ""
        name = a.get("diagnosis") or "diagnosis not stated"
        text = _with_tooth(hedge + name if hedge else _cap(name), e) + _relation(e)
    elif t == "option_discussed":
        rec = {True: "recommended", False: "not recommended"}.get(a.get("recommended_by_clinician"))
        text = _with_tooth(_cap(a.get("option") or "Option"), e) + _relation(e) + (f" ({rec})" if rec else "")
        text = "; ".join(p for p in (text, a.get("risks") and f"risks: {a['risks']}",
                                     a.get("benefits") and f"benefits: {a['benefits']}") if p)
    elif t == "decision":
        opt = graph.get(a["option_id"]) if a.get("option_id") else None
        text = DECISION.get(a.get("decision"), "Patient undecided")
        if opt is not None:
            text += f": {opt.attributes.get('option')}"
        if a.get("reason"):
            text += f" — {a['reason']}"
    elif t == "consent_element":
        text = f"{ELEMENT.get(a.get('element'), 'Discussed')} discussed" + (f": {a['content']}" if a.get("content") else "")
    elif t == "treatment_today":
        text = _with_tooth(_cap(a.get("procedure") or "Treatment"), e) + _relation(e)
    elif t == "prescription":
        status = {"discussed_not_prescribed": "discussed, not prescribed", "continuing": "continuing"}.get(
            a.get("prescription_status"))
        days = a.get("duration_days")
        text = _list(f"{_cap(a.get('drug') or a.get('original_wording') or 'Medication')} {a.get('strength') or ''}".strip(),
                     _dose_unless_strength(a), a.get("route"), a.get("frequency_code"),
                     days is not None and f"for {days} day{'' if days == 1 else 's'}") + (f" ({status})" if status else "")
    elif t == "referral":
        text = f"Referred to {a.get('to') or 'a specialist'}" + (f" for {a['purpose']}" if a.get("purpose") else "")
    elif t == "next_visit":
        text = _list(_with_tooth(_cap(a.get("procedure") or "Follow-up"), e) + _relation(e), a.get("timing"))
    elif t == "instruction":
        text = _cap(a.get("text") or "")
    else:
        text = entity_text(e, graph)[0]
    if e.time_context == "historical" and "in the past" not in text and t != "next_visit":
        text += " (in the past)"
    return text


def expand_abbreviations(lines: list[dict]) -> None:
    """Spell out BWX and PA the first time each appears in the note (in place)."""
    for short, full in ABBREVIATIONS:
        pattern = re.compile(rf"\b{short}\b(?!\))")
        for line in lines:
            if pattern.search(line["text"]):
                line["text"] = pattern.sub(full, line["text"], count=1)
                line["text"] = line["text"][:1].upper() + line["text"][1:]
                break


def chart_sections(note: dict, graph) -> dict:
    """The canonical note regrouped for reading: sections with lines, sections that need attention, and the
    titles of sections where nothing was said (shown as one 'Not discussed: …' line)."""
    sections, not_discussed, all_lines = [], [], []
    for sec in note.get("sections", []):
        if sec["id"] == "visit":
            continue
        lines = []
        for line in sec["lines"]:
            e = graph.get(line["entity_id"]) if line.get("entity_id") else None
            if e is None:
                continue  # 'not documented' filler lines are summarized below
            lines.append({"entity_id": e.id, "text": chart_line(e, graph), "owner": e.owner})
        incomplete = sec.get("status_line") == INCOMPLETE
        if sec["id"] == "discussion_elements" and lines:
            present = {graph.get(l["entity_id"]).attributes.get("element") for l in lines}
            missing = [ELEMENT[el].lower() for el in CONSENT_ELEMENTS if el not in present]
            if missing:
                lines.append({"entity_id": None, "text": "Not documented: " + ", ".join(missing), "owner": None})
        if not lines and not incomplete:
            not_discussed.append(sec["title"])
            continue
        sections.append({"id": sec["id"], "title": sec["title"], "lines": lines, "incomplete": incomplete})
        all_lines += lines
    expand_abbreviations(all_lines)
    return {"sections": sections, "not_discussed": not_discussed}


def chart_text(note: dict, graph, header: list[str] | None = None, footer: list[str] | None = None) -> str:
    """The whole chart note as plain text (for 'Copy as text' and pasting into charting software)."""
    chart = chart_sections(note, graph)
    out = list(header or [])
    for sec in chart["sections"]:
        out += ["", sec["title"].upper()]
        if sec["incomplete"]:
            out.append("  (could not be filled in automatically)")
        out += [f"  - {line['text']}" for line in sec["lines"]]
    if chart["not_discussed"]:
        out += ["", "Not discussed: " + ", ".join(chart["not_discussed"])]
    if footer:
        out += [""] + footer
    return "\n".join(out).strip() + "\n"
