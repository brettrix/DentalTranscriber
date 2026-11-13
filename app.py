"""Streamlit UI (section 13), written for a dental assistant: plain language first, technical details collapsed."""
from __future__ import annotations

import html
import json
import tempfile
import typing
from datetime import datetime
from pathlib import Path

import streamlit as st

from pipeline import approval, human, plain
from pipeline.dispositions import accepted
from pipeline.flags import flag_state, session_flag_actions
from pipeline.graph import load_graph
from pipeline.linker import session_staging
from pipeline.orchestrator import RolesNotConfirmed, derive, load_latest, run_pipeline
from pipeline.overlays import confirm_roles, load_sources
from pipeline.stage_runs import session_stage_log
from pipeline.storage import ROOT, Session, SessionBusy, list_sessions, read_json
from pipeline.trace import read_traces
from pipeline.transcribe import transcribe_audio, transcribe_text, write_quick_notes, write_visit_meta
from pipeline.validate import StructuralError
from pipeline.verify import session_check_log
from schemas.entities import ATTRIBUTE_MODELS, ITEM_SCOPES, Item, is_critical
from schemas.flags import Flag

BANNER = "Prototype — test data only. Do not use with real patient information."
NEW = "__new__"
PAGES = ["Start", "Review", "Speaker roles", "Technical log"]
STATE_LABEL = {"draft": "Draft — not reviewed yet",
               "assistant_review_complete": "Assistant review done — waiting for the dentist",
               "dentist_approved": "Approved by the dentist", "exported": "Approved and exported"}

st.set_page_config(page_title="Dental Scribe (prototype)", layout="wide")

# Navigation requested by an action in the previous run (a widget's value can't change after it is drawn).
for _key in ("page", "sid"):
    if f"next_{_key}" in st.session_state:
        st.session_state[_key] = st.session_state.pop(f"next_{_key}")


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def go(page: str, sid: str | None = None):
    st.session_state["next_page"] = page
    if sid:
        st.session_state["next_sid"] = sid
    st.rerun()


def session_label(sid: str) -> str:
    if sid == NEW:
        return "(new visit)"
    s = Session(sid)
    m = s.meta()
    created = m.get("created")
    when = datetime.fromisoformat(created).astimezone().strftime("%b %d %H:%M") if created else "?"
    return f"{m.get('case') or 'Visit'} · {when} · {m.get('pipeline_mode', '?')}"


def session_caption(s) -> str:
    m = s.meta()
    vm = read_json(s.path("sources", "visit_meta.json"), {}) or {}
    created = m.get("created")
    when = datetime.fromisoformat(created).astimezone().strftime("%Y-%m-%d %H:%M") if created else "?"
    return (f"{m.get('case') or 'Visit'} · processed {when} · {m.get('pipeline_mode', '?')} mode · "
            f"visit date {vm.get('date') or '—'} · {vm.get('provider') or ''}")


# ---------------------------------------------------------------- sidebar: role and session

role = st.sidebar.selectbox("Your role (Prototype: no real login)", ["Assistant", "Dentist"])
sessions = list_sessions()  # newest first
ids = [NEW] + [s.id for s in sessions]
if st.session_state.get("sid") not in ids:
    st.session_state["sid"] = ids[1] if len(ids) > 1 else NEW
sid = st.sidebar.selectbox("Visit", ids, key="sid", format_func=session_label)
session = Session(sid) if sid != NEW else None
meta = session.meta() if session else {}
if session is not None:
    st.sidebar.caption(session_caption(session))
st.error(f"{BANNER}  ·  Mode: {meta.get('pipeline_mode', '—')}  ·  Rules: {meta.get('rule_mode', '—')}")
page = st.radio("Page", PAGES, key="page", horizontal=True, label_visibility="collapsed")


def guarded(fn, *args, **kw):
    try:
        out = fn(*args, **kw)
        st.session_state["flash"] = "Saved."
        return out if out is not None else True
    except (human.HumanActionError, StructuralError, approval.ApprovalBlocked, approval.ExportRefused,
            SessionBusy, RolesNotConfirmed, ValueError) as exc:
        st.session_state["flash_error"] = f"Couldn't do that: {plain.strip_ids(str(exc))}"
        return None


if st.session_state.get("flash"):
    st.success(st.session_state.pop("flash"))
if st.session_state.get("flash_error"):
    st.error(st.session_state.pop("flash_error"))


def _act(label, key, fn, *args, **kw):
    if st.button(label, key=key):
        guarded(fn, *args, **kw)
        st.rerun()


# ---------------------------------------------------------------- Start

def start_page():
    st.subheader("New visit")
    c1, c2, c3 = st.columns(3)
    date = c1.text_input("Visit date", datetime.now().strftime("%Y-%m-%d"))
    provider = c2.text_input("Dentist", "Dr. Hale")
    assistant = c3.text_input("Assistant", "")
    mode = st.radio("Pipeline mode", ["baseline", "team"], horizontal=True,
                    help="baseline: one extractor, quote-checked. team: split extractors plus meaning checks.")
    rule_mode = st.radio("Rule mode", ["synthetic_demo", "office"], horizontal=True)
    source = st.radio("Input", ["Paste transcript", "Upload audio", "Test case"], horizontal=True)
    quick = st.text_area("Quick notes (one per line)", height=100)
    transcript, audio, case_dir = None, None, None
    if source == "Paste transcript":
        transcript = st.text_area("Transcript (lines like 'DENTIST: …', 'PATIENT: …')", height=200)
    elif source == "Upload audio":
        audio = st.file_uploader("Audio (wav, mp3, m4a, flac; up to 50 MB and 30 minutes)",
                                 type=["wav", "mp3", "m4a", "flac"])
    else:
        cases = sorted(p for p in (ROOT / "eval" / "cases").iterdir() if p.is_dir())
        chosen = st.selectbox("Test case", [p.name for p in cases])
        case_dir = next((p for p in cases if p.name == chosen), None)
    if st.button("Process", type="primary"):
        s = Session.create(case=case_dir.name if case_dir else None, pipeline_mode=mode, rule_mode=rule_mode)
        write_visit_meta(s, date=date, provider=provider, assistant=assistant or None)
        try:
            if case_dir is not None:
                transcribe_text(s, (case_dir / "transcript.txt").read_text("utf-8"))
                quick = quick or (case_dir / "quick_notes.txt").read_text("utf-8")
            elif audio is not None:
                tmp = Path(tempfile.mkdtemp()) / audio.name
                tmp.write_bytes(audio.getvalue())
                transcribe_audio(s, tmp)
            else:
                transcribe_text(s, transcript or "")
            write_quick_notes(s, quick)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Couldn't read the recording or transcript: {exc}")
            return
        if not load_sources(s).roles.confirmed:
            st.session_state["flash"] = "Recording loaded. Confirm who is speaking, then process."
            go("Speaker roles", s.id)
        with st.spinner("Processing the visit…"):
            guarded(run_pipeline, s, mode=mode, rule_mode=rule_mode)
        go("Review", s.id)


# ---------------------------------------------------------------- Speaker roles (audio)

def roles_page():
    if session is None:
        st.info("Pick a visit in the sidebar.")
        return
    src = load_sources(session)
    st.write("Who is speaking? Several voices can share a role (for example, two dentists).")
    mapping = {}
    opts = ["Dentist", "Assistant", "Patient", "Other"]
    for spk in sorted({u.speaker for u in src.utterances.utterances}):
        sample = [u.text for u in src.utterances.utterances if u.speaker == spk][:3]
        st.markdown(f"**Voice {esc(spk[1:])}**: " + " / ".join(f"“{esc(t)}”" for t in sample))
        current = src.roles.entries.get(spk).role if spk in src.roles.entries else "Other"
        mapping[spk] = st.selectbox(f"Role for voice {spk[1:]}", opts, index=opts.index(current), key=f"r{spk}")
    if st.button("Confirm speakers and process", type="primary"):
        confirm_roles(session, mapping, by=role)
        with st.spinner("Processing the visit…"):
            guarded(run_pipeline, session)
        go("Review", session.id)


# ---------------------------------------------------------------- field form

def _type_options(annotation):
    args = [a for a in typing.get_args(annotation) if a is not type(None)]
    lit = annotation if typing.get_origin(annotation) is typing.Literal else \
        next((a for a in args if typing.get_origin(a) is typing.Literal), None)
    if lit is not None:
        return "choice", list(typing.get_args(lit))
    if bool in args:
        return "bool", None
    if int in args or float in args:
        return "number", None
    return "text", None


def field_form(e, key: str) -> dict:
    """Plain inputs for an entity's clinical fields; returns only the fields the user changed."""
    changes: dict = {}
    if e.kind == "item":
        tooth = st.text_input("Tooth number (1–32, blank if none)",
                              "" if e.target.tooth is None else str(e.target.tooth), key=f"f_{key}_tooth")
        new_tooth = int(tooth) if tooth.strip().isdigit() else None
        if new_tooth != e.target.tooth:
            changes["target"] = {"tooth": new_tooth}
        attrs = {}
        for name, info in ATTRIBUTE_MODELS[e.type].model_fields.items():
            if name in ("option_id", "decision_id", "link", "option_link", "sequence", "unit"):
                continue
            cur = e.attributes.get(name)
            kind, opts = _type_options(info.annotation)
            label = name.replace("_", " ")
            if kind == "choice":
                choices = ["(not stated)"] + opts
                v = st.selectbox(label, choices, index=choices.index(cur) if cur in choices else 0,
                                 key=f"f_{key}_{name}")
                new = None if v == "(not stated)" else v
            elif kind == "bool":
                choices = ["(not stated)", "yes", "no"]
                v = st.selectbox(label, choices, index={None: 0, True: 1, False: 2}[cur], key=f"f_{key}_{name}")
                new = {"(not stated)": None, "yes": True, "no": False}[v]
            else:
                v = st.text_input(label, "" if cur is None else (f"{cur:g}" if isinstance(cur, float) else str(cur)),
                                  key=f"f_{key}_{name}")
                new = v.strip() or None
                if kind == "number" and new is not None:
                    try:
                        new = float(new) if "." in new else int(new)
                    except ValueError:
                        new = cur
            if new != cur:
                attrs[name] = new
        if attrs:
            changes["attributes"] = attrs
        opts = ["present", "absent", "denied", "possible", "unintelligible"]
        a = st.selectbox("Stated as", opts, index=opts.index(e.assertion), key=f"f_{key}_assertion",
                         help="present = yes; absent = not there; denied = patient said no; possible = hedged")
        if a != e.assertion:
            changes["assertion"] = a
    elif e.kind == "problem":
        ct = st.text_input("Complaint", e.complaint_text or "", key=f"f_{key}_ct")
        loc = st.text_input("Where the patient says it hurts", e.complaint_location.free_text or "", key=f"f_{key}_loc")
        tooth = st.text_input("Problem tooth (1–32)",
                              "" if e.clinical_target.tooth is None else str(e.clinical_target.tooth), key=f"f_{key}_tooth")
        if ct != (e.complaint_text or ""):
            changes["complaint_text"] = ct
        if loc != (e.complaint_location.free_text or ""):
            changes["complaint_location"] = {"free_text": loc}
        nt = int(tooth) if tooth.strip().isdigit() else None
        if nt != e.clinical_target.tooth:
            changes["clinical_target"] = {"tooth": nt}
    return changes


def render_transcript(src, highlight):
    rows = []
    for u in src.utterances.utterances:
        text = u.text
        spans = sorted((s, e) for uid, s, e in highlight if uid == u.id and s is not None)
        out, pos = "", 0
        for s, e in spans:
            if s >= pos:
                out += esc(text[pos:s]) + f"<mark>{esc(text[s:e])}</mark>"
                pos = e
        out += esc(text[pos:])
        rows.append(f"<b>{esc(src.role_of(u.speaker) or 'Speaker')}:</b> {out}")
    st.markdown("<br>".join(rows), unsafe_allow_html=True)


# ---------------------------------------------------------------- Review

def review_page():
    if session is None:
        st.info("Pick a visit in the sidebar, or start a new one.")
        return
    graph = load_graph(session)
    latest = load_latest(session) or {}
    src = load_sources(session)
    state = approval.load_state(session)
    log = session_check_log(session)
    vm = src.visit_meta
    st.markdown(f"### {esc(meta.get('case') or 'Visit')} · {esc(vm.date or '')} · {esc(vm.provider or '')}")
    st.markdown(f"**Status:** {STATE_LABEL[state.state]}")
    if state.revoked:
        st.warning("An earlier approval was undone because something changed after it was given.")
    if graph is None:
        no_graph()
        return
    flags = [Flag.model_validate(f) for f in latest.get("flags", [])]
    session_flag_actions(session).apply(flags)
    flag_by_id = {f.id: f for f in flags}
    note_reason = st.text_input("Note for your actions (optional)", key="reason",
                                placeholder="e.g. checked against the recording")
    reason = note_reason.strip() or f"Reviewed by the {role.lower()} against the transcript"

    covered = checklist(graph, flag_by_id, log, reason)
    alerts(graph, flags, reason, covered)

    left, right = st.columns([3, 2])
    highlight: set = set()
    with left:
        st.subheader("Note")
        for sec in (latest.get("note") or {}).get("sections", []):
            st.markdown(f"**{esc(sec['title'])}**")
            if sec.get("status_line"):
                st.caption(esc(sec["status_line"]))
            for line in sec["lines"]:
                eid = line.get("entity_id")
                if not eid:
                    st.write(f"- {plain.strip_ids(line['text'])}")
                    continue
                e = graph.get(eid)
                chip = "✎ entered by staff" if e.owner == "human" else (
                    "✓ checked" if accepted(graph, e, graph.pipeline_mode) else "⚠ needs review")
                c1, c2 = st.columns([6, 1])
                c1.markdown(f"- {esc(plain.strip_ids(line['text']))} <small>· {chip}</small>", unsafe_allow_html=True)
                if c2.toggle("Edit", key=f"edit_{eid}", value=st.session_state.get("editing") == eid):
                    for s in e.evidence:
                        highlight.add((s.source_id, s.start, s.end))
                    entity_editor(e, graph, log, reason)
        add_item(graph, reason)
    with right:
        st.subheader("Conversation")
        render_transcript(src, highlight)
        st.subheader("Quick notes")
        for q in src.quick_notes.notes:
            st.write(f"- {q.text}")

    approval_buttons(graph)
    technical_details(graph, latest)


def no_graph():
    st.error("A note couldn't be built yet because the chief complaint wasn't found.")
    if session.path("pending_registry.json").exists() and role == "Dentist":
        _act("Accept the assistant's chief complaint and rebuild the note", "accept_registry",
             human.accept_pending_registry, session, role)
    with st.form("registry"):
        ct = st.text_input("What is the patient's main complaint?")
        loc = st.text_input("Where do they say it hurts?")
        tooth = st.text_input("Which tooth did the dentist identify? (1–32, blank if none)")
        if st.form_submit_button("Save and rebuild the note"):
            guarded(human.enter_registry, session,
                    {"complaint_text": ct, "complaint_location": {"free_text": loc or None, "tooth": None},
                     "clinical_target": {"tooth": int(tooth) if tooth.strip().isdigit() else None, "free_text": None}},
                    role, "entered on the review page")
            st.rerun()


def _entity_of(b, graph):
    if b.get("entity_id"):
        return b["entity_id"]
    if b["kind"] == "task":
        t = graph.task(b["task_id"])
        if t.kind in human.ENTITY_TASKS and t.participants:
            return t.participants[0].entity_id
    return None


def checklist(graph, flag_by_id, log, reason):
    """One line per thing to do: a failed check and the review tasks about the same entity are one item."""
    target = "assistant" if role == "Assistant" else "dentist"
    groups: dict = {}
    for i, b in enumerate(approval.blocker_items(session, target)):
        if b["kind"] == "flag" and b.get("flag_id") in flag_by_id:
            b["_flag_title"] = plain.flag_title(flag_by_id[b["flag_id"]], graph)
        groups.setdefault(_entity_of(b, graph) or f"_{i}", []).append(b)
    title = "Before you mark your review complete" if target == "assistant" else "Before you approve the note"
    st.subheader(f"{title} ({len(groups)} to do)" if groups else f"{title}: nothing left to do ✓")
    staging = session_staging(session)
    covered = {"flags": set(), "entities": set(), "tasks": set(), "conflicts": set(), "titles": []}
    for i, group in enumerate(groups.values()):
        primary = next((b for b in group if b["kind"] == "check"), group[0])
        primary = {**primary, "_flag_ids": [b["flag_id"] for b in group if b.get("flag_id")],
                   "_task_ids": [b["task_id"] for b in group if b.get("task_id")]}
        text = plain.blocker_text(primary, graph, log, staging)
        covered["flags"].update(primary["_flag_ids"])
        covered["tasks"].update(primary["_task_ids"])
        covered["conflicts"].update(b["conflict_id"] for b in group if b.get("conflict_id"))
        ent = _entity_of(primary, graph)
        if ent:
            covered["entities"].add(ent)
        if primary["kind"] == "staged":
            rec = staging.get(primary["staged_id"])
            if rec is not None and rec.task_id:
                covered["tasks"].add(rec.task_id)
        covered["titles"].append(text)
        c1, c2 = st.columns([5, 4])
        c1.markdown(f"☐ {esc(text)}")
        with c2:
            item_actions(primary, graph, flag_by_id, reason, f"b{i}")
    return covered


# Safeguard flags that only restate a checklist item (a failed check, an open task, a conflict).
RESTATING = {"unsupported_content", "open_review_task", "open_conflict", "stage_failure", "incomplete_section",
             "unknown_option_link"}


def _covered(f, title, covered) -> bool:
    if f.id in covered["flags"]:
        return True
    if f.rule_id in RESTATING and (set(f.entity_ids) & covered["entities"] or set(f.task_ids) & covered["tasks"]
                                   or set(f.conflict_ids) & covered["conflicts"]):
        return True
    return any(t == title or t.startswith(title + " \u2014") for t in covered["titles"])


def _send_all(flag_ids, reason):
    for fid in flag_ids:
        human.flag_action(session, fid, "for_dentist", role, reason)


def _complete_all(task_ids, reason):
    for tid in task_ids:
        human.complete_task(session, tid, "accepted", role, reason)


def item_actions(b, graph, flag_by_id, reason, key):
    k = b["kind"]
    cols = st.columns(3)
    flag_ids = b.get("_flag_ids") or ([b["flag_id"]] if b.get("flag_id") else [])
    send = role == "Assistant" and flag_ids
    if k == "section":
        with cols[0]:
            _act("Not discussed", f"{key}_nd", human.review_section, session, b["section"], "not_discussed", role, reason)
        with cols[1]:
            _act("I reviewed it", f"{key}_rv", human.review_section, session, b["section"], "completed", role, reason)
    elif k == "check":
        eid = b["entity_id"]
        with cols[0]:
            if role == "Dentist":
                _act("Confirm", f"{key}_ok", human.confirm_entity, session, eid, "dentist_confirmed", role, reason)
            elif not b["critical"]:
                _act("Looks right", f"{key}_ok", human.confirm_entity, session, eid, "human_reviewed", role, reason)
            elif send:
                _act("Send to dentist", f"{key}_fd", _send_all, flag_ids, reason)
        with cols[1]:
            if st.button("Edit", key=f"{key}_ed"):
                st.session_state["editing"] = eid
                st.rerun()
    elif k == "pending" and role == "Dentist":
        with cols[0]:
            _act("Accept", f"{key}_pa", human.decide_pending, session, b["pending_id"], True, role, reason)
        with cols[1]:
            _act("Reject", f"{key}_pr", human.decide_pending, session, b["pending_id"], False, role, reason)
    elif k == "conflict":
        c = graph.conflict(b["conflict_id"])
        parts = [graph.get(p.entity_id, p.version) for p in c.participants]
        for j, p in enumerate([p for p in parts if p is not None and p.status == "active"][:2]):
            with cols[j]:
                _act(f"Keep: {plain.describe(p, graph)[:45]}", f"{key}_k{j}", human.resolve_conflict, session, c.id,
                     "select", role, reason, active_entity_id=p.id)
        with cols[2]:
            _act("Both are right", f"{key}_kb", human.resolve_conflict, session, c.id, "keep_both", role, reason,
                 explanation=reason)
            if send:
                _act("Send to dentist", f"{key}_fd", _send_all, flag_ids, reason)
    elif k == "staged":
        with cols[0]:
            _act("Discard", f"{key}_dc", human.discard_staged, session, b["staged_id"], role, reason)
        if send:
            with cols[1]:
                _act("Send to dentist", f"{key}_fd", _send_all, flag_ids, reason)
    elif k == "task":
        t = graph.task(b["task_id"])
        dentist_only = t.kind == "stage_failure" and t.created_by_stage == "C" and \
            any(f" {a} " in f" {t.reason} " for a in ("Co", "R2"))
        with cols[0]:
            if role == "Dentist" or not dentist_only:
                _act("Done — I checked", f"{key}_tk", _complete_all, b.get("_task_ids") or [t.id], reason)
        if send:
            with cols[1]:
                _act("Send to dentist", f"{key}_fd", _send_all, flag_ids, reason)
    elif k == "flag":
        f = flag_by_id[b["flag_id"]]
        with cols[0]:
            if role == "Dentist" or not f.safety_critical:
                _act("Reviewed — dismiss", f"{key}_dm", human.flag_action, session, f.id, "dismiss", role, reason)
        if role == "Assistant":
            with cols[1]:
                _act("Send to dentist", f"{key}_fd", human.flag_action, session, f.id, "for_dentist", role, reason)


def alerts(graph, flags, reason, covered):
    """Alerts not already on the checklist, each issue once (same wording = one line, under its highest severity)."""
    rank = {"high": 0, "medium": 1, "low": 2}
    merged: dict = {}
    for f in sorted(flags, key=lambda f: rank[f.severity]):
        title = plain.flag_title(f, graph)
        if _covered(f, title, covered):
            continue
        merged.setdefault(title, []).append(f)
    st.subheader("Other alerts" if covered["titles"] else "Alerts")
    if not merged:
        st.write("Nothing else." if covered["titles"] else "No alerts.")
    for heading, sev in (("Needs attention", "high"), ("Please check", "medium"), ("For your information", "low")):
        rows = [(t, fs) for t, fs in merged.items() if fs[0].severity == sev]
        if not rows:
            continue
        st.markdown(f"**{heading}**")
        for title, fs in rows:
            f = fs[0]
            stt = flag_state(f)
            done = {"for_dentist": " — sent to the dentist", "dismissed_by_assistant": " — dismissed",
                    "dismissed_by_dentist": " — dismissed by the dentist", "resolved": " — resolved"}.get(stt, "")
            icon = "🛑" if any(x.safety_critical for x in fs) else ("❓" if f.question else "•")
            st.markdown(f"{icon} {esc(title)}{esc(done)}")
            with st.expander("Details"):
                for x in fs:
                    st.caption(f"rule {x.rule_id} v{x.rule_version} ({x.rule_status}) · severity {x.severity} · "
                               f"origin {x.origin} · items {', '.join(x.entity_ids) or '—'} · tasks "
                               f"{', '.join(x.task_ids) or '—'} · conflicts {', '.join(x.conflict_ids) or '—'}")
                    st.caption(esc(x.message))
                    for h in x.history:
                        st.caption(f"{h.timestamp[:16]} {h.by_role} {h.action}: {esc(h.reason)}")
                ids = [x.id for x in fs]
                c1, c2 = st.columns(2)
                if role == "Assistant" and stt == "open":
                    with c1:
                        _act("Send to dentist", f"al_fd_{f.id}", _flag_all, ids, "for_dentist", reason)
                if stt in ("open", "for_dentist") and (role == "Dentist" or not any(x.safety_critical for x in fs)):
                    with c2:
                        _act("Dismiss", f"al_dm_{f.id}", _flag_all, ids, "dismiss", reason)


def _flag_all(flag_ids, action, reason):
    for fid in flag_ids:
        human.flag_action(session, fid, action, role, reason)


def entity_editor(e, graph, log, reason):
    with st.container(border=True):
        needs = not accepted(graph, e, graph.pipeline_mode) and e.owner != "human"
        st.caption("Highlighted in the conversation on the right." +
                   (f" Needs review: {plain.why(e, log)}." if needs else ""))
        changes = field_form(e, e.id)
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Save changes", key=f"save_{e.id}", disabled=not changes):
                if guarded(human.edit_entity, session, e.id, changes, role, reason):
                    st.session_state.pop("editing", None)
                st.rerun()
        with c2:
            if role == "Dentist" or not is_critical(e):
                kind = "dentist_confirmed" if role == "Dentist" else "human_reviewed"
                _act("Looks right", f"conf_{e.id}", human.confirm_entity, session, e.id, kind, role, reason)
        with c3:
            _act("Remove", f"rm_{e.id}", human.remove_entity, session, e.id, role, reason)
        if role == "Assistant" and is_critical(e):
            st.caption("Changes to teeth, allergies, medicines, prescriptions, blood pressure, diagnoses and "
                       "decisions go to the dentist to accept.")
        with st.expander("Details"):
            st.caption(f"id {e.ref} · checks {e.checks.model_dump()} · source {e.owner}")
            st.caption("Quotes: " + " | ".join(f"{s.source_id}: “{esc(s.text)}”" for s in e.evidence))
            st.code(json.dumps(e.model_dump(mode="json", by_alias=True, exclude={"evidence"}), indent=1))


def add_item(graph, reason):
    with st.expander("Add something the note is missing"):
        labels = {plain.TYPE_LABEL[t].capitalize(): t for t in ATTRIBUTE_MODELS}
        itype = labels[st.selectbox("What kind of item?", list(labels), key="add_type")]
        scope = "problem" if "problem" in ITEM_SCOPES[itype] and graph.chief() else "encounter"
        draft = Item(id="new", type=itype, scope=scope, problem_id=graph.chief().id if scope == "problem" else None,
                     owner="human", assertion_source="clinician_assessment")
        changes = field_form(draft, f"add_{itype}")
        src = st.selectbox("Who said it?", ["clinician_assessment", "clinician_observation", "patient_report",
                                            "clinician_instruction", "assistant_record"], key="add_src",
                           format_func=lambda s: s.replace("_", " "))
        if st.button("Add to the note", key="add_btn"):
            guarded(human.add_entity, session,
                    {"kind": "item", "type": itype, "scope": scope, "problem_id": draft.problem_id,
                     "target": changes.get("target", {"tooth": None}), "attributes": changes.get("attributes", {}),
                     "assertion": changes.get("assertion", "present"), "time_context": "current",
                     "assertion_source": src}, role, reason)
            st.rerun()


def approval_buttons(graph):
    """Only the sign-off step that applies now is offered."""
    st.subheader("Sign-off")
    state = approval.load_state(session)
    c1, c2, c3 = st.columns(3)
    if state.state in ("dentist_approved", "exported"):
        last = state.records[-1]
        st.caption(f"{STATE_LABEL[state.state]} ({last.approver_role}, "
                   f"{datetime.fromisoformat(last.timestamp).astimezone().strftime('%b %d %H:%M')}).")
    if role == "Assistant":
        if state.state == "draft":
            with c1:
                _act("Mark my review complete", "appr_asst", approval.approve_assistant, session)
        elif state.state == "assistant_review_complete":
            st.caption("Your review is complete; waiting for the dentist.")
        return
    if state.state == "draft":
        st.caption("Waiting for the assistant's review.")
    elif state.state == "assistant_review_complete":
        with c1:
            _act("Approve the note", "appr_dent", approval.approve_dentist, session)
    elif state.state == "dentist_approved":
        with c2:
            if st.button("Export", key="export"):
                path = guarded(approval.export, session)
                if path and path is not True:
                    st.download_button("Download the exported note", Path(path).read_bytes(),
                                       file_name=Path(path).name)
    elif state.state == "exported" and state.export_path and Path(state.export_path).exists():
        with c2:
            st.download_button("Download the exported note", Path(state.export_path).read_bytes(),
                               file_name=Path(state.export_path).name, key="dl_export")
    if state.state in ("draft", "assistant_review_complete"):
        with c3:
            _act("Refresh clinical review questions", "retry_e3", derive, session, graph, load_sources(session),
                 graph.pipeline_mode, session.meta().get("rule_mode"), retry_e3=True)


def technical_details(graph, latest):
    with st.expander("Details (technical)"):
        status = latest.get("status") or {}
        st.caption(f"graph v{graph.version} · verification {status.get('verification_level')} · "
                   f"rule mode {status.get('rule_mode')} · notices: {'; '.join(latest.get('notices', []))}")
        st.markdown("**Blocking items (raw)**")
        for b in approval.blockers(session, "assistant" if role == "Assistant" else "dentist"):
            st.caption(b)
        st.markdown("**Conflicts**")
        for c in graph.conflicts:
            st.caption(f"{c.id} {c.kind} {c.status} · " + ", ".join(f"{p.entity_id}@{p.version}" for p in c.participants))
        st.markdown("**Review tasks**")
        for t in graph.tasks:
            st.caption(f"{t.id} {t.kind} {t.status}: {t.reason}")
        st.markdown("**Staged records (not part of the clinical draft)**")
        for r in session_staging(session).open_records():
            st.caption(f"{r.id} {r.owner} {r.kind}: {'; '.join(r.errors)}")
            st.code(json.dumps(r.raw, indent=1))
        st.markdown("**Pending dentist review**")
        for p in graph.pending_changes:
            st.caption(f"{p.id} {p.operation} {p.status} by {p.by_role}: {p.reason}")


# ---------------------------------------------------------------- Technical log

def log_page():
    if session is None:
        return
    rows = [r for r in read_traces(session) if r.get("kind") == "model_call"]
    st.dataframe([{k: r.get(k) for k in ("timestamp", "agent", "label", "attempt", "schema_retry", "result",
                                          "seconds", "input_tokens", "output_tokens", "model", "prompt_hash",
                                          "graph_version", "error")} for r in rows], width="stretch")
    st.subheader("Stage runs")
    st.dataframe(session_stage_log(session).runs, width="stretch")


{"Start": start_page, "Review": review_page, "Speaker roles": roles_page, "Technical log": log_page}[page]()
