"""Chart-note wording, plain-words errors and visit-list helpers (no model calls)."""
from datetime import datetime, timezone

from pipeline import approval, plain
from pipeline.chart import chart_line, chart_sections
from pipeline.render import render_note
from pipeline.visits import filter_visits, is_test_visit, visit_name, waiting_text
from tests.helpers import graph, item, problem, sources


def _lines(*items):
    g = graph(problem(), *items)
    chart = chart_sections(render_note(g, sources(), "baseline"), g)
    return g, chart, [l["text"] for s in chart["sections"] for l in s["lines"]]


def test_lines_read_like_a_chart_note():
    g, chart, lines = _lines(
        item("finding", tooth=14, test="cold", response="present", lingering=False),
        item("finding", tooth=30, test="bite paper", result_description="heavy mark on the new filling"),
        item("finding", tooth=19, test="percussion", response="absent"),
        item("symptom", aspect="trigger", value="cold drinks"),
        item("symptom", aspect="biting_pain", assertion="denied"),
        item("symptom", aspect="severity", score=4.0),
        item("diagnosis", tooth=14, diagnosis="reversible pulpitis", certainty="definite"),
        item("diagnosis", tooth=3, diagnosis="cracked tooth", certainty="possible"),
        item("allergy", problem_id=None, substance="penicillin", allergy_status="reported_active"),
        item("allergy", problem_id=None, allergy_status="denied", assertion="denied"),
        item("prescription", problem_id=None, drug="ibuprofen", strength="600 mg", frequency_code="q6h PRN",
             duration_days=3, prescription_status="prescribed_today"))
    for want in ("#14: cold test positive, not lingering", "#30: bite paper — heavy mark on the new filling",
                 "#19: percussion test negative", "Triggered by: cold drinks", "No pain on biting", "Severity: 4/10",
                 "Reversible pulpitis #14", "Possible cracked tooth #3", "Allergy: penicillin", "No known allergies",
                 "Ibuprofen 600 mg, q6h PRN, for 3 days"):
        assert want in lines, (want, lines)
    text = "\n".join(lines)
    for jargon in ("positive/felt", "Definite:", "Denies", "biting pain:", "trigger:", "provider:", "prescribed today"):
        assert jargon not in text, jargon
    assert chart["not_discussed"] and "Referral" in chart["not_discussed"]
    assert all(s["lines"] for s in chart["sections"]), "empty sections are only named in the one-line summary"


def test_bwx_and_pa_are_spelled_out_on_first_use_only():
    _, _, lines = _lines(item("radiograph", tooth=14, type="PA", action="performed", finding="decay under the filling"),
                         item("radiograph", tooth=19, type="PA", action="performed"),
                         item("radiograph", type="BWX", action="not_needed"))
    assert lines[1:] == ["Periapical X-ray (PA) #14: decay under the filling", "PA #19", "Bitewing X-rays (BWX) (not needed)"]


def test_allergy_reaction_is_shown_only_when_there_is_one():
    g = graph(problem(), item("allergy", problem_id=None, substance="penicillin", reaction="hives",
                              allergy_status="reported_resolved"))
    assert chart_line(g.active("item")[0], g) == "Allergy: penicillin (hives) — patient reports it has resolved"


def test_errors_are_plain_sentences_never_exception_text():
    blocked = approval.ApprovalBlocked(["it_3: failed/unassessed check", "conflict cf_1 must be resolved"])
    assert plain.friendly_error(blocked) == "Answer the 2 items above first."
    assert plain.friendly_error(approval.ApprovalBlocked(["task tk_1 must be completed"])) == \
        "Answer the 1 item above first."
    for exc in (ValueError("it_9 is not an active entity"), RuntimeError("Deepgram error 500: <html>"),
                KeyError("snapshot_hash"), RuntimeError("DEEPGRAM_API_KEY is not set")):
        msg = plain.friendly_error(exc, "save that")
        assert str(exc).strip("'") not in msg and "it_9" not in msg and "Error" not in msg, msg


class _S:
    def __init__(self, meta, vm=None):
        self._meta, self._vm = meta, vm or {}

    def meta(self):
        return self._meta

    def path(self, *parts):
        from pathlib import Path
        return Path("/nonexistent") / "/".join(parts)


def test_visit_names_test_visits_and_search():
    real = _S({"patient": "Maria Lopez 4417", "created": "2026-11-13T19:30:00+00:00"})
    legacy = _S({"case": "case8", "created": "2026-11-12T19:00:00+00:00"})
    started_from_admin = _S({"patient": "Demo", "case": "case1", "test": True})
    assert visit_name(real.meta()) == "Maria Lopez 4417" and visit_name(legacy.meta()) == "case8"
    assert not is_test_visit(real.meta()) and is_test_visit(legacy.meta()) and is_test_visit(started_from_admin.meta())
    everything = [real, legacy, started_from_admin]
    assert filter_visits(everything) == [real]
    assert filter_visits(everything, show_tests=True) == everything
    assert filter_visits(everything, "lopez 4417") == [real] and filter_visits(everything, "nobody") == []


def test_waiting_time_in_plain_words():
    now = datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)
    assert waiting_text("2026-11-13T19:59:40+00:00", now) == "just now"
    assert waiting_text("2026-11-13T19:35:00+00:00", now) == "25 min"
    assert waiting_text("2026-11-13T16:50:00+00:00", now) == "3 h 10 min"
    assert waiting_text("2026-11-10T20:00:00+00:00", now) == "3 days"


def test_sent_time_reads_naturally():
    from pipeline.visits import ago_text
    now = datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)
    assert ago_text("2026-11-13T19:59:40+00:00", now) == "just now"
    assert ago_text("2026-11-13T19:59:00+00:00", now) == "1 minute ago"
    assert ago_text("2026-11-13T19:55:00+00:00", now) == "5 minutes ago"
    assert ago_text("2026-11-13T17:50:00+00:00", now) == "2 hours ago"
    assert ago_text("2026-11-10T20:00:00+00:00", now) == "3 days ago"
