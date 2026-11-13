"""E0 deterministic note renderer: one line per entity, from one frozen graph version."""
from __future__ import annotations

from pipeline.dispositions import section_reviewed
from pipeline.storage import hash_obj
from pipeline.template import template, template_hash

RENDERER_VERSION = "1"
NOT_DOCUMENTED = "Not documented in the provided sources."
INCOMPLETE = "PROCESSING INCOMPLETE — review the transcript."
NOT_DISCUSSED = "Not discussed — confirmed by reviewer."
CONSENT_ELEMENTS = ["risks_discussed", "benefits_discussed", "alternatives_discussed",
                    "consequences_of_refusal_discussed", "questions_answered"]


class RenderError(RuntimeError):
    pass


def render_config_hash() -> str:
    return hash_obj({"template": template_hash(), "renderer": RENDERER_VERSION})


def verification_label(mode: str) -> str:
    return "span-checked (meaning not checked)" if mode == "baseline" else "span-checked and meaning-checked"


def check_marker(entity, mode: str) -> str:
    """The entity's actual check results; never claims more than was achieved."""
    if entity.is_human:
        return "human entry"
    c = entity.checks
    sym = {"pass": "✓", "fail": "✗", "unconfirmed": "?", "not_run": "…", "not_applicable": "–",
           "not_assessed_due_to_failure": "⏸"}
    parts = [f"span{sym[c.span_valid]}", f"norm{sym[c.normalization_valid]}"]
    if mode == "baseline":
        parts.append("meaning not checked")
    elif c.semantic_support == "unconfirmed":
        parts.append("meaning? not confirmed from evidence")
    else:
        parts.append(f"meaning{sym[c.semantic_support]}")
    return " ".join(parts)


def _t(tooth) -> str:
    return f"#{tooth}" if tooth is not None else ""


def _join(*parts) -> str:
    return "; ".join(str(p) for p in parts if p is not None and p is not False and p not in ("", []))


def _dose_unless_strength(a):
    """A dose equal to the strength (e.g. both '600 mg') is shown once."""
    dose = a.get("dose")
    return None if dose and a.get("strength") and dose.strip().lower() == a["strength"].strip().lower() else dose


def _symptom_score(a) -> str:
    """Only a severity score is out of 10; other numbers (e.g. lingering seconds) aren't."""
    n = a.get("score")
    if n is None:
        return ""
    if a.get("aspect") == "severity":
        return f" ({n:g}/10)"
    return "" if f"{n:g}" in (a.get("value") or "") else f" ({n:g})"


def _assert_prefix(e) -> str:
    first = " ".join(str(v) for v in e.attributes.values() if isinstance(v, str))[:12].lower()
    if e.assertion in ("absent", "denied") and first.startswith(("no ", "denies", "not ", "none")):
        return ""
    return {"absent": "No ", "denied": "Denies ", "possible": "Possible ", "unintelligible": "Unintelligible: "}.get(
        e.assertion, "")


def entity_text(e, graph) -> tuple[str, dict]:
    """Line text plus the attributes it renders (scored separately by the Grader)."""
    if e.kind == "problem":
        shown = {"role": e.role, "complaint_text": e.complaint_text,
                 "complaint_location": e.complaint_location.free_text or _t(e.complaint_location.tooth),
                 "clinical_target": _t(e.clinical_target.tooth) or e.clinical_target.free_text}
        return (f"{'Chief' if e.role == 'chief' else 'Secondary'} complaint: {e.complaint_text or '—'} "
                f"(patient-reported location: {shown['complaint_location'] or 'not stated'}; "
                f"clinical target: {shown['clinical_target'] or 'not identified'})"), shown
    if e.kind == "relationship":
        shown = {"tooth": _t(e.tooth), "relation_kind": e.relation_kind, "note": e.note}
        return f"Related tooth {_t(e.tooth)}: {e.relation_kind.replace('_', ' ')}" + (f" — {e.note}" if e.note else ""), shown
    a = e.attributes
    shown: dict = {}

    def show(**kw):
        shown.update({k: v for k, v in kw.items() if v not in (None, "")})

    tooth = _t(e.target.tooth)
    surface = e.target.surface
    rel = f" [{e.target_relation.replace('_', ' ')}]" if e.target_relation and e.target_relation != "matches_target" else ""
    t = e.type
    pre = _assert_prefix(e)
    if t == "history_change":
        show(description=a["description"])
        text = f"{pre}{a['description'] or 'history change'}"
    elif t == "medication":
        show(drug=a["drug"] or a["original_wording"], strength=a["strength"], dose=a["dose"], route=a["route"],
             frequency=a["frequency"], medication_status=a["medication_status"])
        text = pre + _join(f"{shown.get('drug', '?')} {a['strength'] or ''}".strip(), _dose_unless_strength(a),
                           a["route"], a["frequency"], (a["medication_status"] or "").replace("_", " "))
    elif t == "allergy":
        show(substance=a["substance"] or a["original_wording"], reaction=a["reaction"], allergy_status=a["allergy_status"])
        if a["allergy_status"] == "denied" and not a["substance"]:
            text = "Denies allergies"
        else:
            text = _join(f"Allergy: {shown.get('substance', 'unspecified')}", a["reaction"] and f"reaction: {a['reaction']}",
                         (a["allergy_status"] or "").replace("_", " "))
    elif t == "vital_reading":
        show(systolic=a["systolic"], diastolic=a["diastolic"], label=a["label"])
        text = f"BP {a['systolic']}/{a['diastolic']} mmHg" + (f" ({a['label']})" if a["label"] else "")
    elif t == "symptom":
        show(aspect=a["aspect"], value=a["value"], score=a["score"])
        text = f"{pre}{(a['aspect'] or 'symptom').replace('_', ' ')}: {a['value'] or ''}{_symptom_score(a)}".strip()
    elif t == "finding":
        show(tooth=tooth, surface=surface, test=a["test"], observation=a["observation"], response=a["response"],
             result_description=a["result_description"], intensity=a["intensity"], lingering=a["lingering"],
             duration_s=a["duration_s"])
        resp = {"present": "positive/felt", "absent": "negative/no response", "uncertain": "uncertain"}.get(a["response"])
        ling = {True: "lingering", False: "not lingering"}.get(a["lingering"])
        dur = f"{a['duration_s']:g} s" if a["duration_s"] is not None else None
        text = pre + _join(f"{tooth}{(' ' + surface) if surface else ''}{rel}".strip() or None,
                           a["test"] or a["observation"], resp, a["intensity"], ling, dur, a["result_description"])
    elif t == "perio_measurement":
        show(tooth=tooth, site=a["site"], probing_depth_mm=a["probing_depth_mm"], bleeding=a["bleeding"],
             recession_mm=a["recession_mm"], attachment_loss_mm=a["attachment_loss_mm"])
        text = _join(f"{tooth} {a['site'] or ''}".strip(), a["probing_depth_mm"] is not None and f"PD {a['probing_depth_mm']:g} mm",
                     a["bleeding"] is not None and ("BOP+" if a["bleeding"] else "BOP−"),
                     a["recession_mm"] is not None and f"recession {a['recession_mm']:g} mm",
                     a["attachment_loss_mm"] is not None and f"CAL {a['attachment_loss_mm']:g} mm")
    elif t == "radiograph":
        show(type=a["type"], tooth=tooth, target=a["target"], action=a["action"], finding=a["finding"],
             bone_loss=a["bone_loss"])
        text = _join(f"{a['type'] or 'Radiograph'} {tooth or a['target'] or ''}{rel}".strip(),
                     (a["action"] or "").replace("_", " "), a["finding"],
                     a["bone_loss"] is not None and ("bone loss" if a["bone_loss"] else "no bone loss"))
    elif t == "diagnosis":
        show(diagnosis=a["diagnosis"], tooth=tooth, certainty=a["certainty"])
        text = f"{'Possible: ' if a['certainty'] == 'possible' else 'Definite: ' if a['certainty'] == 'definite' else ''}" \
               f"{a['diagnosis']} {tooth}{rel}".strip()
    elif t == "option_discussed":
        show(option=a["option"], tooth=tooth, risks=a["risks"], benefits=a["benefits"],
             recommended_by_clinician=a["recommended_by_clinician"])
        rec = {True: "recommended by dentist", False: "not recommended"}.get(a["recommended_by_clinician"])
        text = _join(f"{a['option']} {tooth}{rel}".strip(), rec, a["risks"] and f"risks: {a['risks']}",
                     a["benefits"] and f"benefits: {a['benefits']}")
    elif t == "decision":
        opt = graph.get(a["option_id"]) if a.get("option_id") else None
        show(decision=a["decision"], option=opt.attributes.get("option") if opt else None, reason=a["reason"])
        text = _join(f"{(a['decision'] or 'undecided').capitalize()}" +
                     (f": {opt.attributes.get('option')}" if opt else " (no linked option)"),
                     a["reason"] and f"reason: {a['reason']}")
    elif t == "consent_element":
        show(element=a["element"], content=a["content"])
        text = f"{(a['element'] or 'element').replace('_', ' ').capitalize()}: documented" + \
               (f" — {a['content']}" if a["content"] else "")
    elif t == "treatment_today":
        show(procedure=a["procedure"], tooth=tooth)
        text = f"{a['procedure']} {tooth}{rel}".strip()
    elif t == "prescription":
        show(drug=a["drug"] or a["original_wording"], strength=a["strength"], dose=a["dose"], route=a["route"],
             frequency_code=a["frequency_code"], duration_days=a["duration_days"], as_needed=a["as_needed"],
             prescription_status=a["prescription_status"])
        text = _join(f"{shown.get('drug', '?')} {a['strength'] or ''}".strip(), _dose_unless_strength(a), a["route"],
                     a["frequency_code"],
                     a["duration_days"] is not None and f"{a['duration_days']} days",
                     (a["prescription_status"] or "").replace("_", " "))
    elif t == "referral":
        show(to=a["to"], purpose=a["purpose"])
        text = _join(f"To {a['to']}", a["purpose"])
    elif t == "next_visit":
        show(procedure=a["procedure"], tooth=tooth, timing=a["timing"])
        text = _join(f"{a['procedure']} {tooth}{rel}".strip(), a["timing"])
    elif t == "instruction":
        show(text=a["text"])
        text = a["text"] or ""
    else:
        text = t
    if e.time_context != "current" and t not in ("next_visit",):
        text += f" ({e.time_context})"
        shown["time_context"] = e.time_context
    shown["assertion"] = e.assertion
    return text, shown


def _section_entities(section: dict, graph) -> list:
    if section.get("entity_kinds"):
        return [e for e in graph.active() if e.kind in section["entity_kinds"]]
    return [e for e in graph.active("item") if e.type in section["item_types"]]


def _visit_lines(sources) -> list[str]:
    vm = sources.visit_meta
    return [f"Date: {vm.date or 'not recorded'}; provider: {vm.provider or 'not recorded'}; assistant: "
            f"{vm.assistant or 'not recorded'}; visit type: {vm.visit_type}"]


def _conflict_notes(graph) -> dict[str, list[str]]:
    """keep_both resolutions render their explanation next to the participants."""
    out: dict[str, list[str]] = {}
    for c in graph.conflicts:
        if c.status == "resolved" and c.resolution and c.resolution.action == "keep_both":
            for p in c.participants:
                out.setdefault(p.entity_id, []).append(f"both kept: {c.resolution.explanation}")
    return out


def render_note(graph, sources, mode: str) -> dict:
    if graph.stale or any(e.status == "stale" for e in graph.active()):
        raise RenderError("stale graph cannot be rendered")
    notes = _conflict_notes(graph)
    sections = []
    for sec in template()["sections"]:
        if sec["id"] == "visit":
            sections.append({"id": "visit", "title": sec["title"], "status": "completed",
                             "lines": [{"entity_id": None, "text": t, "attributes": {}, "marker": "visit metadata"}
                                       for t in _visit_lines(sources)]})
            continue
        rec = next((s for s in graph.section_records if s.section == sec["id"]), None)
        reviewed = section_reviewed(graph, sec["id"])
        ents = _section_entities(sec, graph)
        if sec["id"] == "clinical_findings":
            ents.sort(key=lambda e: (e.target.tooth or 99, e.id))
        lines = []
        for e in ents:
            text, shown = entity_text(e, graph)
            if notes.get(e.id):
                text += " (" + "; ".join(notes[e.id]) + ")"
            lines.append({"entity_id": e.id, "version": e.version, "text": text, "attributes": shown,
                          "marker": check_marker(e, mode), "owner": e.owner})
        status_line = None
        if rec is not None and rec.status in ("failed", "not_run") and not (reviewed and reviewed.outcome == "completed"):
            status_line = NOT_DISCUSSED if (reviewed and reviewed.outcome == "not_discussed") else INCOMPLETE
        elif not lines:
            status_line = NOT_DISCUSSED if (reviewed and reviewed.outcome == "not_discussed") else NOT_DOCUMENTED
        if sec["id"] == "discussion_elements" and lines:
            present = {e.attributes.get("element") for e in ents}
            for el in CONSENT_ELEMENTS:
                if el not in present:
                    lines.append({"entity_id": None, "text": f"{el.replace('_', ' ').capitalize()}: not documented in "
                                                             f"the provided sources", "attributes": {}, "marker": ""})
        sections.append({"id": sec["id"], "title": sec["title"], "status": rec.status if rec else "completed",
                         "status_line": status_line, "lines": lines})
    note = {"graph_version": graph.version, "mode": mode, "verification_level": verification_label(mode),
            "render_config_hash": render_config_hash(), "sections": sections}
    note["note_hash"] = hash_obj({k: v for k, v in note.items() if k != "note_hash"})
    return note


def note_markdown(note: dict) -> str:
    out = [f"# Limited exam note (graph v{note['graph_version']}, {note['verification_level']})", ""]
    for s in note["sections"]:
        out.append(f"## {s['title']}")
        if s.get("status_line"):
            out.append(s["status_line"])
        for line in s["lines"]:
            ref = f"  [{line['entity_id']} · {line['marker']}]" if line.get("entity_id") else ""
            out.append(f"- {line['text']}{ref}")
        out.append("")
    return "\n".join(out)
