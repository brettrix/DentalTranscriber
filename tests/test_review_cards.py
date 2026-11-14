"""Review cards on a visit shaped like the "Bear" test visit (offline: fake model client)."""
import re

from streamlit.testing.v1 import AppTest

import pipeline.storage as storage
from pipeline import approval, human, plain
from pipeline.flags import flag_state, session_flag_actions
from pipeline.graph import load_graph
from pipeline.linker import session_staging
from pipeline.orchestrator import load_latest
from pipeline.overlays import load_sources
from pipeline.verify import session_check_log
from schemas.flags import Flag
from tests import bear
from tests.bear import bear_session
from tests.fake_llm import FakeLLM

REASON = "Reviewed by the {} against the transcript"


def _client():
    return FakeLLM(items=bear.ITEMS, problem=bear.PROBLEM, r2=bear.R2)


def _flags(s):
    flags = [Flag.model_validate(f) for f in load_latest(s)["flags"]]
    session_flag_actions(s).apply(flags)
    return flags


def _cards(s, role):
    items = approval.blocker_items(s, role.lower())
    return plain.build_cards(items, load_graph(s), session_check_log(s), session_staging(s), load_sources(s), role,
                             {f.id: f for f in _flags(s)})


def _card(cards, word):
    return next(c for c in cards if word.lower() in c["title"].lower())


def _ops(card, label, reason=None):
    ops = next(o for _, lbl, o in card["options"] if lbl == label)
    return [{**op, "reason": reason} for op in ops] if reason else ops


def _labels(card):
    return [lbl for _, lbl, _ in card["options"]]


def _sent_to_dentist(tmp_path):
    s = bear_session(tmp_path)
    ops = [op for c in _cards(s, "Assistant") for op in _ops(c, "Ask dentist")]
    assert human.apply_review(s, ops, "Assistant", REASON.format("assistant"), client=_client())["errors"] == []
    approval.approve_assistant(s)
    return s


def test_one_card_per_disagreement_with_buttons_that_name_the_value(tmp_path):
    s = bear_session(tmp_path)
    cards = _cards(s, "Dentist")
    assert [c["title"] for c in cards] == [
        "Which tooth is it: #2 or #3?",
        "Amoxicillin prescribed, but the note has: penicillin allergy (hives)",
        "The quick note and the conversation disagree about allergy penicillin",
        "Blood pressure doesn't match the quick note"], "tooth alerts, the statements and the quick note are one card"
    tooth = _card(cards, "which tooth")
    assert _labels(tooth) == ["Use tooth #2", "Use tooth #3"]
    assert tooth["left"][0] == "Tooth #2" and "Next visit: Crown #2, next week" in tooth["left"][1]
    assert "“We'll do a crown on number two next week.”" in tooth["left"][1]
    assert tooth["right"][0] == "Tooth #3" and "Diagnosis: Cracked tooth #3" in tooth["right"][1]
    assert _labels(_card(cards, "amoxicillin")) == ["Remove prescription", "Change prescription", "Prescribe anyway"]
    assert _labels(_card(cards, "allergy penicillin")) == ["No allergies", "Penicillin allergy (hives)", "Both are right"]
    bp = _card(cards, "blood pressure")
    assert _labels(bp) == ["Use 132/84", "Use 184/112", "Both are right"]
    assert bp["hint"] == "184/112 (said in the visit) is very high.", "the high-reading alert rides on the same card"
    every_label = " ".join(lbl for c in cards for lbl in _labels(c))
    assert "·" not in every_label and "Reviewed, OK" not in every_label and "Keep " not in every_label
    for c in cards:
        assert "**" not in c["title"] and not re.search(r"\b(it|cf|tk|fl)_\w+", c["title"])


def test_assistant_can_only_ask_the_dentist_about_safety_cards(tmp_path):
    s = bear_session(tmp_path)
    cards = _cards(s, "Assistant")
    assert _labels(_card(cards, "which tooth")) == ["Ask dentist"]
    assert _card(cards, "which tooth")["hint"] == "Only the dentist can choose the tooth."
    assert _labels(_card(cards, "amoxicillin")) == ["Ask dentist"]
    assert not any(c["asked"] for c in cards)
    s = _sent_to_dentist(tmp_path)
    assert _cards(s, "Assistant") == []
    assert all(c["asked"] for c in _cards(s, "Dentist")), "the dentist sees which ones the assistant asked about"


def test_dentist_fixes_everything_in_one_save(tmp_path):
    s = _sent_to_dentist(tmp_path)
    cards = _cards(s, "Dentist")
    v0 = load_graph(s).version
    ops = (_ops(_card(cards, "which tooth"), "Use tooth #3") + _ops(_card(cards, "amoxicillin"), "Remove prescription")
           + _ops(_card(cards, "allergy penicillin"), "Penicillin allergy (hives)")
           + _ops(_card(cards, "blood pressure"), "Use 132/84"))
    out = human.apply_review(s, ops, "Dentist", REASON.format("dentist"), client=_client())
    assert out["errors"] == []
    g = load_graph(s)
    assert g.version == v0 + 1, "one rebuild"
    assert approval.blockers(s, "dentist") == [] and _cards(s, "Dentist") == [], "nothing comes back as a new card"
    assert g.chief().clinical_target.tooth == 3
    assert {e.target.tooth for e in g.active("item") if e.type in ("next_visit", "diagnosis", "treatment_today")} == {3}
    assert not [e for e in g.active("item") if e.type == "prescription"]
    assert [(e.attributes["systolic"], e.attributes["diastolic"]) for e in g.active("item")
            if e.type == "vital_reading"] == [(132, 84)]
    assert [e.attributes["substance"] for e in g.active("item") if e.type == "allergy"] == ["penicillin"]
    import pytest
    with pytest.raises(approval.ApprovalBlocked):
        approval.approve_dentist(s)  # the note changed, so the assistant's sign-off no longer binds
    approval.approve_dentist(s, after_own_changes=True)  # what the page does right after the dentist's own save
    assert approval.load_state(s).state == "dentist_approved"


def test_dentist_approval_after_own_changes_is_only_for_a_note_the_assistant_sent(tmp_path):
    import pytest
    s = bear_session(tmp_path)  # still the assistant's draft
    with pytest.raises(approval.ApprovalBlocked):
        approval.approve_dentist(s, after_own_changes=True)


def test_other_choices_also_settle_and_record_why(tmp_path):
    s = _sent_to_dentist(tmp_path)
    cards = _cards(s, "Dentist")
    ops = (_ops(_card(cards, "which tooth"), "Use tooth #2")
           + _ops(_card(cards, "amoxicillin"), "Prescribe anyway", "Tolerated amoxicillin last year")
           + _ops(_card(cards, "allergy penicillin"), "Both are right")
           + _ops(_card(cards, "blood pressure"), "Use 184/112"))
    assert human.apply_review(s, ops, "Dentist", REASON.format("dentist"), client=_client())["errors"] == []
    g = load_graph(s)
    assert approval.blockers(s, "dentist") == [], approval.blockers(s, "dentist")
    assert g.chief().clinical_target.tooth == 2, "the problem tooth follows the dentist's choice"
    assert {e.target.tooth for e in g.active("item") if e.type in ("next_visit", "diagnosis", "treatment_today")} == {2}
    assert [e.attributes["drug"] for e in g.active("item") if e.type == "prescription"] == ["amoxicillin"]
    by_rule = {f.rule_id: f for f in _flags(s)}
    assert flag_state(by_rule["allergy_rx"]) == "dismissed_by_dentist"
    assert by_rule["allergy_rx"].history[-1].reason == "Tolerated amoxicillin last year"
    assert flag_state(by_rule["bp_reading"]) == "dismissed_by_dentist", "kept the high reading, on the record"
    assert "settled the blood pressure" in by_rule["bp_reading"].history[-1].reason


def test_only_the_dentist_can_choose_the_tooth(tmp_path):
    s = bear_session(tmp_path)
    op = _ops(_card(_cards(s, "Dentist"), "which tooth"), "Use tooth #3")
    out = human.apply_review(s, op, "Assistant", REASON.format("assistant"), client=_client())
    assert out["errors"] and load_graph(s).chief().clinical_target.tooth == 3
    assert {e.target.tooth for e in load_graph(s).active("item") if e.type == "next_visit"} == {2}, "nothing changed"


def test_quick_note_allergy_none_reads_as_no_known_allergies(tmp_path):
    s = bear_session(tmp_path)
    g = load_graph(s)
    none = next(e for e in g.active("item") if e.type == "allergy" and e.attributes["substance"] is None)
    assert plain.describe(none, g) == "No known allergies (quick note)"
    from pipeline.chart import chart_line, no_substance
    assert chart_line(none, g) == "No known allergies"
    assert all(no_substance(w) for w in ("Allergy: none", "NKDA", "no known allergies", "Allergies: N/A", "", None))
    assert not no_substance("Allergy: latex") and not no_substance("sulfa")


def test_titles_are_plain_and_never_cut_short():
    long = "**Was the periapical X-ray of #3 taken today, and did it show the crack the dentist described?**"
    assert plain.plain_title(long) == long.strip("*") and len(plain.plain_title(long)) > 60
    assert plain.plain_title("Confirm `it_12` __now__") == "Confirm now"


# ---------------------------------------------------------------- the page

def _app(monkeypatch, tmp_path, role):
    monkeypatch.setattr(storage, "SESSIONS_DIR", tmp_path)
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.session_state["page"] = "Review"
    at.run()
    at.sidebar.selectbox[0].set_value(role).run()
    assert not at.exception, at.exception
    return at


def _group(at, label):
    return next(g for g in at.button_group if any(label in o for o in g.options))


def _value(group, label):
    """The option value behind a label (labels are what the page shows; values are what a click sends)."""
    return {"Ask dentist": "ask", "Use tooth #3": "t3", "Prescribe anyway": "anyway", "Change prescription": "edit",
            "Penicillin allergy (hives)": "keep1", "Use 132/84": "keep0"}[label]


def test_assistant_answers_and_sends_in_one_click_then_sees_a_calm_list(monkeypatch, tmp_path):
    s = bear_session(tmp_path)
    at = _app(monkeypatch, tmp_path, "Assistant")
    bar = next(b for b in at.button if b.key == "handoff")
    assert bar.label == "Send to the dentist" and bar.disabled
    assert any(m.value == "**0 of 4 answered**" for m in at.markdown)
    assert not any(b.key == "save_review" for b in at.button), "no separate save step"
    for g in list(at.button_group):
        next(x for x in at.button_group if x.key == g.key).set_value("ask").run()
    assert any(m.value == "**4 of 4 answered**" for m in at.markdown)
    next(b for b in at.button if b.key == "handoff").click().run()
    assert not at.exception, at.exception
    assert approval.load_state(s).state == "assistant_review_complete", "saved and sent by the one button"
    status = " ".join(x.value for x in at.info)
    assert "Waiting for the dentist" in status and "Sent just now" in status and "ago)" not in status
    sent = next(e for e in at.expander if e.label.startswith("Sent to the dentist ✓"))
    assert sent.label == "Sent to the dentist ✓ · 4 items", sent.label
    shown = " ".join(m.value for m in at.markdown)
    assert "\U0001f6d1" not in shown and not any(h.value == "Needs attention" for h in at.markdown)
    assert not any(b.label == "Dismiss" and "al_dm_" in (b.key or "") and _is_sent_flag(s, b.key) for b in at.button)


def _is_sent_flag(s, key):
    return any(f.id == key.replace("al_dm_", "") and flag_state(f) == "for_dentist" for f in _flags(s))


def test_dentist_sees_who_asked_and_must_give_a_reason_to_prescribe_anyway(monkeypatch, tmp_path):
    s = _sent_to_dentist(tmp_path)
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert sum("Kirstin asked about this" in m.value for m in at.markdown) == 4
    _group(at, "Use tooth #3").set_value("t3").run()
    _group(at, "Penicillin allergy (hives)").set_value("keep1").run()
    _group(at, "Use 132/84").set_value("keep0").run()
    rx = _group(at, "Prescribe anyway")
    rx.set_value("anyway").run()
    bar = next(b for b in at.button if b.key == "handoff")
    assert bar.label == "Approve the note" and not bar.disabled
    bar.click().run()
    assert any("Add a reason" in e.value and "Prescribe anyway" in e.value for e in at.error)
    assert approval.load_state(s).state == "assistant_review_complete", "nothing saved without the reason"
    rx = _group(at, "Prescribe anyway")
    next(t for t in at.text_input if t.key == f"{rx.key}_note").set_value("Tolerated amoxicillin last year").run()
    next(b for b in at.button if b.key == "handoff").click().run()
    assert not at.exception, at.exception
    assert approval.load_state(s).state == "dentist_approved", "answers saved and the note approved in one click"
    assert load_graph(s).chief().clinical_target.tooth == 3


def test_change_prescription_opens_the_editor_inside_the_card(monkeypatch, tmp_path):
    s = _sent_to_dentist(tmp_path)
    rx_id = next(e.id for e in load_graph(s).active("item") if e.type == "prescription")
    at = _app(monkeypatch, tmp_path, "Dentist")
    rx = _group(at, "Change prescription")
    assert not any(t.key == f"f_{rx.key}_drug" for t in at.text_input)
    rx.set_value("edit").run()
    drug = next(t for t in at.text_input if t.key == f"f_{rx.key}_drug")
    assert drug.value == "amoxicillin"
    _group(at, "Use tooth #3").set_value("t3").run()
    _group(at, "Penicillin allergy (hives)").set_value("keep1").run()
    _group(at, "Use 132/84").set_value("keep0").run()
    next(b for b in at.button if b.key == "handoff").click().run()
    assert any("nothing was changed yet" in e.value for e in at.error)
    next(t for t in at.text_input if t.key == f"f_{rx.key}_drug").set_value("clindamycin").run()
    next(t for t in at.text_input if t.key == f"f_{rx.key}_strength").set_value("300 mg").run()
    next(b for b in at.button if b.key == "handoff").click().run()
    assert not at.exception, at.exception
    new = load_graph(s).get(rx_id)
    assert new.attributes["drug"] == "clindamycin" and new.attributes["strength"] == "300 mg"
    assert approval.load_state(s).state == "dentist_approved"
    assert not [f for f in _flags(s) if f.rule_id == "allergy_rx"], "the alert is gone because the cause is fixed"


def test_quick_note_tooth_label_does_not_become_treatment_today(tmp_path):
    """"Tx: #2" in the quick notes names a tooth; it is not a treatment that was done."""
    from agents.extract_common import EXTRACTION_ADDENDUM
    from pipeline.chart import chart_sections
    s = bear_session(tmp_path)
    g = load_graph(s)
    assert not [e for e in g.active("item") if e.type == "treatment_today"]
    chart = chart_sections(load_latest(s)["note"], g)
    assert "Treatment today" in chart["not_discussed"]
    staged = [r for r in session_staging(s).records if r.raw.get("type") == "treatment_today"]
    assert [r.status for r in staged] == ["label_only"], "kept on record in staging, not silently dropped"
    assert not [r for r in session_staging(s).open_records() if r.raw.get("type") == "treatment_today"]
    assert not any(b["kind"] == "staged" for b in approval.blocker_items(s, "dentist")), "and it asks nothing of anyone"
    tooth = _card(_cards(s, "Dentist"), "which tooth")
    assert "Quick note: \u201cTx: #2\u201d" in tooth["left"][1], "the quick note still counts in the tooth question"
    assert "Treatment today" not in tooth["left"][1]
    assert '"Tx: #3"' in EXTRACTION_ADDENDUM and "only identify a tooth" in EXTRACTION_ADDENDUM


def test_label_only_rule_is_narrow():
    from pipeline.linker import label_only_quick_note
    from tests.helpers import item, sources
    from schemas.entities import Span

    def made(itype, note, **attrs):
        e = item(itype, tooth=3, **attrs)
        e.evidence = [Span(source_type="quick_note", source_id="q1", start=0, end=len(note), text=note)]
        return label_only_quick_note(e, sources([note]))

    assert made("treatment_today", "Tx: #3", procedure="treatment")
    assert made("treatment_today", "tx: # 3", procedure="treatment") and made("next_visit", "Tooth: #3", procedure="x")
    assert made("diagnosis", "Dx: tooth 3", diagnosis="caries")
    assert not made("treatment_today", "Tx: temp filling #3", procedure="temp filling"), "a named procedure stays"
    assert not made("finding", "Tx: #3", observation="x"), "only treatment-type items"
    spoken = item("treatment_today", tooth=3, procedure="filling")
    assert not label_only_quick_note(spoken, sources(["Tx: #3"])), "said in the visit: untouched"
