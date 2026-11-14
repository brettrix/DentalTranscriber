"""Note accuracy on a visit rebuilt from the "Dale" lines (see tests/dale.py): a hedged "no" is never a positive,
spoken strengths are kept, discussion elements are not falsely reported missing, brand names read as spoken."""
import copy

from pipeline import approval, plain
from pipeline.chart import chart_line, chart_sections, chart_text
from pipeline.graph import load_graph
from pipeline.orchestrator import load_latest, run_pipeline
from pipeline.tidy import hedged_no, spoken_strength_value
from pipeline.verify import session_check_log
from tests import dale
from tests.dale import dale_session
from tests.fake_llm import FakeLLM, d, mini_session, q
from tests.helpers import graph, item, problem


def _note(s):
    g = load_graph(s)
    return g, chart_text(load_latest(s)["note"], g)


def _one(g, itype, **match):
    return next(e for e in g.active("item") if e.type == itype
                and all(e.attributes.get(k) == v for k, v in match.items()))


# ---- 1. "I don't think so" to fever

def test_unsure_no_to_fever_is_a_denial_not_a_possible_finding(tmp_path):
    s = dale_session(tmp_path)
    g, note = _note(s)
    fever = _one(g, "symptom", value="fever")
    assert fever.assertion == "denied", "the model said 'possible'; an unsure no is a denial"
    assert "- Denies fever (unsure)" in note
    assert "Possible" not in note and "possible" not in note.lower()
    assert [sp.text for sp in fever.evidence] == ["I don't think so.", "Any fever?"], "the question is cited too"
    log = session_check_log(s)
    assert log.latest(fever, "normalization_valid")["result"] == "pass", "the denial is checked against the question"
    assert approval.blockers(s, "dentist") == [], "and it raises no card"
    assert "Denies other: fever" in next(l["text"] for sec in load_latest(s)["note"]["sections"]
                                         for l in sec["lines"] if "fever" in l["text"]), "canonical note too"


def test_hedged_no_is_recognized_narrowly():
    for text in ("I don't think so.", "No, I don't think so", "Not that I know of.", "Um, not really.",
                 "I do not believe so", "Probably not."):
        assert hedged_no(text), text
    for text in ("I don't think so, but it has been swollen since Monday.", "Not really sharp, more of a dull ache.",
                 "Yes.", "I think so.", "I don't think the filling fell out, it just feels rough."):
        assert not hedged_no(text), text


def test_a_possible_finding_that_was_really_said_stays_possible(tmp_path):
    items = copy.deepcopy(dale.ITEMS)
    items["S1"] = {"key": "S1", "type": "symptom", "problem_key": "P1", "assertion": "possible",
                   "attributes": {"aspect": "swelling", "value": "cheek might be a little swollen"},
                   "assertion_source": "patient_report",
                   "evidence": [q("u2", "My lower left back tooth has been throbbing for three days.")]}
    s = mini_session(tmp_path, "baseline")
    from pipeline.transcribe import transcribe_text
    transcribe_text(s, dale.TRANSCRIPT)
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items, problem=dale.PROBLEM))
    assert _one(load_graph(s), "symptom").assertion == "possible"


def test_notes_written_before_the_fix_also_read_as_a_denial():
    """An older session still holds assertion 'possible' with the hedge as its evidence; the note wording alone
    must not show it as a positive."""
    from schemas.entities import Span
    e = item("symptom", aspect="other", value="fever", assertion="possible")
    e.evidence = [Span(source_type="transcript", source_id="u4", start=0, end=17, text="I don't think so.")]
    g = graph(problem(), e)
    assert chart_line(e, g) == "Denies fever (unsure)"
    assert plain.describe(e, g) == "Symptom: Denies fever (unsure)"


# ---- 2. strengths spoken without a unit

def test_spoken_strengths_are_kept(tmp_path):
    s = dale_session(tmp_path)
    g, note = _note(s)
    assert "- Ibuprofen 600 mg, q6h" in note and "- Tylenol (acetaminophen) 500 mg, q6h" in note
    log = session_check_log(s)
    for drug, strength, words in (("ibuprofen", "600 mg", "six hundred"), ("acetaminophen", "500 mg", "five hundred")):
        rx = _one(g, "prescription", drug=drug)
        assert rx.attributes["strength"] == strength
        cited = next(x for x in rx.derivations if x.attribute == "attributes.strength")
        assert (cited.rule, cited.from_, cited.to) == ("spoken_strength", words, strength)
        assert log.latest(rx, "normalization_valid")["result"] == "pass", "traced to the words, so no card"


def test_spoken_strength_rule_is_narrow(tmp_path):
    import pytest
    from pipeline.normalize import NormalizationError
    assert spoken_strength_value("six hundred") == "600 mg" and spoken_strength_value("800") == "800 mg"
    for not_mg in ("three", "6", "five thousand"):
        with pytest.raises(NormalizationError):
            spoken_strength_value(not_mg)
    # A strength the model did extract is left alone, and a number that isn't right after the drug's name is not used.
    items = copy.deepcopy(dale.ITEMS)
    items["RX1"]["attributes"]["strength"] = "400 mg"
    items["RX1"]["evidence"] = [q("u15", dale.RX_LINE), q("u1", "What brings you in today, Dale?")]
    items["RX1"]["derivations"].append(d("attributes.strength", "dose", "six hundred", "400 mg"))
    items["RX2"]["attributes"]["drug"] = "naproxen"   # not named in the line: nothing to read a strength from
    items["RX2"]["attributes"].pop("original_wording")
    items["RX2"]["derivations"] = items["RX2"]["derivations"][1:]
    s = mini_session(tmp_path, "baseline")
    from pipeline.transcribe import transcribe_text
    transcribe_text(s, dale.TRANSCRIPT)
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items, problem=dale.PROBLEM))
    g = load_graph(s)
    assert _one(g, "prescription", drug="ibuprofen").attributes["strength"] == "400 mg"
    assert _one(g, "prescription", drug="naproxen").attributes["strength"] is None


# ---- 3. discussion elements

def test_discussion_elements_are_not_reported_missing(tmp_path):
    s = dale_session(tmp_path)
    g, note = _note(s)
    assert "Not documented" not in note, "the chart note never claims an element was missing"
    assert "- Alternatives discussed: root canal; extraction" in note, "extraction was offered as an alternative"
    assert "- Benefits discussed: root canal: will save the tooth and stop the pain" in note
    chart = chart_sections(load_latest(s)["note"], g)
    assert "Discussion elements documented" not in chart["not_discussed"]


def test_no_options_means_no_discussion_section_and_no_claim_either(tmp_path):
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM())
    g, note = _note(s)
    assert "DISCUSSION ELEMENTS" not in note and "Not documented" not in note
    assert "Discussion elements documented" not in chart_sections(load_latest(s)["note"], g)["not_discussed"]


def test_an_extracted_element_is_shown_once_not_derived_again():
    opt_a = item("option_discussed", tooth=19, option="root canal", benefits="saves the tooth")
    opt_b = item("option_discussed", tooth=19, option="extraction")
    el = item("consent_element", element="alternatives_discussed", content="root canal or extraction")
    g = graph(problem(target=19), opt_a, opt_b, el)
    from pipeline.render import render_note
    from tests.helpers import sources
    chart = chart_sections(render_note(g, sources(), "baseline"), g)
    lines = [l["text"] for sec in chart["sections"] if sec["id"] == "discussion_elements" for l in sec["lines"]]
    assert lines == ["Alternatives discussed: root canal or extraction",
                     "Benefits discussed: root canal #19: saves the tooth"]


# ---- 4 and 5. brand names and intolerance

def test_brand_names_read_as_spoken_with_the_generic(tmp_path):
    s = dale_session(tmp_path)
    g, note = _note(s)
    assert "- Eliquis (apixaban)" in note
    assert plain.describe(_one(g, "medication"), g) == "Medication: Eliquis (apixaban)"
    generic = item("medication", problem_id=None, drug="apixaban")
    assert chart_line(generic, graph(problem(), generic)) == "Apixaban", "no brand was said, so none is shown"


def test_brand_name_on_card_buttons_and_titles(tmp_path):
    from tests.test_review_cards import _cards
    items = copy.deepcopy(dale.ITEMS)
    items["A1"] = {"key": "A1", "type": "allergy",
                   "attributes": {"substance": "amoxicillin", "original_wording": "Amoxil", "reaction": "rash",
                                  "allergy_status": "reported_active"},
                   "assertion_source": "patient_report",
                   "evidence": [q("u8", "Codeine makes me throw up")],   # any cited line; the wording carries the brand
                   "derivations": []}
    items["RX1"]["attributes"].update(drug="amoxicillin", original_wording="Amoxil")
    items["RX1"]["derivations"] = []
    s = mini_session(tmp_path, "baseline")
    from pipeline.transcribe import transcribe_text
    transcribe_text(s, dale.TRANSCRIPT)
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items, problem=dale.PROBLEM))
    card = next(c for c in _cards(s, "Dentist") if c["kind"] == "allergy_rx")
    assert card["title"] == "Amoxil (amoxicillin) prescribed, but the note has: Amoxil (amoxicillin) allergy (rash)"
    g = load_graph(s)
    assert plain.allergy_label(_one(g, "allergy")) == "Amoxil (amoxicillin) allergy (rash)"


def test_not_really_an_allergy_reads_as_intolerance(tmp_path):
    s = dale_session(tmp_path)
    g, note = _note(s)
    assert "- Intolerance (not an allergy): codeine (makes me throw up)" in note
    assert plain.allergy_label(_one(g, "allergy")) == "Codeine intolerance (makes me throw up)"
    real = item("allergy", problem_id=None, substance="penicillin", reaction="hives", allergy_status="reported_active")
    assert chart_line(real, graph(problem(), real)) == "Allergy: penicillin (hives)"
