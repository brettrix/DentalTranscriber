"""Streamlit UI (section 13), written for a dental assistant: plain language first, technical details collapsed."""
from __future__ import annotations

import html
import json
import shutil
import tempfile
import typing
from datetime import datetime
from pathlib import Path

import streamlit as st

from components import copy_button
from pipeline import approval, exports, human, plain
from pipeline.chart import chart_sections
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
from pipeline.visits import (clock, filter_visits, is_test_visit, visit_heading, visit_meta, visit_name, visit_when,
                             waiting_text, worklists)
from schemas.entities import ATTRIBUTE_MODELS, ITEM_SCOPES, Item, is_critical
from schemas.flags import Flag

BANNER = "Prototype — test data only. Do not use with real patient information."
MAX_LISTED = 60
TABS = ["New visit", "Review", "Waiting for dentist", "Cleared by dentist", "Admin"]
st.set_page_config(page_title="Dental Scribe (prototype)", layout="wide")

# Navigation requested by an action in the previous run (a widget's value can't change after it is drawn).
for _key in ("page", "sid"):
    if f"next_{_key}" in st.session_state:
        st.session_state[_key] = st.session_state.pop(f"next_{_key}")
if st.session_state.get("page") not in TABS:
    st.session_state["page"] = TABS[0]


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def go(page: str, sid: str | None = None):
    st.session_state["next_page"] = page
    if sid:
        st.session_state["next_sid"] = sid
    st.rerun()


# ---------------------------------------------------------------- messages, shown next to the button that caused them

def notify(slot: str, kind: str, text: str) -> None:
    st.session_state.setdefault("notices", {})[slot] = (kind, text)


def show_notice(slot: str) -> None:
    kind, text = st.session_state.get("notices", {}).pop(slot, (None, None))
    if text:
        {"error": st.error, "success": st.success, "info": st.info}[kind](text)


def guarded(slot: str, fn, *args, doing: str = "do that", done: str | None = "Saved.", **kw):
    """Run an action; put its confirmation or a plain-words error in the slot beside the button that started it."""
    try:
        out = fn(*args, **kw)
    except Exception as exc:  # noqa: BLE001 - nothing raw reaches the page; the text is kept for the Admin tab
        st.session_state["last_error"] = f"{datetime.now():%H:%M:%S} {type(exc).__name__}: {exc}"
        notify(slot, "error", plain.friendly_error(exc, doing))
        return None
    if done:
        notify(slot, "success", done)
    return out if out is not None else True


def _act(label, key, fn, *args, doing="do that", done="Saved.", type="secondary", **kw):
    if st.button(label, key=key, type=type):
        guarded(key, fn, *args, doing=doing, done=done, **kw)
        st.rerun()
    show_notice(key)


# ---------------------------------------------------------------- sidebar: role and visit

role = st.sidebar.selectbox("Your role (Prototype: no real login)", ["Assistant", "Dentist"])
sessions = list_sessions()  # newest first
by_id = {s.id: s for s in sessions}
st.sidebar.markdown("""<style>
section[data-testid='stSidebar'] { min-width: 330px; }
section[data-testid='stSidebar'] [class*='st-key-visit_'] button { justify-content: flex-start; text-align: left; }
</style>""", unsafe_allow_html=True)
if st.sidebar.button("＋ New visit", key="new_visit", width="stretch"):
    go("New visit")
search = st.sidebar.text_input("Search visits", key="visit_search", placeholder="Patient name, chart # or date")
listed = filter_visits(sessions, search, st.session_state.get("show_tests", False))
if st.session_state.get("sid") not in by_id:
    st.session_state["sid"] = listed[0].id if listed else None
sid = st.session_state["sid"]
with st.sidebar.container(height=460):
    # One button per visit, keyed by the visit's own id: a click can only ever open that visit, whatever the
    # list order is and however many visits share a name.
    if not listed:
        st.caption("No visits match." if search else "No visits yet.")
    for s in listed[:MAX_LISTED]:
        m = s.meta()
        if st.button(f"{visit_name(m)} · {visit_when(m)}", key=f"visit_{s.id}", width="stretch",
                     type="primary" if s.id == sid else "secondary", help=visit_heading(s)):
            go("Review", s.id)
    if len(listed) > MAX_LISTED:
        st.caption(f"Showing the newest {MAX_LISTED} of {len(listed)}. Search to find older visits.")
session = by_id.get(sid)
meta = session.meta() if session else {}
st.error(BANNER)


# ---------------------------------------------------------------- New visit

INPUTS = ["Record visit", "Upload a recording", "Paste a transcript"]


def _last_names() -> tuple[str, str]:
    """The dentist and assistant from the most recent real visit, so they aren't retyped every time."""
    for s in sessions[:20]:
        if not is_test_visit(s.meta()):
            vm = visit_meta(s)
            return vm.get("provider") or "", vm.get("assistant") or ""
    return "", ""


def new_visit_page():
    st.subheader("New visit")
    last_dentist, last_assistant = _last_names()
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    patient = c1.text_input("Patient (name or chart #) *", key="nv_patient")
    date = c2.text_input("Visit date", datetime.now().strftime("%Y-%m-%d"), key="nv_date")
    provider = c3.text_input("Dentist", last_dentist, key="nv_dentist")
    assistant = c4.text_input("Assistant", last_assistant, key="nv_assistant")
    source = st.radio("How do you want to add the visit?", INPUTS, horizontal=True, key="nv_input")
    transcript, audio = None, None
    if source == "Record visit":
        audio = st.audio_input("Press the microphone to start, and again to stop", key="nv_record")
    elif source == "Upload a recording":
        audio = st.file_uploader("Recording (wav, mp3, m4a or flac; up to 50 MB and 30 minutes)",
                                 type=["wav", "mp3", "m4a", "flac"], key="nv_upload")
    else:
        transcript = st.text_area("Transcript (one speaker per line, like “DENTIST: …” or “PATIENT: …”)",
                                  height=200, key="nv_transcript")
    quick = st.text_area("Quick notes (optional, one per line)", height=100, key="nv_quick",
                         placeholder="BP 124/80\nCC: lower left pain\n#19")
    with st.expander("Admin settings"):
        mode = st.radio("Pipeline mode", ["baseline", "team"], horizontal=True, key="nv_mode",
                        help="baseline: one extractor, quote-checked. team: split extractors plus meaning checks.")
        rule_mode = st.radio("Rule mode", ["synthetic_demo", "office"], horizontal=True, key="nv_rules")
        cases = sorted(p for p in (ROOT / "eval" / "cases").iterdir() if p.is_dir())
        chosen = st.selectbox("Test case (replaces the recording or transcript above)",
                              ["(none)"] + [p.name for p in cases], key="nv_case")
        case_dir = next((p for p in cases if p.name == chosen), None)
    clicked = st.button("Write the note", type="primary", key="write_note")
    show_notice("write_note")
    if not clicked:
        return
    patient = patient.strip()
    if not patient and case_dir is None:
        st.error("Enter the patient's name or chart number first.")
        return
    if case_dir is None and audio is None and not (transcript or "").strip():
        st.error({"Record visit": "Record the visit first: press the microphone to start and again to stop.",
                  "Upload a recording": "Choose a recording to upload first.",
                  "Paste a transcript": "Paste the transcript first."}[source])
        return
    s = Session.create(patient=patient or None, case=case_dir.name if case_dir else None,
                       test=case_dir is not None, pipeline_mode=mode, rule_mode=rule_mode)
    write_visit_meta(s, date=date, provider=provider, assistant=assistant or None)
    try:
        if case_dir is not None:
            transcribe_text(s, (case_dir / "transcript.txt").read_text("utf-8"))
            quick = quick or (case_dir / "quick_notes.txt").read_text("utf-8")
        elif audio is not None:
            tmp = Path(tempfile.mkdtemp()) / (Path(audio.name).name if Path(audio.name).suffix else "visit.wav")
            tmp.write_bytes(audio.getvalue())
            with st.spinner("Transcribing the recording…"):
                transcribe_audio(s, tmp)
        else:
            transcribe_text(s, transcript or "")
        write_quick_notes(s, quick)
    except Exception as exc:  # noqa: BLE001
        st.session_state["last_error"] = f"{datetime.now():%H:%M:%S} {type(exc).__name__}: {exc}"
        shutil.rmtree(s.dir, ignore_errors=True)  # nothing usable was saved; don't leave an empty visit in the list
        st.error(plain.friendly_error(exc, "read the recording or transcript"))
        return
    for key in ("nv_patient", "nv_transcript", "nv_quick", "nv_record", "nv_upload"):
        st.session_state.pop(key, None)
    if case_dir is not None:
        st.session_state["show_tests"] = True  # so the test visit just started is in the list
    if not load_sources(s).roles.confirmed:
        go("Review", s.id)  # the Review page asks who is speaking, then writes the note
    with st.spinner("Writing the note…"):
        guarded("review_top", run_pipeline, s, mode=mode, rule_mode=rule_mode, doing="write the note", done=None)
    go("Review", s.id)


# ---------------------------------------------------------------- who is speaking (recordings)

def roles_form(s, button: str):
    src = load_sources(s)
    st.write("Several voices can share a role (for example, two dentists).")
    mapping = {}
    opts = ["Dentist", "Assistant", "Patient", "Other"]
    for spk in sorted({u.speaker for u in src.utterances.utterances}):
        sample = [u.text for u in src.utterances.utterances if u.speaker == spk][:3]
        st.markdown(f"**Voice {esc(spk[1:])}**: " + " / ".join(f"“{esc(t)}”" for t in sample))
        current = src.roles.entries.get(spk).role if spk in src.roles.entries else "Other"
        mapping[spk] = st.selectbox(f"Who is voice {spk[1:]}?", opts, index=opts.index(current), key=f"r{s.id}{spk}")
    clicked = st.button(button, type="primary", key="confirm_roles")
    show_notice("confirm_roles")
    if clicked:
        if "Patient" not in mapping.values() or "Dentist" not in mapping.values():
            st.error("Choose which voice is the patient and which is the dentist first.")
            return
        confirm_roles(s, mapping, by=role)
        with st.spinner("Writing the note…"):
            guarded("review_top", run_pipeline, s, doing="write the note", done=None)
        go("Review", s.id)


# ---------------------------------------------------------------- Admin

def admin_page():
    st.subheader("Admin")
    st.toggle("Show test and evaluation visits in the visit list", key="show_tests_widget",
              value=st.session_state.get("show_tests", False),
              on_change=lambda: st.session_state.update(show_tests=st.session_state["show_tests_widget"]))
    if st.session_state.get("last_error"):
        st.caption(f"Last error (technical): {st.session_state['last_error']}")
    if session is None:
        st.info("Pick a visit in the sidebar to see its speaker roles and technical log.")
        return
    st.caption(f"Selected visit: {visit_heading(session)} · mode {meta.get('pipeline_mode', '—')} · "
               f"rules {meta.get('rule_mode', '—')}")
    with st.expander("Speaker roles"):
        st.caption("Changing who is speaking rewrites the note from the start and undoes any approval.")
        roles_form(session, "Save speakers and rewrite the note")
    with st.expander("Technical log"):
        rows = [r for r in read_traces(session) if r.get("kind") == "model_call"]
        st.dataframe([{k: r.get(k) for k in ("timestamp", "agent", "label", "attempt", "schema_retry", "result",
                                              "seconds", "input_tokens", "output_tokens", "model", "prompt_hash",
                                              "graph_version", "error")} for r in rows], width="stretch")
        st.markdown("**Stage runs**")
        st.dataframe(session_stage_log(session).runs, width="stretch")


# ---------------------------------------------------------------- field form

ASSERTION_LABEL = {"present": "Yes", "absent": "No / not there", "denied": "Patient says no", "possible": "Maybe",
                   "unintelligible": "Couldn't hear it clearly"}
FIELD_NAME = {"medication_status": "Still taking it?", "allergy_status": "Allergy status", "frequency_code": "How often",
              "frequency": "How often", "duration_days": "Number of days", "as_needed": "Only as needed?",
              "prescription_status": "Prescription status", "recommended_by_clinician": "Recommended by the dentist?",
              "result_description": "What was seen or felt", "duration_s": "How long it lasted (seconds)",
              "probing_depth_mm": "Probing depth (mm)", "recession_mm": "Recession (mm)",
              "attachment_loss_mm": "Attachment loss (mm)", "bone_loss": "Bone loss?", "to": "Referred to",
              "original_wording": "Exact words used", "type": "Kind of X-ray", "systolic": "Top number",
              "diastolic": "Bottom number", "score": "Number (for example pain 0–10)", "response": "Result",
              "label": "First reading or recheck?", "value": "Details", "aspect": "What about it"}
VALUE_NAME = {"present": "positive", "absent": "negative", "reported_active": "active", "reported_resolved": "resolved",
              "PA": "periapical (PA)", "BWX": "bitewing (BWX)", "FMX": "full mouth", "pano": "panoramic"}


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


def _value_label(v) -> str:
    return v if v == "(not stated)" else VALUE_NAME.get(v, str(v).replace("_", " "))


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
            label = FIELD_NAME.get(name, name.replace("_", " ").capitalize())
            if kind == "choice":
                choices = ["(not stated)"] + opts
                v = st.selectbox(label, choices, index=choices.index(cur) if cur in choices else 0,
                                 key=f"f_{key}_{name}", format_func=_value_label)
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
        opts = list(ASSERTION_LABEL)
        a = st.selectbox("Is it there?", opts, index=opts.index(e.assertion), key=f"f_{key}_assertion",
                         format_func=ASSERTION_LABEL.get)
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

REVIEW_CSS = """<style>
[data-testid="stButtonGroup"] button { white-space: nowrap; }
[data-testid="stButtonGroup"] button p { white-space: nowrap; }
[data-testid="stButtonGroup"] button[data-selected] { background: #1f8a3b !important; border-color: #1f8a3b !important;
  color: #fff !important; }
[data-testid="stButtonGroup"] button[data-selected] p { color: #fff !important; }
/* Edit appears only on the line being pointed at (or focused, or already open); always on touch screens. */
[class*="st-key-noteline_"] [class*="st-key-edit_"] { opacity: 0; transition: opacity .12s; }
[class*="st-key-noteline_"]:hover [class*="st-key-edit_"],
[class*="st-key-noteline_"]:focus-within [class*="st-key-edit_"],
[class*="st-key-noteline_open_"] [class*="st-key-edit_"] { opacity: 1; }
@media (hover: none) { [class*="st-key-noteline_"] [class*="st-key-edit_"] { opacity: 1; } }
[class*="st-key-noteline_"] [data-testid="stVerticalBlock"] { gap: 0.2rem; }
[class*="st-key-noteline_"] button { padding: 0 .4rem; min-height: 1.6rem; }
</style>"""
APPROVED = ("dentist_approved", "exported")


def _default_reason() -> str:
    return plain.DEFAULT_REASON.format(role=role.lower())


def _items(n: int) -> str:
    return f"{n} item{'' if n == 1 else 's'}"


def _stamp(state, kind: str) -> str | None:
    return next((r.timestamp for r in reversed(state.records) if r.kind == kind), None)


def review_page():
    if session is None:
        st.info("Pick a visit on the left, or start a new one.")
        return
    st.markdown(f"### {esc(visit_heading(session))}")
    show_notice("review_top")
    src = load_sources(session)
    if not src.roles.confirmed:
        st.info("**Who is speaking?** Tell us which voice is the dentist, the patient and the assistant. "
                "Then the note is written.")
        roles_form(session, "Confirm speakers and write the note")
        return
    graph = load_graph(session)
    latest = load_latest(session) or {}
    state = approval.load_state(session)
    log = session_check_log(session)
    if graph is None:
        no_graph()
        return
    st.markdown(REVIEW_CSS, unsafe_allow_html=True)
    flags = [Flag.model_validate(f) for f in latest.get("flags", [])]
    session_flag_actions(session).apply(flags)
    flag_by_id = {f.id: f for f in flags}
    approved = state.state in APPROVED
    target = "assistant" if role == "Assistant" else "dentist"
    items = [] if approved else approval.blocker_items(session, target)
    staging = session_staging(session)
    cards = plain.build_cards(items, graph, log, staging, src, role, flag_by_id)

    status_line(state, cards)
    if not approved:
        checklist(cards)
        sign_off(state, cards, items)
        alerts(graph, flags, _covered_by(items, graph, log, staging))

    left, right = st.columns([3, 2])
    highlight: set = set()
    with left:
        st.subheader("Note")
        chart = chart_sections(latest.get("note") or {}, graph)
        for sec in chart["sections"]:
            st.markdown(f"**{esc(sec['title'])}**")
            if sec["incomplete"]:
                st.caption("This part couldn't be filled in automatically. Check the conversation.")
            for line in sec["lines"]:
                note_line(line, graph, log, highlight, editable=not approved)
        if chart["not_discussed"]:
            st.caption("Not discussed: " + ", ".join(chart["not_discussed"]))
        if not approved:
            add_item(graph)
    with right:
        st.subheader("Conversation")
        render_transcript(src, highlight)
        if src.quick_notes.notes:
            st.subheader("Quick notes")
            for q in src.quick_notes.notes:
                st.write(f"- {q.text}")
        st.caption("Download")
        source_downloads(session, "review")
    technical_details(graph, latest)


def status_line(state, cards):
    """Where the note stands and what happens next, at the top of the page."""
    if state.state in APPROVED:
        at = _stamp(state, "dentist_approved")
        st.success(f"**Approved by the dentist at {clock(at)}** · Download note:")
        downloads()
        return
    if state.revoked:
        st.warning("This note changed after it was signed off, so it needs to be reviewed again.")
    n = len(cards)
    if state.state == "draft":
        if role == "Assistant":
            st.info(f"**Waiting for your review** · Answer the {_items(n)} below, then send the note to the dentist."
                    if n else "**Waiting for your review** · Nothing left to answer. Send the note to the dentist.")
        else:
            st.info("**Waiting for the assistant's review** · It can't be approved yet"
                    + (f", but you can already answer the {_items(n)} below." if n else "."))
    else:
        sent = _stamp(state, "assistant_review_complete")
        if role == "Assistant":
            st.info(f"**Waiting for the dentist** · Sent at {clock(sent)} ({waiting_text(sent)} ago).")
        else:
            st.info(f"**Waiting for your approval** · Answer the {_items(n)} below, then approve the note."
                    if n else "**Waiting for your approval** · Nothing left to answer. Approve the note.")


def downloads():
    """The approved note: PDF first, then Word, one-click copy and the whole visit as a zip. Never Markdown."""
    if exports.approved_record(session) is None:
        st.warning("This note changed after it was approved, so the dentist needs to approve it again.")
        return
    stem = exports.file_stem(session)
    c1, c2, c3, c4, _ = st.columns([2, 2, 2, 3, 2])
    c1.download_button("Download PDF", lambda: exports.note_pdf(session), file_name=f"{stem} note.pdf",
                       mime=exports.PDF_MIME, type="primary", key="dl_pdf", on_click="ignore", width="stretch")
    c2.download_button("Word (.docx)", lambda: exports.note_docx(session), file_name=f"{stem} note.docx",
                       mime=exports.DOCX_MIME, key="dl_docx", on_click="ignore", width="stretch")
    with c3:
        copy_button(exports.note_text(session), key="copy_note")
    c4.download_button("Download everything (.zip)", lambda: exports.bundle_zip(session), file_name=f"{stem}.zip",
                       mime="application/zip", key="dl_zip", on_click="ignore", width="stretch",
                       help="One folder with the note (PDF and Word), the transcript (PDF and text) and the recording")


def source_downloads(s, key: str):
    """The transcript and the recording, available at any stage of the visit."""
    stem = exports.file_stem(s)
    audio = exports.recording_path(s)
    cols = st.columns(3 if audio else 2)
    cols[0].download_button("Transcript (PDF)", lambda: exports.transcript_pdf(s), file_name=f"{stem} transcript.pdf",
                            mime=exports.PDF_MIME, key=f"tpdf_{key}", on_click="ignore", width="stretch")
    cols[1].download_button("Transcript (text)", lambda: exports.transcript_text(s),
                            file_name=f"{stem} transcript.txt", mime="text/plain", key=f"ttxt_{key}",
                            on_click="ignore", width="stretch")
    if audio:
        cols[2].download_button("Recording", audio.read_bytes, file_name=f"{stem} recording{audio.suffix.lower()}",
                                mime=exports.AUDIO_MIME[audio.suffix.lower()], key=f"rec_{key}", on_click="ignore",
                                width="stretch")


def no_graph():
    st.warning("**The note couldn't be written yet** because the patient's main complaint wasn't found. "
               "Fill it in below.")
    if session.path("pending_registry.json").exists() and role == "Dentist":
        _act("Accept the assistant's chief complaint and write the note", "accept_registry",
             human.accept_pending_registry, session, role, doing="write the note")
    with st.form("registry"):
        ct = st.text_input("What is the patient's main complaint?")
        loc = st.text_input("Where do they say it hurts?")
        tooth = st.text_input("Which tooth did the dentist identify? (1–32, blank if none)")
        if st.form_submit_button("Save and write the note"):
            if not ct.strip():
                notify("registry", "error", "Type the patient's main complaint first.")
            else:
                guarded("registry", human.enter_registry, session,
                        {"complaint_text": ct, "complaint_location": {"free_text": loc or None, "tooth": None},
                         "clinical_target": {"tooth": int(tooth) if tooth.strip().isdigit() else None,
                                             "free_text": None}},
                        role, "entered on the review page", doing="write the note")
            st.rerun()
    show_notice("registry")


TAG_COLOR = {"Safety": "red", "Tooth": "orange", "Medicine": "orange", "Allergy": "red", "Blood pressure": "orange",
             "Disagreement": "violet", "Diagnosis": "orange", "Decision": "orange", "Needs dentist": "blue",
             "Wording": "gray", "Possibly missed": "blue", "Not in note": "blue", "Section": "blue"}


def _card_key(card) -> str:
    import hashlib
    # Per role: the assistant's and the dentist's choices on a card differ.
    return "card_" + hashlib.sha1(f"{role}|{card['key']}".encode()).hexdigest()[:10]


def _render_card(card):
    key = _card_key(card)
    labels = {v: lbl for v, lbl, _ in card["options"]}
    with st.container(border=True):
        color = TAG_COLOR.get(card["tag"], "gray")
        st.markdown(f"**{esc(card['title'])}** &nbsp; :{color}-badge[{esc(card['tag'])}]")
        if card.get("hint"):
            st.caption(card["hint"])
        for comment in card.get("comments", []):
            st.markdown(f"💬 *{esc(comment)}*")
        c1, c2 = st.columns(2)
        with c1.container(border=True):
            st.caption(card["left"][0])
            st.markdown(esc(card["left"][1]).replace("\n", "  \n"))
        with c2.container(border=True):
            st.caption(card["right"][0])
            st.markdown(esc(card["right"][1]).replace("\n", "  \n"))
        kw = {} if key in st.session_state else {"default": card["default"]}
        c1, c2 = st.columns([3, 2])
        with c1:
            st.segmented_control("Your choice", list(labels), key=key, label_visibility="collapsed", width="content",
                                 format_func=lambda v, k=key: ("✓ " if st.session_state.get(k) == v else "")
                                 + labels[v], **kw)
        c2.text_input("Comment (optional)", key=f"{key}_note", label_visibility="collapsed",
                      placeholder="Comment (optional)" + (", for the dentist" if role == "Assistant" else ""))
        with st.expander("Details"):
            for d in card["details"]:
                st.caption(esc(d))


def checklist(cards):
    """Review cards: choose on each card (with an optional comment), then save everything at once."""
    shown = [c for c in cards if not c["hidden"]]
    hidden = [c for c in cards if c["hidden"]]
    if cards:
        st.subheader("To answer")
    for card in shown:
        _render_card(card)
    if hidden:
        n = len(hidden)
        with st.expander(f"{n} more {'item looks' if n == 1 else 'items look'} right · show"):
            for card in hidden:
                _render_card(card)
    if cards:
        answered = sum(1 for c in cards if st.session_state.get(_card_key(c)) is not None)
        c1, c2 = st.columns([2, 6])
        save = c1.button("Save my answers", type="primary", key="save_review")
        c2.markdown(f"**{answered} of {len(cards)} answered**")
        if save and answered < len(cards):
            st.error(f"Answer the {_items(len(cards) - answered)} above first.")
        elif save:
            choices = []
            for c in cards:
                v = st.session_state.get(_card_key(c))
                comment = (st.session_state.get(f"{_card_key(c)}_note") or "").strip()
                ops = next(ops for val, _, ops in c["options"] if val == v)
                choices += [{**op, "reason": comment} for op in ops] if comment else ops
            out = guarded("save_review", human.apply_review, session, choices, role, _default_reason(),
                          doing="save your answers", done="Saved your answers.")
            if isinstance(out, dict) and out.get("errors"):
                notify("save_review", "error", f"{_items(len(out['errors']))} couldn't be saved. "
                                               "Check what is still listed here and answer again.")
            for c in cards:
                st.session_state.pop(_card_key(c), None)
                st.session_state.pop(f"{_card_key(c)}_note", None)
            st.rerun()
    show_notice("save_review")


def sign_off(state, cards, items):
    """The one sign-off step that applies now, offered once nothing is left to answer."""
    if cards:
        return
    mine = (role == "Assistant" and state.state == "draft") or \
           (role == "Dentist" and state.state == "assistant_review_complete")
    if not mine:
        return
    label, key, fn = ("Send to the dentist", "appr_asst", approval.approve_assistant) if role == "Assistant" else \
        ("Approve the note", "appr_dent", approval.approve_dentist)
    if st.button(label, key=key, type="primary"):
        if items:  # something still blocks that this role has no way to answer
            notify(key, "error", f"{_items(len(items))} still need{'s' if len(items) == 1 else ''} "
                                 f"{'the dentist' if role == 'Assistant' else 'attention'} before this can be "
                                 f"{'sent' if role == 'Assistant' else 'approved'}. See “Technical details” below.")
        else:
            guarded(key, fn, session, doing="sign off the note", done=None)
        st.rerun()
    show_notice(key)


def _covered_by(items, graph, log, staging) -> dict:
    """What the checklist already covers, so the alerts below don't repeat it."""
    covered = {"flags": set(), "entities": set(), "tasks": set(), "conflicts": set(), "titles": []}
    for b in items:
        for k, field in (("flags", "flag_id"), ("entities", "entity_id"), ("tasks", "task_id"),
                         ("conflicts", "conflict_id")):
            if b.get(field):
                covered[k].add(b[field])
        if b["kind"] == "task":
            t = graph.task(b["task_id"])
            covered["entities"].update(p.entity_id for p in t.participants)
        if b["kind"] == "staged":
            rec = staging.get(b["staged_id"])
            if rec is not None and rec.task_id:
                covered["tasks"].add(rec.task_id)
        covered["titles"].append(plain.blocker_text(b, graph, log, staging))
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
    return any(t == title or t.startswith(title + " —") for t in covered["titles"])


def alerts(graph, flags, covered):
    """Alerts not already on the checklist, each issue once (same wording = one line, under its highest severity)."""
    rank = {"high": 0, "medium": 1, "low": 2}
    merged: dict = {}
    for f in sorted(flags, key=lambda f: rank[f.severity]):
        title = plain.flag_title(f, graph)
        if _covered(f, title, covered):
            continue
        merged.setdefault(title, []).append(f)
    if not merged:
        return
    st.subheader("Other alerts" if covered["titles"] else "Alerts")
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
            ids = [x.id for x in fs]
            can_send = role == "Assistant" and stt == "open"
            can_dismiss = stt in ("open", "for_dentist") and (role == "Dentist" or not any(x.safety_critical for x in fs))
            if can_send or can_dismiss:
                c1, c2, _ = st.columns([2, 2, 6])
                if can_send:
                    with c1:
                        _act("Send to dentist", f"al_fd_{f.id}", _flag_all, ids, "for_dentist",
                             done="Sent to the dentist.")
                if can_dismiss:
                    with c2:
                        _act("Dismiss", f"al_dm_{f.id}", _flag_all, ids, "dismiss", done="Dismissed.")
            with st.expander("Details"):
                for x in fs:
                    st.caption(f"rule {x.rule_id} v{x.rule_version} ({x.rule_status}) · severity {x.severity} · "
                               f"origin {x.origin} · items {', '.join(x.entity_ids) or '—'} · tasks "
                               f"{', '.join(x.task_ids) or '—'} · conflicts {', '.join(x.conflict_ids) or '—'}")
                    st.caption(esc(x.message))
                    for h in x.history:
                        st.caption(f"{h.timestamp[:16]} {h.by_role} {h.action}: {esc(h.reason)}")


def _flag_all(flag_ids, action):
    for fid in flag_ids:
        human.flag_action(session, fid, action, role, _default_reason())


def note_line(line, graph, log, highlight, editable=True):
    """One chart line. Edit shows when the line is pointed at; clicking it opens the editor under the line."""
    eid = line["entity_id"]
    if not eid:
        st.markdown(f"- {esc(line['text'])}")
        return
    e = graph.get(eid)
    chip = " <small>· added by staff</small>" if e.owner == "human" else (
        "" if accepted(graph, e, graph.pipeline_mode) else " <small>· ⚠ needs review</small>")
    if not editable:
        st.markdown(f"- {esc(line['text'])}", unsafe_allow_html=True)
        return
    opened = st.session_state.get("editing") == eid
    with st.container(key=f"noteline_{'open_' if opened else ''}{eid}"):
        c1, c2 = st.columns([8, 1])
        c1.markdown(f"- {esc(line['text'])}{chip}", unsafe_allow_html=True)
        if c2.button("Close" if opened else "Edit", key=f"edit_{eid}", type="tertiary"):
            st.session_state["editing"] = None if opened else eid
            st.rerun()
        show_notice(f"line_{eid}")
        if opened:
            for s in e.evidence:
                highlight.add((s.source_id, s.start, s.end))
            entity_editor(e)


def entity_editor(e):
    with st.container(border=True):
        if any(s.source_type == "transcript" for s in e.evidence):
            st.caption("The words this came from are highlighted in the conversation on the right.")
        changes = field_form(e, e.id)
        comment = st.text_input("Comment (optional)", key=f"note_{e.id}", placeholder="Why are you changing it?")
        reason = comment.strip() or _default_reason()
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Save changes", key=f"save_{e.id}", type="primary"):
                if not changes:
                    notify(f"save_{e.id}", "info", "Nothing was changed yet.")
                elif guarded(f"line_{e.id}", human.edit_entity, session, e.id, changes, role, reason,
                             doing="save that change", done=_saved_text(e)):
                    st.session_state.pop("editing", None)
                st.rerun()
            show_notice(f"save_{e.id}")
        with c2:
            if role == "Dentist" or not is_critical(e):
                kind = "dentist_confirmed" if role == "Dentist" else "human_reviewed"
                _act("Looks right", f"conf_{e.id}", human.confirm_entity, session, e.id, kind, role, reason,
                     done="Marked as checked.")
        with c3:
            _act("Remove from note", f"rm_{e.id}", human.remove_entity, session, e.id, role, reason,
                 doing="remove it", done=_saved_text(e, "Removed."))
        if role == "Assistant" and is_critical(e):
            st.caption("Changes to teeth, allergies, medicines, prescriptions, blood pressure, diagnoses and "
                       "decisions go to the dentist to accept.")
        with st.expander("Details"):
            st.caption(f"id {e.ref} · checks {e.checks.model_dump()} · source {e.owner}")
            st.caption("Quotes: " + " | ".join(f"{s.source_id}: “{esc(s.text)}”" for s in e.evidence))
            st.code(json.dumps(e.model_dump(mode="json", by_alias=True, exclude={"evidence"}), indent=1))


def _saved_text(e, saved="Saved.") -> str:
    return "Sent to the dentist to accept." if role == "Assistant" and is_critical(e) else saved


WHO = {"Dentist": None, "Patient": "patient_report", "Assistant": "assistant_record"}
DENTIST_SOURCE = {"finding": "clinician_observation", "perio_measurement": "clinician_observation",
                  "radiograph": "clinician_observation", "instruction": "clinician_instruction",
                  "prescription": "clinician_instruction", "referral": "clinician_instruction",
                  "next_visit": "clinician_instruction"}
PATIENT_FIRST = ("symptom", "history_change", "medication", "allergy", "decision")


def add_item(graph):
    with st.expander("Add something the note is missing"):
        labels = {plain.TYPE_LABEL[t].capitalize(): t for t in ATTRIBUTE_MODELS}
        itype = labels[st.selectbox("What do you want to add?", sorted(labels), key="add_type")]
        who = st.radio("Who said it?", list(WHO), horizontal=True, key=f"add_who_{itype}",
                       index=1 if itype in PATIENT_FIRST else 0)
        scope = "problem" if "problem" in ITEM_SCOPES[itype] and graph.chief() else "encounter"
        source = WHO[who] or DENTIST_SOURCE.get(itype, "clinician_assessment")
        draft = Item(id="new", type=itype, scope=scope, problem_id=graph.chief().id if scope == "problem" else None,
                     owner="human", assertion_source=source)
        changes = field_form(draft, f"add_{itype}")
        comment = st.text_input("Comment (optional)", key="add_note", placeholder="Where did you hear or see it?")
        if st.button("Add to the note", key="add_btn", type="primary"):
            if not changes.get("attributes") and not changes.get("target"):
                notify("add_btn", "error", "Fill in at least one detail above first.")
            else:
                guarded("add_btn", human.add_entity, session,
                        {"kind": "item", "type": itype, "scope": scope, "problem_id": draft.problem_id,
                         "target": changes.get("target", {"tooth": None}), "attributes": changes.get("attributes", {}),
                         "assertion": changes.get("assertion", "present"), "time_context": "current",
                         "assertion_source": source}, role, comment.strip() or f"Added by the {role.lower()}",
                        doing="add that", done=_saved_text(draft, "Added to the note."))
            st.rerun()
        show_notice("add_btn")


def technical_details(graph, latest):
    with st.expander("Technical details"):
        status = latest.get("status") or {}
        st.caption(f"graph v{graph.version} · verification {status.get('verification_level')} · "
                   f"rule mode {status.get('rule_mode')} · notices: {'; '.join(latest.get('notices', []))}")
        if approval.load_state(session).state not in APPROVED:
            _act("Refresh clinical review questions", "retry_e3", derive, session, graph, load_sources(session),
                 graph.pipeline_mode, session.meta().get("rule_mode"), retry_e3=True, done="Refreshed.")
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


# ---------------------------------------------------------------- worklists

def _worklist_header(*titles, widths):
    for col, title in zip(st.columns(widths), titles):
        col.caption(title)


def waiting_page():
    rows = worklists(sessions, st.session_state.get("show_tests", False))["waiting"]
    st.subheader("Waiting for dentist")
    if not rows:
        st.info("Nothing is waiting for the dentist. Notes appear here after you send them.")
        return
    st.caption(f"{_items(len(rows)).replace('item', 'note')} reviewed and sent, not approved yet. Longest wait first.")
    widths = [4, 2, 3, 2, 2]
    _worklist_header("Patient", "Visit date", "Dentist", "Waiting", "", widths=widths)
    for r in rows:
        c = st.columns(widths, vertical_alignment="center")
        c[0].markdown(f"**{esc(r['patient'])}**")
        c[1].write(r["date"])
        c[2].write(r["dentist"])
        c[3].write(waiting_text(r["since"]))
        if c[4].button("Open" if role == "Assistant" else "Review and approve", key=f"open_w_{r['session'].id}",
                       width="stretch", type="secondary" if role == "Assistant" else "primary"):
            go("Review", r["session"].id)


def cleared_page():
    rows = worklists(sessions, st.session_state.get("show_tests", False))["cleared"]
    st.subheader("Cleared by dentist")
    if not rows:
        st.info("No approved notes yet. Notes appear here once the dentist approves them.")
        return
    st.caption("Approved notes, newest first.")
    widths = [4, 2, 3, 2, 2, 2, 2, 2]
    _worklist_header("Patient", "Visit date", "Dentist", "Approved", "Download", "", "", "", widths=widths)
    for r in rows[:MAX_LISTED]:
        s = r["session"]
        stem = exports.file_stem(s)
        c = st.columns(widths, vertical_alignment="center")
        c[0].markdown(f"**{esc(r['patient'])}**")
        c[1].write(r["date"])
        c[2].write(r["dentist"])
        c[3].write(clock(r["since"]))
        c[4].download_button("PDF", lambda s=s: exports.note_pdf(s), file_name=f"{stem} note.pdf",
                             mime=exports.PDF_MIME, type="primary", key=f"pdf_{s.id}", on_click="ignore",
                             width="stretch", help="Download the note as a PDF")
        c[5].download_button("Word", lambda s=s: exports.note_docx(s), file_name=f"{stem} note.docx",
                             mime=exports.DOCX_MIME, key=f"docx_{s.id}", on_click="ignore", width="stretch",
                             help="Download the note as a Word document")
        c[6].download_button("Everything", lambda s=s: exports.bundle_zip(s), file_name=f"{stem}.zip",
                             mime="application/zip", key=f"zip_{s.id}", on_click="ignore", width="stretch",
                             help="A zip with the note, the transcript and the recording")
        if c[7].button("Open", key=f"open_c_{s.id}", width="stretch"):
            go("Review", s.id)
    if len(rows) > MAX_LISTED:
        st.caption(f"Showing the newest {MAX_LISTED} of {len(rows)}. Use the search on the left for older visits.")


# ---------------------------------------------------------------- pages

PAGES = {"New visit": new_visit_page, "Review": review_page, "Waiting for dentist": waiting_page,
         "Cleared by dentist": cleared_page, "Admin": admin_page}
for _name, _tab in zip(TABS, st.tabs(TABS, key="page", on_change="rerun")):
    if _tab.open:
        with _tab:
            PAGES[_name]()
st.session_state.pop("notices", None)  # a message is shown once, beside its button
