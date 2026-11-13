"""Streamlit UI (section 13): start, role confirmation, review with item editor and approvals, trace."""
from __future__ import annotations

import html
import json
import tempfile
from pathlib import Path

import streamlit as st

from pipeline import approval, human
from pipeline.graph import load_graph
from pipeline.linker import session_staging
from pipeline.orchestrator import RolesNotConfirmed, derive, load_latest, run_pipeline
from pipeline.overlays import confirm_roles, load_sources
from pipeline.stage_runs import session_stage_log
from pipeline.storage import ROOT, Session, SessionBusy, list_sessions
from pipeline.trace import read_traces
from pipeline.transcribe import transcribe_audio, transcribe_text, write_quick_notes, write_visit_meta
from pipeline.validate import StructuralError
from schemas.entities import ATTRIBUTE_MODELS

BANNER = "Prototype — test data only. Do not use with real patient information."
ICON = {"succeeded": "✓", "failed": "✗", "blocked": "⏸", "not_applicable": "–"}

st.set_page_config(page_title="Dental Scribe (prototype)", layout="wide")


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


# ---------------------------------------------------------------- sidebar: role and session

role = st.sidebar.selectbox("Role (Prototype: no real login)", ["Assistant", "Dentist"])
sessions = list_sessions()
labels = ["(new session)"] + [f"{s.meta().get('case') or 'session'} · {s.meta().get('pipeline_mode')} · {s.id[:8]}"
                              for s in sessions]
pick = st.sidebar.selectbox("Session", labels, index=1 if sessions and "sid" in st.session_state else 0)
session = None
if pick != "(new session)":
    session = sessions[labels.index(pick) - 1]
    st.session_state["sid"] = session.id

meta = session.meta() if session else {}
st.error(f"{BANNER}  ·  Pipeline: {meta.get('pipeline_mode', '—')}  ·  Rule mode: {meta.get('rule_mode', '—')}")


def rerun_ui():
    st.rerun()


def guarded(fn, *args, **kw):
    try:
        out = fn(*args, **kw)
        st.success("Saved.")
        return out
    except (human.HumanActionError, StructuralError, approval.ApprovalBlocked, approval.ExportRefused,
            SessionBusy, RolesNotConfirmed, ValueError) as exc:
        st.error(f"Rejected: {exc}")
        if isinstance(exc, approval.ApprovalBlocked):
            for r in exc.reasons:
                st.write(f"- {esc(r)}")
        return None


tab_start, tab_roles, tab_review, tab_trace = st.tabs(["Start", "Role confirmation", "Review", "Trace"])

# ---------------------------------------------------------------- Start

with tab_start:
    st.subheader("New visit")
    c1, c2, c3 = st.columns(3)
    date = c1.text_input("Date", "2026-11-12")
    provider = c2.text_input("Provider", "Dr. Hale")
    assistant = c3.text_input("Assistant", "")
    mode = st.radio("Pipeline mode", ["team", "baseline"], horizontal=True)
    rule_mode = st.radio("Rule mode", ["synthetic_demo", "office"], horizontal=True)
    source = st.radio("Input", ["Paste transcript", "Upload audio", "Test case"], horizontal=True)
    quick = st.text_area("Quick notes (one per line)", height=100)
    transcript, audio, case_dir = None, None, None
    if source == "Paste transcript":
        transcript = st.text_area("Transcript (lines like 'DENTIST: …', 'PATIENT: …')", height=200)
    elif source == "Upload audio":
        audio = st.file_uploader("Audio (wav, mp3, m4a, flac; ≤ 50 MB; ≤ 30 min)", type=["wav", "mp3", "m4a", "flac"])
    else:
        cases = sorted(p for p in (ROOT / "eval" / "cases").iterdir() if p.is_dir())
        names = [p.name for p in cases]
        chosen = st.selectbox("Test case", names)
        case_dir = cases[names.index(chosen)] if chosen else None
    if st.button("Process", type="primary"):
        s = Session.create(case=case_dir.name if case_dir else None, pipeline_mode=mode, rule_mode=rule_mode)
        st.session_state["sid"] = s.id
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
            st.error(f"Transcription failed: {exc}")
            st.stop()
        if load_sources(s).roles.confirmed:
            with st.status("Processing…", expanded=True) as status:
                result = guarded(run_pipeline, s, mode=mode, rule_mode=rule_mode)
                for r in session_stage_log(s).runs:
                    st.write(f"{ICON.get(r['status'], '?')} {r['stage']}/{r['agent']} {r['status']}"
                             + (f" — {esc(r['error'])}" if r.get("error") else ""))
                status.update(label="Done", state="complete")
        else:
            st.info("Audio session created. Confirm speaker roles on the Role confirmation tab, then process.")

# ---------------------------------------------------------------- Role confirmation (audio)

with tab_roles:
    if session is None:
        st.info("Pick a session.")
    else:
        src = load_sources(session)
        speakers = sorted({u.speaker for u in src.utterances.utterances})
        st.write(f"Roles overlay v{src.roles.version} ({'confirmed' if src.roles.confirmed else 'not confirmed'}). "
                 "Several speaker ids may share a role.")
        mapping = {}
        for spk in speakers:
            sample = [u.text for u in src.utterances.utterances if u.speaker == spk][:3]
            st.markdown(f"**{spk}**: " + " / ".join(f"“{esc(t)}”" for t in sample))
            current = src.roles.entries.get(spk).role if spk in src.roles.entries else "Other"
            mapping[spk] = st.selectbox(f"Role for {spk}", ["Dentist", "Assistant", "Patient", "Other"],
                                        index=["Dentist", "Assistant", "Patient", "Other"].index(current), key=f"r{spk}")
        if st.button("Confirm roles and process"):
            confirm_roles(session, mapping, by=role)
            guarded(run_pipeline, session)
            rerun_ui()

# ---------------------------------------------------------------- Review

def entity_editor(e, key: str):
    data = e.model_dump(mode="json", by_alias=True)
    editable = {k: data[k] for k in ("target", "attributes", "assertion", "time_context", "assertion_source",
                                     "problem_id", "complaint_text", "complaint_location", "clinical_target",
                                     "tooth", "relation_kind") if k in data}
    text = st.text_area("Fields (JSON)", json.dumps(editable, indent=1), key=f"ed{key}", height=220)
    reason = st.text_input("Reason", key=f"rs{key}")
    c1, c2 = st.columns(2)
    if c1.button("Save edit", key=f"sv{key}"):
        try:
            changes = json.loads(text)
        except json.JSONDecodeError as exc:
            st.error(f"Invalid JSON: {exc}")
            return
        if guarded(human.edit_entity, session, e.id, changes, role, reason):
            rerun_ui()
    if c2.button("Remove", key=f"rm{key}"):
        if guarded(human.remove_entity, session, e.id, role, reason):
            rerun_ui()


def render_transcript(src, highlight: set[tuple[str, int | None, int | None]]):
    rows = []
    for u in src.utterances.utterances:
        text = u.text
        spans = sorted((s, e) for sid, s, e in highlight if sid == u.id and s is not None)
        if spans:
            out, pos = "", 0
            for s, e in spans:
                if s < pos:
                    continue
                out += esc(text[pos:s]) + f"<mark>{esc(text[s:e])}</mark>"
                pos = e
            out += esc(text[pos:])
        else:
            out = esc(text)
        rows.append(f"<b>{esc(u.id)}</b> <i>{esc(u.speaker)} {esc(src.role_of(u.speaker) or '?')}</i>: {out}")
    st.markdown("<br>".join(rows), unsafe_allow_html=True)


with tab_review:
    if session is None:
        st.info("Pick or create a session.")
        st.stop()
    graph = load_graph(session)
    latest = load_latest(session) or {}
    src = load_sources(session)
    state = approval.load_state(session)
    status = latest.get("status") or {}
    st.markdown(f"**State:** {state.state} · **Graph:** v{graph.version if graph else '—'} · "
                f"**Verification:** {status.get('verification_level', '—')} · **High flags:** {status.get('high_flags', 0)}"
                f" · **Safety-critical:** {status.get('safety_critical_flags', 0)} · **Open conflicts:** "
                f"{status.get('open_conflicts', 0)} · **Open tasks:** {status.get('open_tasks', 0)} · "
                f"**Incomplete sections:** {', '.join(status.get('incomplete_sections') or []) or 'none'}")
    if state.revoked:
        st.warning(f"Approval revoked earlier: {state.revoked[-1]['reason']} (changed: "
                   f"{', '.join(state.revoked[-1]['changed'])})")
    for n in latest.get("notices", []):
        st.caption(esc(n))
    if graph is None:
        st.error("No candidate graph. Enter the chief problem (registry) below to continue.")

    # Flags
    st.subheader("Flags")
    from schemas.flags import Flag
    from pipeline.flags import flag_state
    flags = [Flag.model_validate(f) for f in latest.get("flags", [])]
    from pipeline.flags import session_flag_actions
    session_flag_actions(session).apply(flags)
    for f in flags:
        stt = flag_state(f)
        label = f"[{f.severity}{' · SAFETY' if f.safety_critical else ''}{' · question' if f.question else ''}] " \
                f"{f.rule_id} — {f.message} ({stt})"
        with st.expander(label):
            st.write(f"Entities: {', '.join(f.entity_ids) or '—'} · tasks: {', '.join(f.task_ids) or '—'} · "
                     f"conflicts: {', '.join(f.conflict_ids) or '—'} · origin {f.origin} · group {f.group_id}")
            for h in f.history:
                st.caption(f"{h.timestamp} {h.by_role} {h.action}: {esc(h.reason)}")
            reason = st.text_input("Reason", key=f"fr{f.id}")
            cols = st.columns(3)
            allowed_dismiss = not (f.safety_critical and role != "Dentist")
            if role == "Assistant" and cols[0].button("Mark for dentist", key=f"fd{f.id}"):
                guarded(human.flag_action, session, f.id, "for_dentist", role, reason)
                rerun_ui()
            if allowed_dismiss and cols[1].button("Dismiss", key=f"fx{f.id}"):
                guarded(human.flag_action, session, f.id, "dismiss", role, reason)
                rerun_ui()
            if cols[2].button("Comment", key=f"fc{f.id}"):
                guarded(human.flag_action, session, f.id, "comment", role, reason)
                rerun_ui()

    left, right = st.columns([3, 2])
    highlight: set = set()
    with left:
        st.subheader("Note")
        note = latest.get("note")
        if note:
            for sec in note["sections"]:
                st.markdown(f"**{esc(sec['title'])}**")
                if sec.get("status_line"):
                    st.caption(esc(sec["status_line"]))
                for line in sec["lines"]:
                    eid = line.get("entity_id")
                    if not eid:
                        st.write(f"- {line['text']}")
                        continue
                    c1, c2 = st.columns([6, 1])
                    c1.markdown(f"- {esc(line['text'])}  `{esc(eid)}` · <small>{esc(line['marker'])}</small>",
                                unsafe_allow_html=True)
                    if c2.toggle("Edit", key=f"tg{eid}"):
                        e = graph.get(eid)
                        for s in e.evidence:
                            highlight.add((s.source_id, s.start, s.end))
                        with st.container(border=True):
                            st.caption("Evidence: " + " | ".join(f"{esc(s.source_id)}: “{esc(s.text)}”" for s in e.evidence))
                            st.caption(f"Checks: {e.checks.model_dump()} · dispositions: {len(e.dispositions)}")
                            entity_editor(e, eid)
                            kind = "dentist_confirmed" if role == "Dentist" else "human_reviewed"
                            if st.button(f"Mark {kind.replace('_', ' ')}", key=f"cf{eid}"):
                                guarded(human.confirm_entity, session, eid, kind, role, "reviewed against sources")
                                rerun_ui()
                # Section review (failed sections, or confirming "not discussed")
                rec = next((s for s in graph.section_records if s.section == sec["id"]), None) if graph else None
                if rec is not None and (rec.status != "completed" or not sec["lines"]):
                    with st.popover(f"Review section {sec['id']}"):
                        outcome = st.radio("Outcome", ["not_discussed", "completed"], key=f"so{sec['id']}")
                        why = st.text_input("Reason", key=f"sr{sec['id']}")
                        if st.button("Record section review", key=f"sb{sec['id']}"):
                            guarded(human.review_section, session, sec["id"], outcome, role, why)
                            rerun_ui()
        with st.expander("Add item (human entry)"):
            itype = st.selectbox("Type", ["problem"] + list(ATTRIBUTE_MODELS))
            template = ({"kind": "problem", "key": "human", "role": "chief", "complaint_text": "",
                         "complaint_location": {"free_text": None, "tooth": None},
                         "clinical_target": {"tooth": None, "free_text": None},
                         "assertion_source": "clinician_assessment"} if itype == "problem" else
                        {"kind": "item", "type": itype, "scope": "problem" if graph and graph.chief() else "encounter",
                         "problem_id": graph.chief().id if graph and graph.chief() else None,
                         "target": {"tooth": None}, "attributes": {}, "assertion": "present",
                         "time_context": "current", "assertion_source": "clinician_assessment"})
            text = st.text_area("Entity (JSON)", json.dumps(template, indent=1), key=f"add{itype}", height=220)
            why = st.text_input("Reason", key="addwhy")
            if st.button("Add"):
                try:
                    data = json.loads(text)
                    if graph is None:
                        st.error("Registry entry without a graph: use the pipeline rerun after entering it.")
                    elif guarded(human.add_entity, session, data, role, why):
                        rerun_ui()
                except json.JSONDecodeError as exc:
                    st.error(f"Invalid JSON: {exc}")
    with right:
        st.subheader("Transcript")
        render_transcript(src, highlight)
        st.subheader("Quick notes")
        for q in src.quick_notes.notes:
            st.write(f"{q.id}: {q.text}")

    if graph is not None:
        st.subheader("Conflicts")
        for c in graph.conflicts:
            with st.expander(f"{c.id} · {c.kind} · {c.subject} · {c.status}"):
                st.write("Participants: " + ", ".join(f"{p.entity_id}@{p.version}" for p in c.participants))
                st.write("Evidence: " + " | ".join(f"{esc(s.source_id)}: “{esc(s.text)}”" for s in c.evidence))
                if c.later_statement:
                    st.write(f"Later statement: {esc(c.later_statement.source_id)} “{esc(c.later_statement.text)}”")
                if c.resolution:
                    st.write(f"Resolution: {c.resolution.action} by {c.resolution.resolver_role}: {esc(c.resolution.reason)}"
                             + (" (pending dentist)" if c.resolution.pending_change_id else ""))
                if c.status == "open":
                    action = st.selectbox("Action", ["select", "supersede", "keep_both"], key=f"ca{c.id}")
                    target = st.selectbox("Entity", [p.entity_id for p in c.participants], key=f"ce{c.id}")
                    expl = st.text_input("Explanation (keep_both)", key=f"cx{c.id}")
                    why = st.text_input("Reason", key=f"cr{c.id}")
                    if st.button("Resolve", key=f"cb{c.id}"):
                        guarded(human.resolve_conflict, session, c.id, action, role, why,
                                active_entity_id=target if action == "select" else None,
                                superseded_entity_id=target if action == "supersede" else None, explanation=expl)
                        rerun_ui()
        st.subheader("Review tasks")
        for t in graph.tasks:
            with st.expander(f"{t.id} · {t.kind} · {t.status} · {t.severity}"):
                st.write(esc(t.reason))
                if t.status == "open":
                    comp = st.selectbox("Completion", ["corrected", "accepted", "not_applicable"], key=f"tc{t.id}")
                    why = st.text_input("Reason", key=f"tr{t.id}")
                    if st.button("Complete task", key=f"tb{t.id}"):
                        guarded(human.complete_task, session, t.id, comp, role, why)
                        rerun_ui()
        st.subheader("Staged records (not part of the clinical draft)")
        for r in session_staging(session).open_records():
            with st.expander(f"Staged — not part of the clinical draft · {r.id} · {r.owner} {r.kind}"):
                st.code(json.dumps(r.raw, indent=1))
                st.write("Errors: " + esc("; ".join(r.errors)))
                why = st.text_input("Reason", key=f"dr{r.id}")
                if st.button("Discard", key=f"dd{r.id}"):
                    guarded(human.discard_staged, session, r.id, role, why)
                    rerun_ui()
        st.subheader("Pending dentist review")
        for pc in [p for p in graph.pending_changes if p.status == "pending"]:
            with st.expander(f"{pc.id} · {pc.operation} by {pc.by_role}: {pc.reason}"):
                st.code(json.dumps(pc.model_dump(mode="json"), indent=1))
                if role == "Dentist":
                    c1, c2 = st.columns(2)
                    if c1.button("Accept", key=f"pa{pc.id}"):
                        guarded(human.decide_pending, session, pc.id, True, role)
                        rerun_ui()
                    if c2.button("Reject", key=f"pr{pc.id}"):
                        guarded(human.decide_pending, session, pc.id, False, role)
                        rerun_ui()
        st.subheader("Human entries")
        for e in [x for x in graph.active() if x.owner == "human"]:
            st.write(f"{e.id}@{e.version}: {e.kind} {getattr(e, 'type', '')} — {esc(e.evidence[0].text)}")

    st.subheader("Approval")
    target = "assistant" if role == "Assistant" else "dentist"
    reasons = approval.blockers(session, target)
    if reasons:
        st.write(f"Blocking {'assistant review complete' if role == 'Assistant' else 'dentist approval'}:")
        for r in reasons:
            st.write(f"- {esc(r)}")
    c1, c2, c3 = st.columns(3)
    if role == "Assistant" and c1.button("Assistant review complete"):
        guarded(approval.approve_assistant, session)
        rerun_ui()
    if role == "Dentist" and c2.button("Dentist approve"):
        guarded(approval.approve_dentist, session)
        rerun_ui()
    if role == "Dentist" and c3.button("Export"):
        path = guarded(approval.export, session)
        if path:
            st.download_button("Download export", Path(path).read_bytes(), file_name=Path(path).name)
    if role == "Dentist" and st.button("Retry clinical review (E3)"):
        if graph is not None:
            derive(session, graph, src, graph.pipeline_mode, session.meta().get("rule_mode"), retry_e3=True)
            rerun_ui()

# ---------------------------------------------------------------- Trace

with tab_trace:
    if session is not None:
        rows = [r for r in read_traces(session) if r.get("kind") == "model_call"]
        st.dataframe([{k: r.get(k) for k in ("timestamp", "agent", "label", "attempt", "schema_retry", "result",
                                              "seconds", "input_tokens", "output_tokens", "model", "prompt_hash",
                                              "graph_version", "error")} for r in rows], use_container_width=True)
        st.subheader("Stage runs")
        st.dataframe(session_stage_log(session).runs, use_container_width=True)
