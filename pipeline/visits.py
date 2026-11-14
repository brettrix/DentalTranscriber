"""Visit names, list filtering and waiting times for the app's sidebar and worklists (no Streamlit here)."""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline.storage import read_json


def visit_name(meta: dict) -> str:
    """The patient (name or chart #) the assistant typed; older and test sessions fall back to the case name."""
    return (meta.get("patient") or meta.get("case") or "Visit").strip()


def is_test_visit(meta: dict) -> bool:
    """Test-case and evaluation runs: started from a case folder, with no patient entered."""
    return bool(meta.get("test") or (meta.get("case") and not meta.get("patient")))


def _local(iso: str | None) -> datetime | None:
    return datetime.fromisoformat(iso).astimezone() if iso else None


def visit_when(meta: dict) -> str:
    when = _local(meta.get("created"))
    return when.strftime("%b %d %H:%M") if when else "?"


def visit_meta(session) -> dict:
    return read_json(session.path("sources", "visit_meta.json"), {}) or {}


def visit_heading(session) -> str:
    """'Patient · visit date · Dentist' for page headings and file names."""
    vm = visit_meta(session)
    return " · ".join(p for p in (visit_name(session.meta()), vm.get("date"), vm.get("provider")) if p)


def filter_visits(sessions: list, query: str = "", show_tests: bool = False) -> list:
    """Sessions to list (the given order is kept): test runs hidden unless asked for; the search matches the
    patient, visit date, dentist or processed time, every word, any case."""
    words = (query or "").lower().split()
    out = []
    for s in sessions:
        meta = s.meta()
        if not show_tests and is_test_visit(meta):
            continue
        vm = visit_meta(s)
        hay = " ".join(str(x) for x in (visit_name(meta), vm.get("date"), vm.get("provider"), visit_when(meta))
                       if x).lower()
        if all(w in hay for w in words):
            out.append(s)
    return out


def waiting_text(since_iso: str | None, now: datetime | None = None) -> str:
    """How long ago, in plain words: 'just now', '25 min', '3 h 10 min', '2 days'."""
    since = _local(since_iso)
    if since is None:
        return "?"
    minutes = int(((now or datetime.now(timezone.utc)) - since).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 48 * 60:
        h, m = divmod(minutes, 60)
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{minutes // (24 * 60)} days"


def ago_text(since_iso: str | None, now: datetime | None = None) -> str:
    """'just now', '5 minutes ago', '2 hours ago', '3 days ago'."""
    since = _local(since_iso)
    if since is None:
        return "earlier"
    minutes = int(((now or datetime.now(timezone.utc)) - since).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    for size, unit in ((24 * 60, "day"), (60, "hour"), (1, "minute")):
        if minutes >= size:
            n = minutes // size
            return f"{n} {unit}{'' if n == 1 else 's'} ago"
    return "just now"


def clock(iso: str | None) -> str:
    """'12:38' today, otherwise 'Nov 12 12:38'."""
    when = _local(iso)
    if when is None:
        return "?"
    return when.strftime("%H:%M") if when.date() == datetime.now().astimezone().date() else when.strftime("%b %d %H:%M")


def worklists(sessions: list, show_tests: bool = False) -> dict[str, list[dict]]:
    """The assistant's two queues. 'waiting': her review is done and the dentist hasn't approved yet, longest wait
    first. 'cleared': approved by the dentist, newest approval first."""
    from pipeline import approval
    waiting, cleared = [], []
    for s in sessions:
        meta = s.meta()
        if not show_tests and is_test_visit(meta):
            continue
        state = approval.load_state(s)
        if state.state == "assistant_review_complete":
            kind, queue = "assistant_review_complete", waiting
        elif state.state in ("dentist_approved", "exported"):
            kind, queue = "dentist_approved", cleared
        else:
            continue
        since = next((r.timestamp for r in reversed(state.records) if r.kind == kind), None)
        vm = visit_meta(s)
        queue.append({"session": s, "patient": visit_name(meta), "date": vm.get("date") or "—",
                      "dentist": vm.get("provider") or "—", "since": since})
    waiting.sort(key=lambda r: r["since"] or "")
    cleared.sort(key=lambda r: r["since"] or "", reverse=True)
    return {"waiting": waiting, "cleared": cleared}
