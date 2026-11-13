"""E2 rules (section 9.2): a positive and an expected-negative test for each rule."""
from pipeline.dispositions import add_entity_disposition, make_disposition
from schemas.conflicts import Conflict, Participant
from schemas.dispositions import SectionRecord
from tests.helpers import flags_for, graph, item, problem, rel, rule_ids, span


def fired(g, rule, **kw):
    flags, _ = flags_for(g, **kw)
    return [f for f in flags if f.rule_id == rule]


BP_OK = dict(systolic=120, diastolic=80)


def bp(**kw):
    return item("vital_reading", problem_id=None, **(kw or BP_OK))


# ---- target rules

def test_treatment_target_mismatch():
    assert fired(graph(problem(), item("diagnosis", 15, diagnosis="x", certainty="definite")), "treatment_target_mismatch")
    assert not fired(graph(problem(), item("diagnosis", 14, diagnosis="x", certainty="definite")), "treatment_target_mismatch")


def test_treatment_target_mismatch_not_suppressed_by_control_relationship():
    g = graph(problem(mode="team"), rel(tooth=3, kind="control"), item("next_visit", 3, mode="team", procedure="filling"),
              mode="team")
    f = fired(g, "treatment_target_mismatch", mode="team")
    assert f and f[0].safety_critical and f[0].severity == "high"


def test_treatment_target_disagreement():
    g = graph(problem(target=8), item("diagnosis", 8, diagnosis="x", certainty="definite"),
              item("next_visit", 9, procedure="filling"))
    assert fired(g, "treatment_target_disagreement")
    g2 = graph(problem(target=8), item("diagnosis", 8, diagnosis="x"), item("next_visit", 8, procedure="filling"))
    assert not fired(g2, "treatment_target_disagreement")


def test_unexplained_other_tooth():
    assert fired(graph(problem(), item("finding", 3, test="cold", response="present")), "unexplained_other_tooth")
    g = graph(problem(mode="team"), rel(tooth=3), item("finding", 3, mode="team", test="cold"), mode="team")
    assert not fired(g, "unexplained_other_tooth", mode="team")


def test_unexplained_other_tooth_baseline_needs_dentist_confirmed_relationship():
    r = rel(tooth=3, mode="baseline")
    g = graph(problem(), r, item("finding", 3, test="cold"))
    assert fired(g, "unexplained_other_tooth")
    add_entity_disposition(g, g.get("rl_1"), "dentist_confirmed", "Dentist")
    from pipeline.relations import compute_target_relations
    compute_target_relations(g, "baseline")
    assert not fired(g, "unexplained_other_tooth")


def test_complaint_location_differs():
    assert fired(graph(problem(target=19, complaint_text="upper right")), "complaint_location_differs")
    assert not fired(graph(problem(target=19, complaint_text="lower left jaw")), "complaint_location_differs")


def test_complaint_location_differs_suppressed_by_eligible_referred_from():
    g = graph(problem(target=30, complaint_text="upper right", mode="team"), rel(tooth=3, kind="referred_from"),
              mode="team")
    assert not fired(g, "complaint_location_differs", mode="team")
    g2 = graph(problem(target=30, complaint_text="upper right", mode="team"),
               rel(tooth=3, kind="referred_from", semantic="unconfirmed"), mode="team")
    assert fired(g2, "complaint_location_differs", mode="team")


def test_target_not_assessable():
    assert fired(graph(problem(complaint_text="my back tooth")), "target_not_assessable")
    assert not fired(graph(problem(complaint_text="upper left")), "target_not_assessable")


# ---- quick-note rules

def test_quick_note_target_conflict():
    f = fired(graph(problem()), "quick_note_target_conflict", quick_notes=["Tx: #15"])
    assert f and f[0].safety_critical
    assert not fired(graph(problem()), "quick_note_target_conflict", quick_notes=["Tx: #14"])


def test_quick_note_complaint_mismatch():
    assert fired(graph(problem()), "quick_note_complaint_mismatch", quick_notes=["CC: lower right pain"])
    assert not fired(graph(problem()), "quick_note_complaint_mismatch", quick_notes=["CC: upper left hurts with cold"])


def test_quick_note_tooth_unclear():
    assert fired(graph(problem()), "quick_note_tooth_unclear", quick_notes=["#20"])
    assert not fired(graph(problem()), "quick_note_tooth_unclear", quick_notes=["#14"])


# ---- clinical-content rules

def _allergy(status="reported_active", substance="penicillin"):
    return item("allergy", problem_id=None, substance=substance, allergy_status=status,
                assertion="denied" if status == "denied" else "present")


def _rx(drug="amoxicillin", status="prescribed_today"):
    return item("prescription", 19, drug=drug, strength="500 mg", prescription_status=status)


def test_allergy_rx_high_on_active_allergy_match():
    f = fired(graph(problem(target=19), _allergy(), _rx()), "allergy_rx")
    assert f and f[0].severity == "high" and f[0].safety_critical and "reported active" in f[0].message


def test_allergy_rx_combination_product_matches():
    assert fired(graph(problem(target=19), _allergy(), _rx("amoxicillin/clavulanate")), "allergy_rx")


def test_allergy_rx_not_fired_when_denied_or_no_match():
    assert not fired(graph(problem(target=19), _allergy("denied", None), _rx()), "allergy_rx")
    assert not fired(graph(problem(target=19), _allergy(), _rx("ibuprofen")), "allergy_rx")


def test_allergy_rx_medium_cases():
    assert fired(graph(problem(target=19), _allergy("reported_resolved"), _rx()), "allergy_rx")[0].severity == "medium"
    assert fired(graph(problem(target=19), _allergy(), _rx(status="discussed_not_prescribed")), "allergy_rx")[0].severity == "medium"
    a = item("allergy", problem_id=None, substance=None, original_wording="the pink stuff", allergy_status="reported_active")
    assert fired(graph(problem(target=19), a, _rx()), "allergy_rx")[0].severity == "medium"


def test_allergy_rx_precautionary_on_unconfirmed_entities():
    failed = {"span_valid": "fail", "normalization_valid": "pass", "semantic_support": "not_applicable"}
    a = item("allergy", problem_id=None, substance="penicillin", allergy_status="reported_active", checks=failed)
    f = fired(graph(problem(target=19), a, _rx()), "allergy_rx")
    assert f and f[0].precautionary and "Depends on unconfirmed information" in f[0].message


def test_allergy_rx_inactive_in_office_mode_with_notice():
    flags, notices = flags_for(graph(problem(target=19), _allergy(), _rx()), rule_mode="office")
    assert "allergy_rx" not in rule_ids(flags)
    assert any("Allergy check not active" in n for n in notices)
    assert "unsupported_content" not in rule_ids(flags)  # technical rules still run (nothing to flag here)


def test_bp_reading_levels_per_reading():
    assert fired(graph(problem(), bp(systolic=165, diastolic=90)), "bp_reading")[0].severity == "medium"
    f = fired(graph(problem(), bp(systolic=182, diastolic=100)), "bp_reading")[0]
    assert f.severity == "high" and f.safety_critical
    assert fired(graph(problem(), bp(systolic=150, diastolic=104)), "bp_reading")[0].severity == "medium"
    two = fired(graph(problem(), bp(systolic=158, diastolic=98, sequence=1), bp(systolic=150, diastolic=105, sequence=2)),
                "bp_reading")[0]
    assert two.severity == "medium" and "158/98" in two.message and "150/105" in two.message


def test_bp_reading_negative_and_missing():
    assert not fired(graph(problem(), bp(systolic=124, diastolic=80)), "bp_reading")
    f = fired(graph(problem()), "bp_reading")
    assert f and f[0].severity == "low"


def _plan(decision="declined", recommended=True, consequences=False, link_option=True):
    opt = item("option_discussed", 14, id="it_opt", option="crown", recommended_by_clinician=recommended)
    dec = item("decision", id="it_dec", decision=decision, option_id="it_opt" if link_option else None,
               option_link="linked" if link_option else "unknown")
    ents = [problem(), opt, dec]
    if consequences:
        ents.append(item("consent_element", element="consequences_of_refusal_discussed", option_id="it_opt",
                         link="linked", content="could crack"))
    return graph(*ents)


def test_refusal_discussion():
    assert fired(_plan("declined"), "refusal_discussion")
    assert fired(_plan("deferred"), "refusal_discussion")
    assert not fired(_plan("deferred", consequences=True), "refusal_discussion")
    assert not fired(_plan("monitor"), "refusal_discussion")
    assert not fired(_plan("declined", recommended=False), "refusal_discussion")
    q = fired(_plan("declined", recommended=None), "refusal_discussion")
    assert q and "recommended" in q[0].message


# ---- documentation rules

def test_chief_problem_minimum():
    assert fired(graph(problem(target=None)), "chief_problem_minimum")
    assert not fired(graph(problem()), "chief_problem_minimum")


def test_diagnosis_or_plan_missing():
    assert fired(graph(problem()), "diagnosis_or_plan_missing")
    assert not fired(graph(problem(), item("diagnosis", 14, diagnosis="crack", certainty="possible")),
                     "diagnosis_or_plan_missing")
    assert not fired(graph(problem(), item("decision", decision="monitor", option_link="unknown")),
                     "diagnosis_or_plan_missing")


def test_radiograph_finding_missing():
    assert fired(graph(problem(), item("radiograph", 14, type="PA", action="performed")), "radiograph_finding_missing")
    assert not fired(graph(problem(), item("radiograph", 14, type="PA", action="not_needed")), "radiograph_finding_missing")
    assert not fired(graph(problem(), item("radiograph", 14, type="PA", action="performed", finding="normal")),
                     "radiograph_finding_missing")


def test_unconfirmed_radiograph_finding_does_not_satisfy_requirement():
    failed = {"span_valid": "pass", "normalization_valid": "pass", "semantic_support": "unconfirmed"}
    x = item("radiograph", 14, mode="team", type="PA", action="performed", finding="decay", checks=failed)
    f = fired(graph(problem(mode="team"), x, mode="team"), "radiograph_finding_missing", mode="team")
    assert f and "present but not confirmed" in f[0].message


# ---- technical safeguards

def test_unsupported_content():
    bad = {"span_valid": "fail", "normalization_valid": "pass", "semantic_support": "not_applicable"}
    g = graph(problem(), item("instruction", text="rinse", checks=bad, id="it_i"))
    assert fired(g, "unsupported_content")[0].severity == "medium"
    add_entity_disposition(g, g.get("it_i"), "human_reviewed", "Assistant", "checked transcript")
    assert not fired(g, "unsupported_content")


def test_unsupported_content_critical_needs_dentist_confirmed():
    bad = {"span_valid": "fail", "normalization_valid": "pass", "semantic_support": "not_applicable"}
    g = graph(problem(), item("allergy", problem_id=None, substance="penicillin", checks=bad, id="it_a"))
    add_entity_disposition(g, g.get("it_a"), "human_reviewed", "Assistant")
    assert fired(g, "unsupported_content")[0].severity == "high"
    add_entity_disposition(g, g.get("it_a"), "dentist_confirmed", "Dentist")
    assert not fired(g, "unsupported_content")


def test_incomplete_section():
    rec = SectionRecord(section="medical_history", owner="B1", status="failed")
    g = graph(problem(), section_records=[rec])
    assert fired(g, "incomplete_section")
    g.dispositions.append(make_disposition("section", "medical_history", {"record_version": 1}, "section_reviewed",
                                           "Assistant", outcome="not_discussed"))
    assert not fired(g, "incomplete_section")


def test_stage_failure():
    from pipeline.tasks import make_task
    run = {"id": "sr_1", "stage": "C", "agent": "Co", "status": "failed", "error": "timeout"}
    task = make_task("stage_failure", "Co failed", created_by_stage="C", stage_run_id="sr_1")
    g = graph(problem(), tasks=[task])
    assert fired(g, "stage_failure", stage_runs=[run])
    g.tasks[0].status = "completed"
    assert not fired(g, "stage_failure", stage_runs=[run])


def test_open_conflict():
    a = item("vital_reading", problem_id=None, id="it_v1", systolic=130, diastolic=80)
    b = item("vital_reading", problem_id=None, id="it_v2", systolic=150, diastolic=95)
    c = Conflict(id="cf_1", kind="quick_note_vs_transcript", participants=[Participant(entity_id="it_v1", version=1),
                                                                           Participant(entity_id="it_v2", version=1)],
                 evidence=[span()])
    g = graph(problem(), a, b, conflicts=[c])
    f = fired(g, "open_conflict")
    assert f and f[0].severity == "high"
    g.conflicts[0].status = "resolved"
    assert not fired(g, "open_conflict")


def test_open_review_task():
    from pipeline.tasks import make_task
    g = graph(problem(), tasks=[make_task("omission", "missed statement", created_by_stage="C")])
    assert fired(g, "open_review_task")
    g.tasks[0].status = "completed"
    assert not fired(g, "open_review_task")


def test_unknown_option_link():
    assert fired(_plan("monitor", link_option=False), "unknown_option_link")
    assert not fired(_plan("monitor"), "unknown_option_link")


def test_pending_critical_correction():
    assert fired(graph(problem()), "pending_critical_correction", pending_corrections=["tooth 14 -> 15"])
    assert not fired(graph(problem()), "pending_critical_correction")


def test_treatment_on_recorded_control_tooth_without_target_is_mismatch():
    g = graph(problem(target=None, mode="team"), rel(tooth=3, kind="control"),
              item("next_visit", 3, mode="team", procedure="filling"), mode="team")
    f = fired(g, "treatment_target_mismatch", mode="team")
    assert f and f[0].severity == "high" and f[0].safety_critical
    g2 = graph(problem(target=None), item("next_visit", 3, procedure="filling"))
    assert not fired(g2, "treatment_target_mismatch") and fired(g2, "target_not_assessable")
