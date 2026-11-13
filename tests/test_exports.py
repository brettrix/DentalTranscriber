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


def _with_recording(s, seconds=(0.0, 3.2, 62.0, 101.9)):
    """Make the session look like an audio visit: a recording file and times on the first lines."""
    import json
    s.path("sources", "audio.wav").write_bytes(b"RIFF....WAVEfmt fake audio bytes")
    path = s.path("sources", "utterances.json")
    data = json.loads(path.read_text())
    for u, start in zip(data["utterances"], seconds):
        u["start"], u["end"] = start, start + 2.0
    path.write_text(json.dumps(data))


def test_transcript_has_speaker_names_and_timestamps_only_for_recordings(tmp_path):
    s = mini_session(tmp_path, "baseline")
    s.update_meta(patient="Ana Ruiz")
    text = exports.transcript_text(s)
    assert text.startswith("Visit transcript: Ana Ruiz\nDate: 2026-11-12\nDentist: Dr. Test\n")
    assert "\nDentist: What brings you in today?\nPatient: My upper left tooth hurts with cold.\n" in text
    assert "[" not in text, "a pasted transcript has no times"
    assert "Quick notes:\n- BP 124/80" in text
    assert not exports.has_timestamps(s) and exports.recording_path(s) is None

    timed = mini_session(tmp_path, "baseline")
    _with_recording(timed)
    assert exports.has_timestamps(timed) and exports.recording_path(timed).name == "audio.wav"
    text = exports.transcript_text(timed)
    assert "[00:00] Dentist: What brings you in today?" in text and "[00:03] Patient: My upper left" in text
    assert "[01:02] Dentist: Any allergies" in text and "[01:41] Patient: Penicillin gives me hives." in text
    assert exports.stamp(3725) == "1:02:05"
    pdf = _pdf_text(exports.transcript_pdf(timed))
    assert "01:41" in pdf and "Patient:" in pdf and "Penicillin gives me hives." in pdf


def test_download_everything_is_one_folder_named_for_the_patient_and_date(tmp_path):
    s = _approved(tmp_path, patient="Maria Lopez/4417")
    with zipfile.ZipFile(io.BytesIO(exports.bundle_zip(s))) as z:
        assert sorted(z.namelist()) == [f"Maria Lopez-4417 2026-11-12/{n}" for n in
                                        ("note.docx", "note.pdf", "transcript.pdf", "transcript.txt")]
        assert z.read("Maria Lopez-4417 2026-11-12/note.pdf").startswith(b"%PDF-")

    rec = mini_session(tmp_path, "baseline")
    rec.update_meta(patient="Ben Cho")
    _with_recording(rec)
    run_pipeline(rec, mode="baseline", client=FakeLLM())
    approval.force_approve_for_test(rec)
    with zipfile.ZipFile(io.BytesIO(exports.bundle_zip(rec))) as z:
        names = sorted(n.split("/", 1)[1] for n in z.namelist())
        assert names == ["note.docx", "note.pdf", "recording.wav", "transcript.pdf", "transcript.txt"]
        assert all(n.startswith("Ben Cho 2026-11-12/") for n in z.namelist())
        assert z.read("Ben Cho 2026-11-12/recording.wav") == rec.path("sources", "audio.wav").read_bytes()
        assert b"[00:03] Patient:" in z.read("Ben Cho 2026-11-12/transcript.txt")
