"""Drive the Streamlit review page as an assistant and a dentist (offline: fake model client, network blocked)."""
import copy
import os
import re

from streamlit.testing.v1 import AppTest

import pipeline.storage as storage
from pipeline import approval
from pipeline.graph import load_graph
from pipeline.orchestrator import run_pipeline
from tests.fake_llm import ITEMS, MINI_TRANSCRIPT, FakeLLM, mini_session, q

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


def _cards(at):
    """Card titles (bold markdown lines with a tag badge)."""
    return [m.value for m in at.markdown if m.value.startswith("**") and "-badge[" in m.value]


def _answered(at):
    return next(m.value for m in at.markdown if "answered**" in m.value)


def _visible_text(at):
    return " ".join([m.value for m in at.markdown] + [c.value for c in at.caption])


def _status(at):
    return " ".join(x.value for x in list(at.info) + list(at.success))


def test_ui_edit_review_approve_download(monkeypatch, tmp_path):
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    rx = next(e for e in load_graph(s).active("item") if e.type == "prescription")
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert any("Prototype — test data only" in e.value for e in at.error), "banner on the page"
    assert "Waiting for the assistant's review" in _status(at)
    assert not any(t.key == f"f_{rx.id}_strength" for t in at.text_input), "the editor is closed until Edit is clicked"
    next(b for b in at.button if b.key == f"edit_{rx.id}").click().run()
    next(t for t in at.text_input if t.key == f"f_{rx.id}_strength").set_value("400 mg").run()
    next(b for b in at.button if b.key == f"save_{rx.id}").click().run()
    assert not at.exception, at.exception
    edited = load_graph(s).get(rx.id)
    assert edited.attributes["strength"] == "400 mg" and edited.owner == "human"
    assert any(x.value == "Saved." for x in at.success), "confirmation beside the line that was edited"
    assert not any(t.key == f"f_{rx.id}_strength" for t in at.text_input), "the editor closes after saving"

    at = _app(monkeypatch, tmp_path, "Assistant")
    assert "Waiting for your review" in _status(at)
    _button(at, "Send to the dentist").click().run()
    assert approval.load_state(s).state == "assistant_review_complete"
    assert "Waiting for the dentist" in _status(at) and "Sent just now" in _status(at)
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert "Waiting for your approval" in _status(at)
    _button(at, "Approve the note").click().run()
    assert not at.exception and approval.load_state(s).state == "dentist_approved"
    assert re.search(r"Approved by the dentist at \d\d:\d\d", _status(at))
    assert not any(h.value == "To answer" for h in at.subheader), "no checklist once approved"
    assert not any(b.key and b.key.startswith("edit_") for b in at.button), "an approved note isn't edited in place"


def test_note_reads_like_a_chart_note(monkeypatch, tmp_path):
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    at = _app(monkeypatch, tmp_path, "Assistant")
    lines = [m.value for m in at.markdown if m.value.startswith("- ")]
    text = "\n".join(lines)
    assert "- Allergy: penicillin (hives)" in text and "- #14: cold test positive, sharp" in text
    assert "- Reversible pulpitis #14" in text and "- Ibuprofen 600 mg, q6h PRN" in text
    for jargon in ("positive/felt", "Definite:", "Denies", "provider:", "reaction:", "prescribed today", "trigger:"):
        assert jargon not in text, jargon
    empty = next(c.value for c in at.caption if c.value.startswith("Not discussed: "))
    assert "Radiographs" in empty and "Referral" in empty, "empty sections fold into one line"
    assert not any("Not documented in the provided sources" in m.value for m in list(at.markdown) + list(at.caption))


def test_add_something_uses_plain_choices(monkeypatch, tmp_path):
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    at = _app(monkeypatch, tmp_path, "Assistant")
    kinds = next(w for w in at.selectbox if w.key == "add_type")
    assert "Exam finding" in kinds.options and "X-ray" in kinds.options and not any("_" in o for o in kinds.options)
    kinds.set_value("Instruction").run()
    who = next(r for r in at.radio if r.label == "Who said it?")
    assert who.options == ["Dentist", "Patient", "Assistant"]
    _button(at, "Add to the note").click().run()
    assert any(e.value == "Fill in at least one detail above first." for e in at.error)
    next(t for t in at.text_input if t.key == "f_add_instruction_text").set_value("soft foods for two days").run()
    _button(at, "Add to the note").click().run()
    assert not at.exception, at.exception
    added = next(e for e in load_graph(s).active("item") if e.type == "instruction")
    assert added.attributes["text"] == "soft foods for two days" and added.assertion_source == "clinician_instruction"
    assert any(x.value == "Added to the note." for x in at.success)


def _bad_session(tmp_path, with_bp=True):
    items = {**copy.deepcopy(ITEMS), **({"V2": V2} if with_bp else {})}
    items["F1"]["evidence"][0]["quote"] = "Cold on tooth fourteen."   # fails the quote check -> needs confirming
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items))
    return s


def test_cards_are_plain_with_side_by_side_quotes(monkeypatch, tmp_path):
    _bad_session(tmp_path)
    at = _app(monkeypatch, tmp_path, "Dentist")
    cards = _cards(at)
    assert len(cards) == 2, cards
    text = _visible_text(at)
    assert "a second read" not in text.lower()
    head = " ".join(cards)
    assert not ID.search(head) and not JARGON.search(head), head
    assert any(c.startswith("**Blood pressure doesn't match the quick note**") for c in cards)
    assert any("Quick note says" == c.value for c in at.caption) and any("Said in the visit" == c.value for c in at.caption)
    assert any("\u201cBlood pressure is 150 over 95.\u201d \u2014 Dentist" in m.value for m in at.markdown), \
        "the exact quote and who said it"
    assert 'white-space: nowrap' in " ".join(m.value for m in at.markdown), "button labels stay on one line"


def test_choices_are_held_then_saved_together(monkeypatch, tmp_path):
    s = _bad_session(tmp_path)
    v0 = load_graph(s).version
    at = _app(monkeypatch, tmp_path, "Dentist")
    groups = at.button_group
    assert _answered(at) == "**0 of 2 answered**"
    bar = next(b for b in at.button if b.key == "handoff")
    assert bar.disabled and bar.label == "Save my answers", "one button in the bar, off until everything is answered"
    assert load_graph(s).version == v0
    assert "you can already answer the 2 items below" in _status(at)
    groups = at.button_group
    bp = next(g for g in groups if "Use 150/95" in g.options)
    assert bp.options == ["Use 124/80", "Use 150/95", "Both are right"], "buttons name the actual readings"
    bp.set_value("keep0").run()
    bp = next(g for g in at.button_group if g.key == bp.key)
    assert bp.value == "keep0" and bp.options[0] == "\u2713 Use 124/80", "selected shows a check"
    bp.set_value("both").run()
    bp = next(g for g in at.button_group if g.key == bp.key)
    assert bp.value == "both" and bp.options == ["Use 124/80", "Use 150/95", "\u2713 Both are right"], \
        "selection moved"
    assert load_graph(s).version == v0, "nothing saved per click"
    other = next(g for g in at.button_group if g.key != bp.key)
    other.set_value("ok").run()
    assert _answered(at) == "**2 of 2 answered**"
    next(b for b in at.button if b.key == "handoff").click().run()
    assert not at.exception, at.exception
    g = load_graph(s)
    assert g.version == v0 + 1, "one rebuild for the whole review"
    assert all(c.status == "resolved" for c in g.conflicts)
    assert any(x.value == "Saved your answers." for x in at.success)
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert _cards(at) == []


def test_ask_dentist_is_part_of_the_choice(monkeypatch, tmp_path):
    s_ = _bad_session(tmp_path, with_bp=False)
    at = _app(monkeypatch, tmp_path, "Assistant")
    grp = at.button_group[0]
    assert "Ask dentist" in grp.options and "Looks right" not in grp.options, \
        "a critical item can't be passed by the assistant"
    assert any(c.value == "Only the dentist can confirm tooth numbers." for c in at.caption)
    grp.set_value("ask").run()
    next(t for t in at.text_input if t.key == f"{grp.key}_note").set_value("I heard fifteen, not fourteen").run()
    next(b for b in at.button if b.key == "handoff").click().run()
    at = _app(monkeypatch, tmp_path, "Assistant")
    assert _cards(at) == [], "cleared for the assistant"
    assert not any(t.label == "Note for your actions (optional)" for t in at.text_input)
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert len(_cards(at)) == 1, "now the dentist's to answer"
    assert any("The assistant asked about this" in m.value and "I heard fifteen, not fourteen" in m.value
               for m in at.markdown), "the dentist sees what the assistant asked, with her comment"
    assert approval.load_state(s_).state == "assistant_review_complete", "answering and sending was one click"


def test_wording_only_disagreements_are_folded(monkeypatch, tmp_path):
    from tests.fake_llm import ITEMS
    s = mini_session(tmp_path, "team")
    run_pipeline(s, mode="team", client=FakeLLM(cs_override={ITEMS["S1"]["evidence"][0]["quote"]:
                                                             {"attributes.value": "cold drinks hurt a lot"}},
                                                ce_verdict="different"))
    at = _app(monkeypatch, tmp_path, "Dentist")
    folded = [e for e in at.expander if "look" in e.label and e.label.endswith("right \u00b7 show")]
    assert folded and folded[0].label == "1 more item looks right \u00b7 show", [e.label for e in at.expander]
    assert _answered(at).startswith("**1 of 1"), "folded items arrive pre-answered as 'Looks right'"


def test_new_visit_needs_a_patient_then_writes_the_note_and_opens_review(monkeypatch, tmp_path):
    old = mini_session(tmp_path, "baseline")
    run_pipeline(old, mode="baseline", client=FakeLLM())
    at = _app(monkeypatch, tmp_path, "Assistant", page="New visit")
    labels = [w.label for w in at.radio]
    assert "Pipeline mode" in labels and "Rule mode" in labels, "still there, inside Admin settings"
    assert any(e.label == "Admin settings" for e in at.expander)
    how = next(r for r in at.radio if r.key == "nv_input")
    assert how.options == ["Record visit", "Upload a recording", "Paste a transcript"]
    assert not any("Mode:" in e.value or "Rules:" in e.value for e in at.error), "no mode or rules in the banner"
    quick = next(t for t in at.text_area if t.key == "nv_quick")
    assert quick.placeholder == "BP 124/80\nCC: lower left pain\n#19"

    how.set_value("Paste a transcript").run()
    _button(at, "Write the note").click().run()
    assert any("patient's name or chart number" in e.value for e in at.error)
    assert len(storage.list_sessions(tmp_path)) == 1, "nothing created without a patient"
    next(t for t in at.text_input if t.key == "nv_patient").set_value("Maria Lopez 4417").run()
    _button(at, "Write the note").click().run()
    assert any(e.value == "Paste the transcript first." for e in at.error)
    next(t for t in at.text_area if t.key == "nv_transcript").set_value(MINI_TRANSCRIPT).run()
    _button(at, "Write the note").click().run()
    assert not at.exception, at.exception
    assert at.session_state["page"] == "Review"
    new = storage.list_sessions(tmp_path)[0]
    assert at.session_state["sid"] == new.id != old.id, "the new visit is selected"
    assert new.meta()["patient"] == "Maria Lopez 4417"
    assert any(m.value.startswith("### Maria Lopez 4417 · ") for m in at.markdown), "the patient is the visit name"
    assert any(b.label.startswith("Maria Lopez 4417 · ") for b in at.sidebar.button)


def test_bad_transcript_gives_a_plain_message_and_leaves_no_visit(monkeypatch, tmp_path):
    at = _app(monkeypatch, tmp_path, "Assistant", page="New visit")
    next(r for r in at.radio if r.key == "nv_input").set_value("Paste a transcript").run()
    next(t for t in at.text_input if t.key == "nv_patient").set_value("Chart 88").run()
    next(t for t in at.text_area if t.key == "nv_transcript").set_value("hello there, no speakers here").run()
    _button(at, "Write the note").click().run()
    assert not at.exception
    err = " ".join(e.value for e in at.error)
    assert "speaker at the start of each line" in err and "TranscriptFormatError" not in err and "prefix" not in err
    assert storage.list_sessions(tmp_path) == []


def test_test_case_lives_in_admin_settings_and_test_visits_are_hidden_by_default(monkeypatch, tmp_path):
    real = mini_session(tmp_path, "baseline")
    real.update_meta(patient="Sam Park")
    run_pipeline(real, mode="baseline", client=FakeLLM())
    legacy = mini_session(tmp_path, "baseline")
    legacy.update_meta(case="case8")
    run_pipeline(legacy, mode="baseline", client=FakeLLM())
    at = _app(monkeypatch, tmp_path, "Assistant", page="New visit")
    assert [b.key for b in at.sidebar.button if b.key.startswith("visit_")] == [f"visit_{real.id}"]
    next(w for w in at.selectbox if w.key == "nv_case").set_value("case1").run()
    _button(at, "Write the note").click().run()
    assert not at.exception, at.exception
    new = storage.list_sessions(tmp_path)[0]
    assert new.meta()["case"] == "case1" and new.meta()["test"] is True
    assert at.session_state["sid"] == new.id and at.session_state["page"] == "Review"
    at.session_state["page"] = "Admin"
    at.run()
    toggle = next(t for t in at.toggle if t.key == "show_tests_widget")
    assert toggle.value is True, "switched on so the test visit just started is listed"
    toggle.set_value(False).run()
    assert [b.key for b in at.sidebar.button if b.key.startswith("visit_")] == [f"visit_{real.id}"]
    assert any(e.label == "Speaker roles" for e in at.expander) and any(e.label == "Technical log" for e in at.expander)


def _visit(tmp_path, patient, date, created):
    s = mini_session(tmp_path, "baseline")
    s.update_meta(patient=patient, created=created)
    from pipeline.transcribe import write_visit_meta
    write_visit_meta(s, date=date, provider="Dr. Test")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    return s


def test_clicking_a_visit_always_opens_that_visit(monkeypatch, tmp_path):
    """Regression: two visits with the same name, and a list that changes between clicks."""
    a = _visit(tmp_path, "case8", "2026-11-12", "2026-11-12T19:00:00.000+00:00")
    b = _visit(tmp_path, "case8", "2026-11-13", "2026-11-13T19:30:00.000+00:00")
    c = _visit(tmp_path, "case2", "2026-11-10", "2026-11-10T19:00:00.000+00:00")
    at = _app(monkeypatch, tmp_path, "Assistant")

    def heading():
        return next(m.value for m in at.markdown if m.value.startswith("### "))

    for s, date in ((a, "2026-11-12"), (b, "2026-11-13"), (c, "2026-11-10"), (a, "2026-11-12")):
        next(x for x in at.sidebar.button if x.key == f"visit_{s.id}").click().run()
        assert not at.exception, at.exception
        assert at.session_state["sid"] == s.id
        assert heading() == f"### {s.meta()['patient']} · {date} · Dr. Test", heading()
    # A newer visit appears at the top of the list (every position shifts); the next click still opens its own visit.
    _visit(tmp_path, "case8", "2026-11-14", "2026-11-14T19:00:00.000+00:00")
    next(x for x in at.sidebar.button if x.key == f"visit_{c.id}").click().run()
    assert at.session_state["sid"] == c.id and heading() == "### case2 · 2026-11-10 · Dr. Test"
    # The open visit stays open while the list is filtered by the search box.
    at.sidebar.text_input[0].set_value("case8").run()
    assert at.session_state["sid"] == c.id and heading().startswith("### case2")
    assert sorted(x.key for x in at.sidebar.button if x.key.startswith("visit_")) == \
        sorted(f"visit_{s.id}" for s in storage.list_sessions(tmp_path) if s.meta()["patient"] == "case8")


def test_signoff_buttons_only_while_they_apply(monkeypatch, tmp_path):
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    signs = ("Send to the dentist", "Approve the note")
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert not any(b.label in signs for b in at.button), "nothing to sign before the assistant"
    at = _app(monkeypatch, tmp_path, "Assistant")
    _button(at, "Send to the dentist").click().run()
    assert not any(b.label in signs for b in at.button), "gone once sent"
    at = _app(monkeypatch, tmp_path, "Dentist")
    _button(at, "Approve the note").click().run()
    at = _app(monkeypatch, tmp_path, "Assistant")
    assert not any(b.label in signs for b in at.button), "hidden once approved"
    assert "Approved by the dentist at" in _status(at)
    assert any(d.label.startswith("Download") for d in at.get("download_button"))
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert not any(b.label in signs for b in at.button)


def test_sign_off_is_not_offered_while_items_are_unanswered(monkeypatch, tmp_path):
    _bad_session(tmp_path)
    at = _app(monkeypatch, tmp_path, "Assistant")
    assert _cards(at) and _button(at, "Send to the dentist").disabled, "off until every item is answered"
    assert any(h.value == "To answer" for h in at.subheader)


def test_approved_note_offers_pdf_word_and_copy_never_markdown(monkeypatch, tmp_path):
    s = mini_session(tmp_path, "baseline")
    s.update_meta(patient="Maria Lopez 4417")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    at = _app(monkeypatch, tmp_path, "Assistant")
    assert [d.label for d in at.get("download_button")] == ["Transcript (PDF)", "Transcript (text)"], \
        "before approval only the transcript can be downloaded (a pasted transcript has no recording)"
    approval.force_approve_for_test(s)
    at = _app(monkeypatch, tmp_path, "Assistant")
    assert not at.exception, at.exception
    buttons = {d.label: d for d in at.get("download_button")}
    assert list(buttons) == ["Download PDF", "Word (.docx)", "Download everything (.zip)", "Transcript (PDF)",
                             "Transcript (text)"], "PDF first; no Recording button without a recording"
    assert not any("md" in label.lower() or "markdown" in label.lower() for label in buttons)
    assert not any(b.label == "Export" for b in at.button)


def test_waiting_and_cleared_tabs_follow_the_note(monkeypatch, tmp_path):
    a = _visit(tmp_path, "Ana Ruiz", "2026-11-12", "2026-11-12T19:00:00.000+00:00")
    b = _visit(tmp_path, "Ben Cho", "2026-11-13", "2026-11-13T19:00:00.000+00:00")
    draft = _visit(tmp_path, "Still Draft", "2026-11-13", "2026-11-13T20:00:00.000+00:00")
    at = _app(monkeypatch, tmp_path, "Assistant", page="Waiting for dentist")
    assert any("Nothing is waiting for the dentist" in i.value for i in at.info)
    approval.approve_assistant(a)
    approval.approve_assistant(b)
    at = _app(monkeypatch, tmp_path, "Assistant", page="Waiting for dentist")
    names = [m.value for m in at.markdown if m.value in ("**Ana Ruiz**", "**Ben Cho**", "**Still Draft**")]
    assert names == ["**Ana Ruiz**", "**Ben Cho**"], "sent notes only, longest wait first"
    shown = " ".join(str(w.value) for w in at.markdown)
    assert "2026-11-12" in shown and "Dr. Test" in shown and ("just now" in shown or " min" in shown)
    next(x for x in at.button if x.key == f"open_w_{b.id}").click().run()
    assert at.session_state["page"] == "Review" and at.session_state["sid"] == b.id
    assert any(m.value.startswith("### Ben Cho") for m in at.markdown)

    approval.approve_dentist(a)
    at = _app(monkeypatch, tmp_path, "Assistant", page="Waiting for dentist")
    assert [m.value for m in at.markdown if m.value in ("**Ana Ruiz**", "**Ben Cho**")] == ["**Ben Cho**"]
    at = _app(monkeypatch, tmp_path, "Assistant", page="Cleared by dentist")
    assert not at.exception, at.exception
    assert [m.value for m in at.markdown if m.value.startswith("**")] == ["**Ana Ruiz**"]
    assert sorted(d.key for d in at.get("download_button")) == [f"docx_{a.id}", f"pdf_{a.id}", f"zip_{a.id}"], \
        "each cleared note has its download buttons"
    approval.approve_dentist(b)
    at = _app(monkeypatch, tmp_path, "Assistant", page="Cleared by dentist")
    assert [m.value for m in at.markdown if m.value.startswith("**")] == ["**Ben Cho**", "**Ana Ruiz**"], "newest first"
    assert draft.id not in " ".join(d.key for d in at.get("download_button"))


def _recorded(tmp_path, bad_quote=False):
    """An audio visit without any real call: a recording file and a time on every line."""
    import json
    import wave
    items = copy.deepcopy(ITEMS)
    if bad_quote:
        items["F1"]["evidence"][0]["quote"] = "Cold on tooth fourteen."
    s = mini_session(tmp_path, "baseline")
    s.update_meta(patient="Ben Cho")
    with wave.open(str(s.path("sources", "audio.wav")), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)
    path = s.path("sources", "utterances.json")
    data = json.loads(path.read_text())
    for i, u in enumerate(data["utterances"]):
        u["start"], u["end"] = 20.5 * i, 20.5 * i + 3
    path.write_text(json.dumps(data))
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items))
    return s


def test_recorded_visit_has_clickable_timestamps_and_a_player(monkeypatch, tmp_path):
    _recorded(tmp_path, bad_quote=True)
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert not at.exception, at.exception
    talk = next(m.value for m in at.markdown if "What brings you in today?" in m.value and "<b>" in m.value)
    assert talk.startswith('<a href="#t=0.00" title="Play from here">00:00</a> &nbsp;<b>Dentist:</b> What brings')
    assert '<a href="#t=102.50" title="Play from here">01:42</a> &nbsp;<b>Patient:</b> Yes, that' in talk
    assert len(at.get("audio")) == 1, "the recording is on the page for the pinned player to drive"
    assert any(c.value == "Click a time to hear that part of the recording." for c in at.caption)
    quote = next(m.value for m in at.markdown if "\u201cYes, that&#x27;s sharp.\u201d" in m.value
                 or "\u201cYes, that's sharp.\u201d" in m.value)
    assert quote.count('href="#t=') >= 1 and 'href="#t=102.50"' in quote, "a quote on a card jumps to where it was said"
    assert "Recording" in [d.label for d in at.get("download_button")]


def test_pasted_transcript_has_no_player_and_no_timestamps(monkeypatch, tmp_path):
    _bad_session(tmp_path)
    at = _app(monkeypatch, tmp_path, "Dentist")
    assert not at.get("audio")
    assert not any("#t=" in m.value for m in at.markdown)
    assert not any("Click a time" in c.value for c in at.caption)
    assert "Recording" not in [d.label for d in at.get("download_button")]
