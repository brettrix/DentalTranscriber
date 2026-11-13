"""Exports for the assistant: PDF, Word, plain text, transcript, zip bundle (offline)."""
import io
import zipfile

import pytest

from pipeline import approval, exports
from pipeline.orchestrator import run_pipeline
from tests.fake_llm import FakeLLM, mini_session


def _approved(tmp_path, patient="Maria Lopez 4417"):
    s = mini_session(tmp_path, "baseline")
    s.update_meta(patient=patient)
    from pipeline.transcribe import write_visit_meta
    write_visit_meta(s, date="2026-11-12", provider="Dr. Test", assistant="Kirstin")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    approval.force_approve_for_test(s)
    return s


def _pdf_text(data: bytes) -> str:
    """Text of a PDF made by fpdf2 (uncompressed here), enough to check what a reader would see."""
    import re
    import zlib
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        raw = m.group(1)
        try:
            raw = zlib.decompressobj().decompress(raw)  # tolerant of a trailing byte lost to the pattern above
        except zlib.error:
            pass
        for t in re.findall(rb"\((.*?)(?<!\\)\)\s*Tj", raw, re.S):
            out.append(t.replace(rb"\(", b"(").replace(rb"\)", b")").decode("latin-1"))
    return " ".join(out)


def test_plain_text_note_has_header_note_and_approval_line(tmp_path):
    s = _approved(tmp_path)
    text = exports.note_text(s)
    assert text.startswith("Limited exam note\nPatient: Maria Lopez 4417\nDate: 2026-11-12\nDentist: Dr. Test\n"
                           "Assistant: Kirstin\n")
    assert "\nASSESSMENT\n- Reversible pulpitis #14\n" in text and "- Allergy: penicillin (hives)" in text
    assert "\nNot discussed: " in text
    assert text.rstrip().splitlines()[-1].startswith("Approved by Dr. Test on ")
    assert "#" not in text.split("\n")[0] and "**" not in text and "it_" not in text, "plain text, not Markdown"


def test_pdf_is_a_printable_chart_note(tmp_path):
    s = _approved(tmp_path)
    data = exports.note_pdf(s)
    assert data.startswith(b"%PDF-")
    text = _pdf_text(data)
    for want in ("Limited exam note", "Patient:", "Maria Lopez 4417", "Visit date:", "2026-11-12", "Dentist:",
                 "Dr. Test", "Assistant:", "Kirstin", "Assessment", "Reversible pulpitis #14",
                 "Approved by Dr. Test on", "Prototype - test data only"):
        assert want in text, (want, text[:400])


def test_pdf_survives_names_and_punctuation_outside_latin1(tmp_path):
    s = _approved(tmp_path, patient="Nguyễn Thị “Lily” — #88")
    assert "Nguyen Thi \"Lily\" - #88" in _pdf_text(exports.note_pdf(s))


def test_word_note_has_the_same_content(tmp_path):
    from docx import Document
    s = _approved(tmp_path)
    doc = Document(io.BytesIO(exports.note_docx(s)))
    paras = [p.text for p in doc.paragraphs]
    cells = [c.text for row in doc.tables[0].rows for c in row.cells]
    assert cells == ["Patient: Maria Lopez 4417", "Visit date: 2026-11-12", "Dentist: Dr. Test", "Assistant: Kirstin"]
    assert "Reversible pulpitis #14" in paras and any(p.startswith("Approved by Dr. Test on ") for p in paras)
    assert any(p.style.name == "List Bullet" for p in doc.paragraphs)


def test_note_is_refused_unless_approved_and_unchanged(tmp_path):
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    for make in (exports.note_pdf, exports.note_docx, exports.note_text, exports.bundle_zip):
        with pytest.raises(exports.NotApproved):
            make(s)
    approval.force_approve_for_test(s)
    assert exports.note_pdf(s)
    from pipeline.transcribe import write_quick_notes
    write_quick_notes(s, "BP 180/110")  # a source changed after approval
    with pytest.raises(exports.NotApproved):
        exports.note_pdf(s)
    assert approval.load_state(s).state == "draft", "the stale approval is undone"
