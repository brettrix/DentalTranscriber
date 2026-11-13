"""Regression tests for the post-evaluation fixes."""
import copy
import os

from streamlit.testing.v1 import AppTest

from pipeline.normalize import apply
from pipeline.render import entity_text
from schemas.entities import Derivation, Item, Span
from tests.helpers import graph, item, problem, sources

os.environ["SCRIBE_NO_SLEEP"] = "1"


def test_spoken_tooth_numbers_are_case_insensitive():
    for text in ("Number twelve", "NUMBER TWELVE", "number Twelve", "Tooth Twelve", "Twelve", "#12"):
        assert apply("spoken_tooth_number", text) == 12, text


def test_cv_accepts_capitalized_tooth_derivation():
    from pipeline.overlays import sources_from_objects
    from pipeline.verify import check_normalization
    from schemas.sources import RoleEntry, RolesOverlay, Utterance, UtterancesSource
    text = "Number twelve, the old filling has a big piece missing."
    src = sources_from_objects(UtterancesSource(provider="text", utterances=[Utterance(id="u11", speaker="S0", text=text)]),
                               roles=RolesOverlay(confirmed=True, entries={"S0": RoleEntry(role="Dentist", set_by="t")}))
    it = Item(id="it_1", type="finding", scope="problem", problem_id="pb_1", target={"tooth": 12}, owner="B0",
              attributes={"observation": "piece missing"}, assertion_source="clinician_observation",
              evidence=[Span(source_type="transcript", source_id="u11", start=0, end=len(text), text=text)],
              derivations=[Derivation.model_validate({"attribute": "target.tooth", "rule": "spoken_tooth_number",
                                                      "from": "number Twelve", "to": 12})])
    assert check_normalization(it, src) == ("pass", [])


def test_lingering_seconds_not_rendered_out_of_ten():
    g = graph(problem())
    ling = item("symptom", aspect="lingering", value="lingers about twenty seconds", score=20)
    sev = item("symptom", aspect="severity", value="a seven", score=7)
    assert "/10" not in entity_text(ling, g)[0]
    assert "(7/10)" in entity_text(sev, g)[0]
    bare = item("symptom", aspect="lingering", value="lingers", score=20)
    assert entity_text(bare, g)[0].endswith("(20)")


def test_prescription_dose_equal_to_strength_rendered_once():
    g = graph(problem())
    rx = item("prescription", problem_id=None, drug="ibuprofen", strength="600 mg", dose="600 mg",
              frequency_code="q6h PRN", prescription_status="prescribed_today")
    text = entity_text(rx, g)[0]
    assert text.count("600 mg") == 1, text
    rx2 = item("prescription", problem_id=None, drug="amoxicillin", strength="500 mg", dose="1 capsule",
               prescription_status="prescribed_today")
    assert "1 capsule" in entity_text(rx2, g)[0]


def test_applied_repair_revisions_do_not_stay_staged(tmp_path):
    import json as _json
    from pipeline import approval
    from pipeline.linker import session_staging
    from pipeline.orchestrator import run_pipeline
    from tests.fake_llm import ITEMS, FakeLLM, mini_session
    items = copy.deepcopy(ITEMS)
    items["F1"]["evidence"][0]["quote"] = "Cold on tooth fourteen."

    def repair(agent, user):
        fixed = copy.deepcopy(ITEMS["F1"])
        ents = _json.loads(user.split("Your current entities (graph ids shown as `id`):\n")[1].split("\n\nOpen issues:")[0])
        fixed["id"] = ents[0]["id"]
        return {"items": [fixed], "unresolved": []}

    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items, repair=repair))
    revs = [r for r in session_staging(s).records if r.raw.get("id")]
    assert revs and all(r.status == "committed" for r in revs)
    assert not any("staged record" in b for b in approval.blockers(s, "dentist"))


def test_ui_defaults_to_baseline():
    at = AppTest.from_file("../app.py", default_timeout=60).run()
    radio = next(r for r in at.radio if r.label == "Pipeline mode")
    assert radio.value == "baseline" and radio.options == ["baseline", "team"]


def test_orchestrator_default_mode_is_baseline(tmp_path, monkeypatch):
    from pipeline.orchestrator import run_pipeline
    from pipeline.storage import Session
    from pipeline.transcribe import transcribe_text, write_quick_notes
    from tests.fake_llm import MINI_TRANSCRIPT, FakeLLM
    monkeypatch.delenv("PIPELINE_MODE", raising=False)
    s = Session.create(root=tmp_path)
    transcribe_text(s, MINI_TRANSCRIPT)
    write_quick_notes(s, "")
    run_pipeline(s, client=FakeLLM())
    assert s.meta()["pipeline_mode"] == "baseline"


def test_extraction_guide_covers_outgrown_allergy():
    from agents.base import read_prompt
    guide = read_prompt("_extraction_guide.md")
    assert "outgrew" in guide and "reported_resolved" in guide


def test_bp_alert_names_only_readings_over_threshold():
    from pipeline.plain import bp_title
    from pipeline.rules import RuleContext, run_rules
    from tests.helpers import ROLES, sources as mk_sources
    qn = Item(id="it_q", type="vital_reading", scope="encounter", owner="B0", assertion_source="assistant_record",
              attributes={"systolic": 162, "diastolic": 98, "sequence": 1},
              evidence=[Span(source_type="quick_note", source_id="q1", start=0, end=10, text="BP 162/98")],
              checks={"span_valid": "fail", "normalization_valid": "pass", "semantic_support": "not_applicable"})
    said = item("vital_reading", problem_id=None, systolic=128, diastolic=84, sequence=2)
    g = graph(problem(), qn, said)
    flags, _ = run_rules(RuleContext(graph=g, mode="baseline", rule_mode="synthetic_demo", sources=mk_sources()))
    bp = next(f for f in flags if f.rule_id == "bp_reading")
    assert bp_title(bp, g) == "162/98 (from the quick note, not confirmed) is elevated"


def test_legacy_applied_revisions_are_not_open(tmp_path):
    from pipeline.linker import StagedRecord, Staging
    st = Staging(tmp_path / "staging.json")
    legacy = StagedRecord(id="st_1", owner="B0", kind="item", raw={"id": "it_003", "key": "F1"}, entity={"id": "it_003"})
    failed = StagedRecord(id="st_2", owner="B0", kind="item", raw={"key": "BAD"}, errors=["tooth 40 outside 1-32"])
    st.add(legacy)
    st.add(failed)
    assert [r.id for r in st.open_records()] == ["st_2"]


def test_second_read_wording_says_what_differs():
    from pipeline.plain import why

    class Log:
        def __init__(self, details):
            self.details = details

        def latest(self, e, check):
            return {"result": "fail", "details": self.details} if check == "semantic_support" else None

    text = why(None, Log(["free-text details: different (producer 'large filling' vs checker 'bite test; big filling')"]))
    assert "described it differently" not in text and "“bite test; big filling”" in text
    assert "the patient" in why(None, Log(["assertion_source: producer 'clinician_assessment' vs checker 'patient_report'"]))


def test_displayed_text_says_in_the_past_and_hints_dentist_only():
    from pipeline.plain import describe, dentist_only_hint
    g = graph(problem())
    med = item("medication", problem_id=None, drug="warfarin", medication_status="discontinued")
    med.time_context = "historical"
    assert "(in the past)" in describe(med, g) and "historical" not in describe(med, g)
    assert dentist_only_hint(item("allergy", problem_id=None, substance="penicillin")) == \
        "Only the dentist can confirm allergies."
    assert dentist_only_hint(problem()) == "Only the dentist can confirm the chief complaint."
