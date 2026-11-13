"""Drive the Streamlit review page as an assistant and a dentist (offline: fake model client, network blocked)."""
import copy
import os
import re

from streamlit.testing.v1 import AppTest

import pipeline.storage as storage
from pipeline import approval
from pipeline.graph import load_graph
from pipeline.orchestrator import run_pipeline
from tests.fake_llm import ITEMS, FakeLLM, mini_session, q

os.environ["SCRIBE_NO_SLEEP"] = "1"
ID = re.compile(r"\b(?:it_\d+|pb_\w+|rl_\w+|tk_\w+|st_\w+|cf_\w+|pc_\w+)\b")
JARGON = re.compile(r"\b(span|norm|derivation|registry_issue|unsupported_content|semantic)\b", re.I)

V2 = {"key": "V2", "type": "vital_reading", "attributes": {"systolic": 150, "diastolic": 95, "sequence": 2},
      "assertion_source": "clinician_observation", "evidence": [q("u10", "Blood pressure is 150 over 95.")],
      "derivations": [{"attribute": "attributes.systolic", "rule": "bp_reading", "from": "150 over 95", "to": 150},
                      {"attribute": "attributes.diastolic", "rule": "bp_reading", "from": "150 over 95", "to": 95}]}


def _app(monkeypatch, tmp_path, role, page="Review"):
    monkeypatch.setattr(storage, "SESSIONS_DIR", tmp_path)
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.session_state["page"] = page
    at.run()
    at.sidebar.selectbox[0].set_value(role).run()
    assert not at.exception, at.exception
    return at


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def _checklist(at):
    return [m.value for m in at.markdown if m.value.startswith("☐")]


def test_ui_edit_review_approve_export(monkeypatch, tmp_path):
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    rx = next(e for e in load_graph(s).active("item") if e.type == "prescription")
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert any("Prototype — test data only" in e.value for e in at.error), "banner on the page"
    assert any("Review" in m.value or "Alerts" in m.value for m in at.subheader)
    next(t for t in at.toggle if t.key == f"edit_{rx.id}").set_value(True).run()
    next(t for t in at.text_input if t.key == f"f_{rx.id}_strength").set_value("400 mg").run()
    next(b for b in at.button if b.key == f"save_{rx.id}").click().run()
    assert not at.exception, at.exception
    edited = load_graph(s).get(rx.id)
    assert edited.attributes["strength"] == "400 mg" and edited.owner == "human"

    at = _app(monkeypatch, tmp_path, "Assistant")
    _button(at, "Mark my review complete").click().run()
    assert approval.load_state(s).state == "assistant_review_complete"
    at = _app(monkeypatch, tmp_path, "Dentist")
    _button(at, "Approve the note").click().run()
    assert approval.load_state(s).state == "dentist_approved"
    _button(at, "Export").click().run()
    assert not at.exception and approval.load_state(s).state == "exported"


def test_checklist_is_plain_and_one_click(monkeypatch, tmp_path):
    items = {**copy.deepcopy(ITEMS), "V2": V2}
    items["F1"]["evidence"][0]["quote"] = "Cold on tooth fourteen."   # fails the quote check -> needs confirming
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items))
    at = _app(monkeypatch, tmp_path, "Dentist")
    lines = _checklist(at)
    assert lines, "the dentist has items to clear"
    text = " ".join(lines) + " " + " ".join(m.value for m in at.markdown if m.value.startswith(("🛑", "❓", "•")))
    assert not ID.search(text), f"internal ids shown: {ID.findall(text)}"
    assert not JARGON.search(text), f"jargon shown: {JARGON.findall(text)}"
    assert any("Blood pressure doesn't match the quick note (150/95 said vs 124/80 written)" in l for l in lines)
    assert any(l.startswith("☐ Confirm: Exam finding") for l in lines)
    alert_lines = [m.value[2:] for m in at.markdown if m.value.startswith(("🛑 ", "❓ ", "• "))]
    for a in alert_lines:
        assert not any(l[2:] == a or l[2:].startswith(a + " \u2014") for l in lines), f"shown twice: {a}"
    assert not any("Blood pressure doesn't match" in a for a in alert_lines)
    assert len(alert_lines) == len(set(alert_lines)), "each alert once"
    before = len(lines)
    next(b for b in at.button if b.label.startswith("Keep: BP 150/95")).click().run()
    assert not at.exception, at.exception
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert not any("Blood pressure doesn't match" in l for l in _checklist(at))
    confirm = next(b for b in at.button if b.label == "Confirm")
    confirm.click().run()
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert len(_checklist(at)) <= before - 2


def test_assistant_sends_critical_item_to_dentist(monkeypatch, tmp_path):
    items = copy.deepcopy(ITEMS)
    items["F1"]["evidence"][0]["quote"] = "Cold on tooth fourteen."
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items))
    at = _app(monkeypatch, tmp_path, "Assistant")
    assert any(l.startswith("☐ Confirm: Exam finding") for l in _checklist(at))
    next(b for b in at.button if b.label == "Send to dentist").click().run()
    at = _app(monkeypatch, tmp_path, "Assistant")
    assert not any(l.startswith("☐ Confirm: Exam finding") for l in _checklist(at)), "cleared for the assistant"
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert any(l.startswith("☐ Confirm: Exam finding") for l in _checklist(at)), "still on the dentist's list"


def test_process_selects_new_visit_and_opens_review(monkeypatch, tmp_path):
    old = mini_session(tmp_path, "baseline")
    run_pipeline(old, mode="baseline", client=FakeLLM())
    at = _app(monkeypatch, tmp_path, "Assistant", page="Start")
    next(r for r in at.radio if r.label == "Input").set_value("Test case").run()
    _button(at, "Process").click().run()
    assert not at.exception, at.exception
    assert at.session_state["page"] == "Review"
    sessions = storage.list_sessions(tmp_path)
    assert at.session_state["sid"] == sessions[0].id != old.id, "the new visit is selected"
    labels = at.sidebar.selectbox[1].options
    assert re.match(r"case1 · \w{3} \d{2} \d{2}:\d{2} · baseline$", labels[1]), labels[:3]
    assert any("processed" in c.value and "baseline mode" in c.value for c in at.sidebar.caption)


def test_signoff_buttons_only_while_they_apply(monkeypatch, tmp_path):
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert not any(b.label in ("Approve the note", "Export") for b in at.button), "nothing to sign before the assistant"
    at = _app(monkeypatch, tmp_path, "Assistant")
    _button(at, "Mark my review complete").click().run()
    at = _app(monkeypatch, tmp_path, "Assistant")
    assert not any(b.label == "Mark my review complete" for b in at.button)
    at = _app(monkeypatch, tmp_path, "Dentist")
    _button(at, "Approve the note").click().run()
    at = _app(monkeypatch, tmp_path, "Assistant")
    assert not any(b.label == "Mark my review complete" for b in at.button), "hidden once approved"
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert not any(b.label == "Approve the note" for b in at.button)
    _button(at, "Export").click().run()
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert not any(b.label == "Export" for b in at.button)
    assert any("Approved and exported (Dentist" in c.value for c in at.caption)
