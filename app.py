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
from pipeline.visits import filter_visits, visit_heading, visit_name, visit_when
from schemas.entities import ATTRIBUTE_MODELS, ITEM_SCOPES, Item, is_critical
from schemas.flags import Flag

BANNER = "Prototype — test data only. Do not use with real patient information."
MAX_LISTED = 60
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


# ---------------------------------------------------------------- sidebar: role and visit

role = st.sidebar.selectbox("Your role (Prototype: no real login)", ["Assistant", "Dentist"])
sessions = list_sessions()  # newest first
by_id = {s.id: s for s in sessions}
st.sidebar.markdown("""<style>
section[data-testid='stSidebar'] { min-width: 330px; }
section[data-testid='stSidebar'] [class*='st-key-visit_'] button { justify-content: flex-start; text-align: left; }
</style>""", unsafe_allow_html=True)
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
    provider = c2.text_input("Dentist", "")
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
    st.markdown(f"### {esc(visit_heading(session))}")
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


CARD_CSS = """<style>
[data-testid="stButtonGroup"] button { white-space: nowrap; }
[data-testid="stButtonGroup"] button p { white-space: nowrap; }
[data-testid="stButtonGroup"] button[data-selected] { background: #1f8a3b !important; border-color: #1f8a3b !important;
  color: #fff !important; }
[data-testid="stButtonGroup"] button[data-selected] p { color: #fff !important; }
</style>"""
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
        c1, c2 = st.columns(2)
        with c1.container(border=True):
            st.caption(card["left"][0])
            st.markdown(esc(card["left"][1]).replace("\n", "  \n"))
        with c2.container(border=True):
            st.caption(card["right"][0])
            st.markdown(esc(card["right"][1]).replace("\n", "  \n"))
        kw = {} if key in st.session_state else {"default": card["default"]}
        st.segmented_control("Your choice", list(labels), key=key, label_visibility="collapsed", width="content",
                             format_func=lambda v, k=key: ("\u2713 " if st.session_state.get(k) == v else "") + labels[v],
                             **kw)
        with st.expander("Details"):
            for d in card["details"]:
                st.caption(esc(d))


def checklist(graph, flag_by_id, log, reason):
    """Review cards: choose on each card, then save everything at once."""
    st.markdown(CARD_CSS, unsafe_allow_html=True)
    target = "assistant" if role == "Assistant" else "dentist"
    items = approval.blocker_items(session, target)
    staging = session_staging(session)
    src = load_sources(session)
    cards = plain.build_cards(items, graph, log, staging, src, role, flag_by_id)
    shown = [c for c in cards if not c["hidden"]]
    hidden = [c for c in cards if c["hidden"]]
    title = "Before you mark your review complete" if target == "assistant" else "Before you approve the note"
    st.subheader(f"{title}" if cards else f"{title}: nothing left to do \u2713")
    for card in shown:
        _render_card(card)
    if hidden:
        n = len(hidden)
        with st.expander(f"{n} more {'item looks' if n == 1 else 'items look'} right \u00b7 show"):
            for card in hidden:
                _render_card(card)
    if cards:
        answered = sum(1 for c in cards if st.session_state.get(_card_key(c)) is not None)
        c1, c2, c3 = st.columns([2, 2, 4])
        c1.markdown(f"**{answered} of {len(cards)} answered**")
        save = c2.button("Save my review", type="primary", disabled=answered < len(cards), key="save_review")
        if answered < len(cards):
            c3.caption("Answer every item first")
        if save:
            choices = []
            for c in cards:
                v = st.session_state.get(_card_key(c))
                choices += next(ops for val, _, ops in c["options"] if val == v)
            out = guarded(human.apply_review, session, choices, role, reason)
            if out and isinstance(out, dict) and out.get("errors"):
                st.session_state["flash_error"] = "Some choices couldn't be applied: " + "; ".join(
                    plain.strip_ids(e) for e in out["errors"])
            for c in cards:
                st.session_state.pop(_card_key(c), None)
            st.rerun()
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
    return any(t == title or t.startswith(title + " \u2014") for t in covered["titles"])


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
        st.caption("Highlighted in the conversation on the right.")
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
