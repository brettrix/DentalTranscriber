"""Drive the Streamlit UI through the human checkpoint: flags, item edit, assistant review, dentist approval, export."""
import os

from streamlit.testing.v1 import AppTest

import pipeline.storage as storage
from pipeline import approval
from pipeline.graph import load_graph
from pipeline.orchestrator import run_pipeline
from tests.fake_llm import FakeLLM, mini_session

os.environ["SCRIBE_NO_SLEEP"] = "1"


def _app(monkeypatch, tmp_path, role):
    monkeypatch.setattr(storage, "SESSIONS_DIR", tmp_path)
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    at.sidebar.selectbox[1].set_value(at.sidebar.selectbox[1].options[1]).run()
    at.sidebar.selectbox[0].set_value(role).run()
    assert not at.exception, at.exception
    return at


def _button(at, label):
    return next(b for b in at.button if b.label == label)


def test_ui_edit_review_approve_export(monkeypatch, tmp_path):
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    rx = next(e for e in load_graph(s).active("item") if e.type == "prescription")

    at = _app(monkeypatch, tmp_path, "Dentist")
    assert any("Prototype — test data only" in e.value for e in at.error), "banner on the page"
    assert any(x.label.startswith("[low · question] endo_findings_review") for x in at.expander), "flags shown"
    # Edit an item through the note's Edit toggle.
    next(t for t in at.toggle if t.key == f"tg{rx.id}").set_value(True).run()
    editor = next(t for t in at.text_area if t.key == f"ed{rx.id}")
    editor.set_value(editor.value.replace('"600 mg"', '"400 mg"')).run()
    next(t for t in at.text_input if t.key == f"rs{rx.id}").set_value("dose corrected by dentist").run()
    next(b for b in at.button if b.key == f"sv{rx.id}").click().run()
    assert not at.exception, at.exception
    edited = load_graph(s).get(rx.id)
    assert edited.attributes["strength"] == "400 mg" and edited.owner == "human"

    at = _app(monkeypatch, tmp_path, "Assistant")
    _button(at, "Assistant review complete").click().run()
    assert approval.load_state(s).state == "assistant_review_complete"

    at = _app(monkeypatch, tmp_path, "Dentist")
    _button(at, "Dentist approve").click().run()
    assert approval.load_state(s).state == "dentist_approved"
    _button(at, "Export").click().run()
    assert not at.exception, at.exception
    assert approval.load_state(s).state == "exported"
