"""UI fixes: no sidebar tooltip or stale highlight, labels that never truncate, prescription editor order,
one-paragraph transcripts split by speaker (offline)."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

import pipeline.storage as storage
from pipeline import approval
from pipeline.graph import load_graph
from pipeline.orchestrator import run_pipeline
from pipeline.transcribe import parse_text_transcript, split_speakers
from tests.fake_llm import MINI_TRANSCRIPT, FakeLLM, mini_session

ROOT = Path(__file__).resolve().parent.parent


def _app(monkeypatch, tmp_path, role="Assistant", page="Review"):
    monkeypatch.setattr(storage, "SESSIONS_DIR", tmp_path)
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.session_state["page"] = page
    at.run()
    at.sidebar.selectbox[0].set_value(role).run()
    assert not at.exception, at.exception
    return at


def _visit(tmp_path, patient="Ana Ruiz"):
    s = mini_session(tmp_path, "baseline")
    s.update_meta(patient=patient)
    run_pipeline(s, mode="baseline", client=FakeLLM())
    return s


def _visit_buttons(at):
    return [b for b in at.sidebar.button if (b.key or "").startswith("visit_")]


def test_sidebar_visits_have_no_tooltip(monkeypatch, tmp_path):
    _visit(tmp_path)
    _visit(tmp_path, "Ben Cho")
    at = _app(monkeypatch, tmp_path)
    assert len(_visit_buttons(at)) == 2
    assert all(not b.proto.help for b in _visit_buttons(at)), "a tooltip stayed over the row above and blocked clicks"


def test_no_visit_is_highlighted_while_new_visit_is_open(monkeypatch, tmp_path):
    s = _visit(tmp_path)
    at = _app(monkeypatch, tmp_path, page="Review")
    assert [b.proto.type for b in _visit_buttons(at)] == ["primary"], "the open visit is highlighted on Review"
    next(b for b in at.sidebar.button if b.key == "new_visit").click().run()
    assert at.session_state["page"] == "New visit"
    assert [b.proto.type for b in _visit_buttons(at)] == ["secondary"], "cleared while a new visit is entered"
    _visit_buttons(at)[0].click().run()
    assert at.session_state["sid"] == s.id and [b.proto.type for b in _visit_buttons(at)] == ["primary"]


def test_labels_are_whole_and_rows_wrap(monkeypatch, tmp_path):
    s = _visit(tmp_path)
    approval.force_approve_for_test(s)
    at = _app(monkeypatch, tmp_path, page="Cleared by dentist")
    assert [d.label for d in at.get("download_button")] == ["Download PDF", "Word (.docx)", "Everything (.zip)"], \
        "full labels, not single letters squeezed into table columns"
    assert any(b.label == "Open" for b in at.button)
    css = " ".join(m.value for m in at.markdown if "<style>" in m.value)
    assert "white-space: normal !important" in css and "text-overflow: clip !important" in css
    assert "flex-wrap: wrap !important" in css, "answer buttons wrap instead of scrolling sideways"
    at = _app(monkeypatch, tmp_path, page="Review")
    assert [d.label for d in at.get("download_button")] == ["Download PDF", "Word (.docx)",
                                                            "Download everything (.zip)", "Transcript (PDF)",
                                                            "Transcript (text)"]


def test_prescription_editor_starts_with_the_drug_and_has_no_tooth(monkeypatch, tmp_path):
    s = _visit(tmp_path)
    g = load_graph(s)
    rx = next(e for e in g.active("item") if e.type == "prescription")
    finding = next(e for e in g.active("item") if e.type == "finding")
    at = _app(monkeypatch, tmp_path, role="Dentist")
    next(b for b in at.button if b.key == f"edit_{rx.id}").click().run()
    fields = [t for t in at.text_input if (t.key or "").startswith(f"f_{rx.id}_")]
    assert fields[0].key == f"f_{rx.id}_drug" and fields[0].label == "Drug" and fields[0].value == "ibuprofen"
    assert not any(t.key == f"f_{rx.id}_tooth" for t in at.text_input), "a prescription has no tooth"
    next(b for b in at.button if b.key == f"edit_{rx.id}").click().run()
    next(b for b in at.button if b.key == f"edit_{finding.id}").click().run()
    assert any(t.key == f"f_{finding.id}_tooth" for t in at.text_input), "an exam finding still has its tooth"


def test_one_paragraph_transcript_is_split_by_speaker():
    para = ("Dentist: What brings you in today? PATIENT: My upper left tooth hurts with cold. dentist: Any allergies "
            "to medications? Patient [S1]: Penicillin gives me hives. Assistant: BP is 124 over 80.")
    lines = split_speakers(para).splitlines()
    assert lines == ["Dentist: What brings you in today?", "PATIENT: My upper left tooth hurts with cold.",
                     "dentist: Any allergies to medications?", "Patient [S1]: Penicillin gives me hives.",
                     "Assistant: BP is 124 over 80."]
    utterances, roles = parse_text_transcript(split_speakers(para))
    assert len(utterances) == 5 and {r.role for r in roles.values()} == {"Dentist", "Patient", "Assistant"}
    assert split_speakers(MINI_TRANSCRIPT) == MINI_TRANSCRIPT.rstrip("\n"), "already one per line: unchanged"
    said = "PATIENT: The other doctor said: wait and see. I asked my dentist, and she agreed."
    assert split_speakers(said) == said, "a speaker label needs a colon right after the role word"


def test_existing_case_transcripts_are_untouched_by_the_splitter():
    files = sorted((ROOT / "eval").glob("*/*/transcript.txt"))
    assert len(files) > 20
    for f in files:
        text = f.read_text("utf-8")
        assert split_speakers(text).splitlines() == text.splitlines(), f


def test_pasting_a_paragraph_makes_a_normal_visit(monkeypatch, tmp_path):
    at = _app(monkeypatch, tmp_path, page="New visit")
    next(r for r in at.radio if r.key == "nv_input").set_value("Paste a transcript").run()
    next(t for t in at.text_input if t.key == "nv_patient").set_value("Ruth 2210").run()
    next(t for t in at.text_area if t.key == "nv_transcript").set_value(" ".join(MINI_TRANSCRIPT.split("\n"))).run()
    next(b for b in at.button if b.label == "Write the note").click().run()
    assert not at.exception, at.exception
    s = storage.list_sessions(tmp_path)[0]
    from pipeline.overlays import load_sources
    assert len(load_sources(s).utterances.utterances) == 10, "ten speaker turns, not one long line"
    assert load_graph(s) is not None and at.session_state["page"] == "Review"
