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
