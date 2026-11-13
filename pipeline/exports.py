"""What the assistant downloads for a visit: the approved chart note (PDF, Word, plain text), the transcript
(text, PDF), the recording, and a zip of everything. Markdown is never offered here.

The note is only produced while the dentist's approval still matches the session (the same hash check as
`approval.export`); a note that changed after approval is refused and returns to draft.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

from pipeline import approval
from pipeline.chart import chart_sections
from pipeline.graph import load_graph
from pipeline.overlays import load_sources
from pipeline.storage import read_json
from pipeline.visits import visit_meta, visit_name

BANNER = approval.BANNER
AUDIO_MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".flac": "audio/flac"}
PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class NotApproved(RuntimeError):
    pass


# ---------------------------------------------------------------- what goes into a note

def approved_record(session):
    """The dentist's approval, if the note is approved and nothing changed since; otherwise None."""
    state = approval.load_state(session)
    if state.state not in ("dentist_approved", "exported"):
        return None
    rec = next((r for r in reversed(state.records) if r.kind == "dentist_approved"), None)
    if rec is None or approval.binding_mismatches(rec, approval.current_binding(session)):
        approval.revoke_if_changed(session, "download hash check")
        return None
    return rec


def _long_date(iso: str) -> str:
    when = datetime.fromisoformat(iso).astimezone()
    return f"{when:%b} {when.day}, {when.year} at {when:%H:%M}"


def note_content(session) -> dict:
    """Header fields, chart sections and the approval line for the approved note."""
    rec = approved_record(session)
    if rec is None:
        raise NotApproved("the note is not approved by the dentist (or changed after approval)")
    vm = visit_meta(session)
    latest = read_json(session.path("outputs", "latest.json"), {}) or {}
    chart = chart_sections(latest.get("note") or {}, load_graph(session))
    dentist = vm.get("provider") or "the dentist"
    return {"patient": visit_name(session.meta()), "date": vm.get("date") or "not recorded",
            "dentist": vm.get("provider") or "not recorded", "assistant": vm.get("assistant") or "not recorded",
            "visit_type": (vm.get("visit_type") or "limited exam").capitalize(),
            "approval": f"Approved by {dentist} on {_long_date(rec.timestamp)}", **chart}


def file_stem(session) -> str:
    """'<Patient> <date>', safe as a file or folder name."""
    stem = f"{visit_name(session.meta())} {visit_meta(session).get('date') or ''}".strip()
    return re.sub(r"[^\w .#()-]+", "-", stem).strip(" .") or "Visit"


def note_text(session) -> str:
    """Plain text for 'Copy as text' and for pasting into charting software."""
    c = note_content(session)
    out = [f"{c['visit_type']} note", f"Patient: {c['patient']}", f"Date: {c['date']}", f"Dentist: {c['dentist']}",
           f"Assistant: {c['assistant']}"]
    for sec in c["sections"]:
        out += ["", sec["title"].upper()]
        if sec["incomplete"]:
            out.append("- (could not be filled in automatically)")
        out += [f"- {line['text']}" for line in sec["lines"]]
    if c["not_discussed"]:
        out += ["", "Not discussed: " + ", ".join(c["not_discussed"])]
    out += ["", c["approval"]]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- PDF

_PDF_CHARS = {"—": "-", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
              "…": "...", "•": "-", "−": "-", "→": "->", "≥": ">=", "≤": "<=",
              " ": " ", "✓": "", "⚠": "!"}


def _latin(text) -> str:
    """The built-in PDF fonts cover Latin-1; map common punctuation and strip other accents rather than fail."""
    text = "".join(_PDF_CHARS.get(ch, ch) for ch in str(text))
    out = []
    for ch in text:
        try:
            ch.encode("latin-1")
            out.append(ch)
        except UnicodeEncodeError:
            base = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
            out.append(base or "?")
    return "".join(out)


def _pdf(title: str):
    from fpdf import FPDF

    class Doc(FPDF):
        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(120)
            self.cell(0, 5, _latin(f"{BANNER}   Page {self.page_no()} of {{nb}}"), align="C")
            self.set_text_color(0)

    pdf = Doc(format="Letter", unit="mm")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_title(_latin(title))
    pdf.add_page()
    return pdf


def _line(pdf, text: str, size=10.5, style="", height=5.2, indent=0.0, gap=0.0):
    pdf.set_font("Helvetica", style, size)
    pdf.set_x(pdf.l_margin + indent)
    pdf.multi_cell(pdf.epw - indent, height, _latin(text), new_x="LMARGIN", new_y="NEXT", align="L")
    if gap:
        pdf.ln(gap)


def _header_table(pdf, pairs: list[tuple[str, str]]):
    half = pdf.epw / 2
    for i in range(0, len(pairs), 2):
        y = pdf.get_y()
        bottom = y
        for col, (label, value) in enumerate(pairs[i:i + 2]):
            pdf.set_xy(pdf.l_margin + col * half, y)
            pdf.set_font("Helvetica", "B", 10.5)
            width = pdf.get_string_width(label + ": ") + 1
            pdf.cell(width, 5.6, _latin(label + ":"))
            pdf.set_font("Helvetica", "", 10.5)
            pdf.multi_cell(half - width - 2, 5.6, _latin(value), new_x="LMARGIN", new_y="NEXT")
            bottom = max(bottom, pdf.get_y())
        pdf.set_y(bottom)


def _rule(pdf, gap=2.5):
    pdf.ln(gap)
    pdf.set_draw_color(170)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(gap)


def note_pdf(session) -> bytes:
    """A clean, printable chart note: patient, date, dentist, assistant, the note, and the approval line."""
    c = note_content(session)
    pdf = _pdf(f"{c['patient']} {c['date']} note")
    _line(pdf, f"{c['visit_type']} note", size=16, style="B", height=8, gap=1.5)
    _header_table(pdf, [("Patient", c["patient"]), ("Visit date", c["date"]), ("Dentist", c["dentist"]),
                        ("Assistant", c["assistant"])])
    _rule(pdf)
    for sec in c["sections"]:
        if pdf.will_page_break(16):
            pdf.add_page()
        _line(pdf, sec["title"], size=11.5, style="B", height=6.2, gap=0.4)
        if sec["incomplete"]:
            _line(pdf, "(could not be filled in automatically)", style="I", indent=3)
        for line in sec["lines"]:
            y = pdf.get_y()
            if pdf.will_page_break(5.2):
                pdf.add_page()
                y = pdf.get_y()
            pdf.set_font("Helvetica", "", 10.5)
            pdf.set_xy(pdf.l_margin + 3, y)
            pdf.cell(4, 5.2, "-")
            _line(pdf, line["text"], indent=7)
        pdf.ln(2.2)
    if c["not_discussed"]:
        _line(pdf, "Not discussed: " + ", ".join(c["not_discussed"]), size=10, style="I")
    _rule(pdf, gap=3)
    _line(pdf, c["approval"], style="B")
    return bytes(pdf.output())


# ---------------------------------------------------------------- Word

def note_docx(session) -> bytes:
    from docx import Document
    from docx.shared import Pt, RGBColor

    c = note_content(session)
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Calibri", Pt(11)
    doc.core_properties.title = f"{c['patient']} {c['date']} note"
    doc.add_heading(f"{c['visit_type']} note", level=1)
    table = doc.add_table(rows=2, cols=2)
    for cell, (label, value) in zip((table.cell(0, 0), table.cell(0, 1), table.cell(1, 0), table.cell(1, 1)),
                                    (("Patient", c["patient"]), ("Visit date", c["date"]),
                                     ("Dentist", c["dentist"]), ("Assistant", c["assistant"]))):
        p = cell.paragraphs[0]
        p.add_run(f"{label}: ").bold = True
        p.add_run(value)
    for sec in c["sections"]:
        doc.add_heading(sec["title"], level=2)
        if sec["incomplete"]:
            doc.add_paragraph().add_run("(could not be filled in automatically)").italic = True
        for line in sec["lines"]:
            doc.add_paragraph(line["text"], style="List Bullet")
    if c["not_discussed"]:
        doc.add_paragraph().add_run("Not discussed: " + ", ".join(c["not_discussed"])).italic = True
    doc.add_paragraph()
    doc.add_paragraph().add_run(c["approval"]).bold = True
    run = doc.sections[0].footer.paragraphs[0].add_run(BANNER)
    run.font.size, run.font.color.rgb = Pt(8), RGBColor(0x78, 0x78, 0x78)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- transcript and recording

def stamp(seconds: float | None) -> str | None:
    """01:42 (or 1:02:05 past an hour); None when the line has no time."""
    if seconds is None:
        return None
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def recording_path(session) -> Path | None:
    return next((p for p in sorted(session.path("sources").glob("audio.*")) if p.suffix.lower() in AUDIO_MIME), None)


def has_timestamps(session, sources=None) -> bool:
    """True only for visits with a recording whose lines carry times (pasted transcripts have neither)."""
    sources = sources or load_sources(session)
    return recording_path(session) is not None and any(u.start is not None for u in sources.utterances.utterances)


def transcript_rows(session, sources=None) -> list[dict]:
    """[{time ('01:42' or None), start (seconds or None), speaker, text}] with speaker names from the roles."""
    sources = sources or load_sources(session)
    timed = has_timestamps(session, sources)
    roles = [e.role for e in sources.roles.entries.values()]
    rows = []
    for u in sources.utterances.utterances:
        role = sources.role_of(u.speaker) or f"Voice {u.speaker[1:]}"
        if roles.count(role) > 1:  # e.g. two dentists: tell the voices apart
            role = f"{role} ({u.speaker[1:]})"
        rows.append({"id": u.id, "time": stamp(u.start) if timed else None, "start": u.start if timed else None,
                     "speaker": role, "text": u.text})
    return rows


def _transcript_head(session) -> list[str]:
    vm = visit_meta(session)
    return [f"Visit transcript: {visit_name(session.meta())}", f"Date: {vm.get('date') or 'not recorded'}",
            f"Dentist: {vm.get('provider') or 'not recorded'}", f"Assistant: {vm.get('assistant') or 'not recorded'}"]


def transcript_text(session) -> str:
    out = _transcript_head(session) + [""]
    for r in transcript_rows(session):
        out.append((f"[{r['time']}] " if r["time"] else "") + f"{r['speaker']}: {r['text']}")
    notes = load_sources(session).quick_notes.notes
    if notes:
        out += ["", "Quick notes:"] + [f"- {q.text}" for q in notes]
    return "\n".join(out) + "\n"


def transcript_pdf(session) -> bytes:
    head = _transcript_head(session)
    pdf = _pdf(head[0])
    _line(pdf, head[0], size=14, style="B", height=7.5, gap=1)
    _line(pdf, "   ".join(head[1:]), size=10)
    _rule(pdf)
    for r in transcript_rows(session):
        if pdf.will_page_break(5.2):
            pdf.add_page()
        y, indent = pdf.get_y(), 0.0
        if r["time"]:
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(110)
            pdf.set_xy(pdf.l_margin, y)
            pdf.cell(15, 5.2, r["time"])
            pdf.set_text_color(0)
            indent = 15.0
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_xy(pdf.l_margin + indent, y)
        label = _latin(r["speaker"] + ": ")
        width = pdf.get_string_width(label) + 1
        pdf.cell(width, 5.2, label)
        _line(pdf, r["text"], indent=indent + width, gap=1.2)
    notes = load_sources(session).quick_notes.notes
    if notes:
        _rule(pdf)
        _line(pdf, "Quick notes", size=11.5, style="B", height=6.2)
        for q in notes:
            _line(pdf, f"- {q.text}", indent=3)
    return bytes(pdf.output())


# ---------------------------------------------------------------- everything

def bundle_zip(session) -> bytes:
    """A zip holding one folder '<Patient> <date>' with note.pdf, note.docx, transcript.txt, transcript.pdf and
    the recording (when there is one)."""
    folder = file_stem(session)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{folder}/note.pdf", note_pdf(session))
        z.writestr(f"{folder}/note.docx", note_docx(session))
        z.writestr(f"{folder}/transcript.txt", transcript_text(session))
        z.writestr(f"{folder}/transcript.pdf", transcript_pdf(session))
        audio = recording_path(session)
        if audio is not None:
            z.write(audio, f"{folder}/recording{audio.suffix.lower()}")
    return buf.getvalue()
