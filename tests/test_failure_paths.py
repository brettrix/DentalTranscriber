"""Failure-path tests (section 14.1) and the stage-5 behaviour list (section 17), offline with the fake LLM."""
import copy
import os

import pytest

from pipeline import approval, human
from pipeline.dispositions import bound_dispositions
from pipeline.graph import load_graph, snapshot_hash
from pipeline.linker import session_staging
from pipeline.orchestrator import load_latest, run_pipeline
from pipeline.overlays import confirm_roles
from pipeline.stage_runs import session_stage_log
from pipeline.validate import StructuralError
from pipeline.verify import session_check_log
from tests.fake_llm import ITEMS, FakeLLM, mini_session, q, timeout_error

os.environ["SCRIBE_NO_SLEEP"] = "1"


def run(s, mode, fake=None):
    fake = fake or FakeLLM()
    return run_pipeline(s, mode=mode, client=fake), fake


def item_of(g, type_):
    return next(e for e in g.active("item") if e.type == type_)


def flag_ids(s):
    return [f["rule_id"] for f in load_latest(s)["flags"]]


def clear_for_dentist(s):
    """Dismiss/mark everything the matrix lets a reviewer settle, so a test isolates one blocker."""
    for f in load_latest(s)["flags"]:
        if f["severity"] == "high" and f["rule_id"] not in ("unsupported_content", "open_conflict",
                                                            "open_review_task", "incomplete_section"):
            human.flag_action(s, f["id"], "dismiss", "Dentist", "reviewed")


def approve_both(s):
    clear_for_dentist(s)
    approval.approve_assistant(s)
    approval.approve_dentist(s)


V2 = {"key": "V2", "type": "vital_reading", "attributes": {"systolic": 150, "diastolic": 95, "sequence": 2},
      "assertion_source": "clinician_observation", "evidence": [q("u10", "Blood pressure is 150 over 95.")],
      "derivations": [{"attribute": "attributes.systolic", "rule": "bp_reading", "from": "150 over 95", "to": 150},
                      {"attribute": "attributes.diastolic", "rule": "bp_reading", "from": "150 over 95", "to": 95}]}


# ---------------------------------------------------------------- 14.1

def test_timeout_makes_extractor_fail_with_terminal_records(tmp_path):
    s = mini_session(tmp_path, "baseline")
    result, fake = run(s, "baseline", FakeLLM(fail={"B0": timeout_error()}))
    assert fake.calls.count("B0") == 4, "3 transport retries after the first attempt"
    runs = session_stage_log(s).for_run(result["run"]["run_id"])
    assert {(r["agent"], r["status"]) for r in runs} >= {("B0", "failed"), ("Linker", "failed")}
    assert result["candidate"] is False
    staging = session_staging(s)
    assert any(t["kind"] == "stage_failure" for t in staging.tasks), "the failure creates a task without a graph"


def test_invalid_json_gets_one_schema_reask(tmp_path):
    s = mini_session(tmp_path, "baseline")
    result, fake = run(s, "baseline", FakeLLM(fail={"B0": "invalid_once"}))
    assert fake.calls.count("B0") == 2 and result["candidate"]
    s2 = mini_session(tmp_path / "b", "baseline")
    result2, fake2 = run(s2, "baseline", FakeLLM(fail={"B0": "invalid"}))
    assert fake2.calls.count("B0") == 2 and not result2["candidate"]


def test_failed_section_reaches_ready_for_review_with_approval_blocked(tmp_path):
    s = mini_session(tmp_path, "team")
    result, _ = run(s, "team", FakeLLM(fail={"B1": timeout_error()}))
    assert result["status"]["ready_for_review"]
    assert "medical_history" in result["status"]["incomplete_sections"]
    assert "incomplete_section" in flag_ids(s)
    note = result["note"]
    mh = next(x for x in note["sections"] if x["id"] == "medical_history")
    assert mh["status_line"].startswith("PROCESSING INCOMPLETE")
    assert any("medical_history" in b for b in approval.blockers(s, "dentist"))
    with pytest.raises(approval.ApprovalBlocked):
        approval.approve_assistant(s)


def test_overlay_change_reruns_extraction_and_revokes_approval(tmp_path):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    approve_both(s)
    assert approval.load_state(s).state == "dentist_approved"
    confirm_roles(s, {"S0": "Dentist", "S1": "Other"})
    _, fake = run(s, "baseline")
    assert "B0" in fake.calls
    assert approval.load_state(s).state == "draft"
    assert approval.load_state(s).revoked[-1]["changed"]


def test_human_edit_swapping_finding_tooth(tmp_path):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    g = load_graph(s)
    f = item_of(g, "finding")
    human.edit_entity(s, f.id, {"target": {"tooth": 15}}, "Dentist", "tooth misheard; it was 15")
    g2 = load_graph(s)
    new = g2.get(f.id)
    assert new.version == f.version + 1 and new.target.tooth == 15 and new.owner == "human"
    assert g2.get(f.id, f.version).status == "superseded"
    assert new.target_relation == "unknown"
    assert "unexplained_other_tooth" in flag_ids(s)


def _bp_conflict_session(tmp_path, mode="baseline", items=None):
    items = items or {**copy.deepcopy(ITEMS), "V2": V2}
    s = mini_session(tmp_path, mode)
    run(s, mode, FakeLLM(items=items))
    g = load_graph(s)
    c = next(c for c in g.conflicts if c.kind == "quick_note_vs_transcript")
    return s, c


def test_conflict_resolution_persists_and_reopens_when_participant_changes(tmp_path):
    s, c = _bp_conflict_session(tmp_path)
    v2 = next(p.entity_id for p in c.participants if load_graph(s).get(p.entity_id).evidence[0].source_id == "u10")
    human.resolve_conflict(s, c.id, "select", "Dentist", "recheck reading is the one", active_entity_id=v2)
    assert load_graph(s).conflict(c.id).status == "resolved"
    run(s, "baseline", FakeLLM(items={**copy.deepcopy(ITEMS), "V2": V2}))
    g = load_graph(s)
    assert g.conflict(c.id).status == "resolved", "persists across a rerun with unchanged participants"
    v1 = next(p.entity_id for p in c.participants if p.entity_id != v2)
    assert g.get(v1).status == "superseded"
    changed = copy.deepcopy(V2)
    changed["attributes"]["systolic"] = 152
    changed["evidence"] = [q("u10", "Blood pressure is 150 over 95.")]
    changed["derivations"][0]["to"] = 150
    v2b = copy.deepcopy(V2)
    v2b["attributes"]["label"] = "recheck"   # participant content changes -> new version
    run(s, "baseline", FakeLLM(items={**copy.deepcopy(ITEMS), "V2": v2b}))
    assert load_graph(s).conflict(c.id).status == "open", "reopens when a participant's version changes"


def test_assistant_added_prescription_blocks_dentist_until_confirmed(tmp_path):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    rx = {"kind": "item", "type": "prescription", "scope": "encounter",
          "attributes": {"drug": "chlorhexidine", "prescription_status": "prescribed_today"},
          "assertion_source": "clinician_instruction"}
    human.add_entity(s, rx, "Assistant", "dentist said rinse")
    g = load_graph(s)
    assert not any(e.attributes.get("drug") == "chlorhexidine" for e in g.active_items("prescription"))
    pc = next(p for p in g.pending_changes if p.status == "pending")
    clear_for_dentist(s)
    approval.approve_assistant(s)
    assert any(pc.id in b for b in approval.blockers(s, "dentist"))
    with pytest.raises(approval.ApprovalBlocked):
        approval.approve_dentist(s)
    human.decide_pending(s, pc.id, True, "Dentist")
    g = load_graph(s)
    added = next(e for e in g.active_items("prescription") if e.attributes.get("drug") == "chlorhexidine")
    assert bound_dispositions(g, added, {"dentist_confirmed"})
    assert not any(pc.id in b for b in approval.blockers(s, "dentist"))


def test_export_refused_after_post_approval_change(tmp_path, monkeypatch):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    approve_both(s)
    import pipeline.rules as rules_mod
    real = rules_mod.rule_file_hashes
    monkeypatch.setattr(rules_mod, "rule_file_hashes", lambda: {**real(), "config.json": "changed"})
    with pytest.raises(approval.ExportRefused):
        approval.export(s)
    assert approval.load_state(s).state == "draft"
    monkeypatch.setattr(rules_mod, "rule_file_hashes", real)


def test_export_succeeds_when_unchanged(tmp_path):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    approve_both(s)
    path = approval.export(s)
    text = open(path).read()
    assert "Prototype — test data only" in text and approval.load_state(s).state == "exported"


# ---------------------------------------------------------------- section 17, stage 5 list

def test_human_edit_with_dangling_reference_is_rejected(tmp_path):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    before = load_graph(s).version
    d = item_of(load_graph(s), "diagnosis")
    with pytest.raises(StructuralError):
        human.edit_entity(s, d.id, {"problem_id": "pb_99"}, "Dentist", "relink")
    assert load_graph(s).version == before


def test_one_human_medication_does_not_clear_failed_history_section(tmp_path):
    s = mini_session(tmp_path, "team")
    run(s, "team", FakeLLM(fail={"B1": timeout_error()}))
    med = {"kind": "item", "type": "medication", "scope": "encounter",
           "attributes": {"drug": "lisinopril", "medication_status": "current"}, "assertion_source": "patient_report"}
    human.add_entity(s, med, "Dentist", "patient mentioned at checkout")
    assert any("medical_history" in b for b in approval.blockers(s, "dentist"))
    human.review_section(s, "medical_history", "completed", "Assistant", "reviewed transcript; entered the medication")
    assert not any("section medical_history" in b for b in approval.blockers(s, "dentist"))
    g = load_graph(s)
    b1_task = next(t for t in g.tasks if t.kind == "stage_failure" and "B1" in t.reason)
    assert b1_task.status == "completed", "the extractor's failure task completes itself (10.1)"


def test_failed_co_blocks_dentist_until_task_accepted(tmp_path):
    s = mini_session(tmp_path, "team")
    run(s, "team", FakeLLM(fail={"Co": timeout_error()}))
    g = load_graph(s)
    task = next(t for t in g.tasks if t.kind == "stage_failure" and "Co" in t.reason)
    assert any(task.id in b for b in approval.blockers(s, "dentist"))
    with pytest.raises(human.HumanActionError):
        human.complete_task(s, task.id, "accepted", "Assistant", "looked")
    human.complete_task(s, task.id, "accepted", "Dentist", "reviewed the transcript for omissions")
    assert not any(task.id in b for b in approval.blockers(s, "dentist"))


def test_br_failure_blocks_b2_b4_and_stages_b1_until_registry(tmp_path):
    s = mini_session(tmp_path, "team")
    result, fake = run(s, "team", FakeLLM(fail={"Br": timeout_error()}))
    runs = {r["agent"]: r["status"] for r in session_stage_log(s).for_run(result["run"]["run_id"])}
    assert runs["Br"] == "failed" and runs["B1"] == "succeeded"
    assert runs["B2"] == runs["B3"] == runs["B4"] == "blocked"
    assert load_graph(s) is None
    staged = [r for r in session_staging(s).open_records() if r.owner == "B1"]
    assert staged and all(r.status == "staged" for r in staged)
    human.enter_registry(s, {"complaint_text": "upper left tooth hurts with cold",
                             "complaint_location": {"free_text": "upper left", "tooth": None},
                             "clinical_target": {"tooth": 14, "free_text": None}}, "Dentist",
                         "entered from the transcript", client=FakeLLM())
    g = load_graph(s)
    assert g is not None and g.chief().owner == "human"
    assert {e.type for e in g.active("item")} >= {"allergy", "finding", "diagnosis"}


def test_accepted_e3_failure_not_rerun_when_dispositions_change(tmp_path):
    s = mini_session(tmp_path, "baseline")
    fake = FakeLLM(fail={"E3": timeout_error()})
    run(s, "baseline", fake)
    g = load_graph(s)
    task = next(t for t in g.tasks if t.kind == "stage_failure" and "E3" in t.reason)
    human.complete_task(s, task.id, "accepted", "Dentist", "no review questions needed", client=fake)
    n = fake.calls.count("E3")
    human.confirm_entity(s, item_of(load_graph(s), "finding").id, "dentist_confirmed", "Dentist", "ok", client=fake)
    assert fake.calls.count("E3") == n, "accepted E3 failure is not re-run"


def test_editing_problem_voids_linked_dispositions(tmp_path):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    f = item_of(load_graph(s), "finding")
    human.confirm_entity(s, f.id, "dentist_confirmed", "Dentist", "checked")
    assert bound_dispositions(load_graph(s), load_graph(s).get(f.id), {"dentist_confirmed"})
    human.edit_entity(s, load_graph(s).chief().id, {"complaint_text": "cold sensitivity upper left"}, "Dentist", "clarify")
    g = load_graph(s)
    assert not bound_dispositions(g, g.get(f.id), {"dentist_confirmed"})


@pytest.mark.parametrize("target", ["allergy", "prescription"])
def test_assistant_removal_of_critical_item_is_pending(tmp_path, target):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    e = item_of(load_graph(s), target)
    human.remove_entity(s, e.id, "Assistant", "patient says this is wrong")
    g = load_graph(s)
    assert g.get(e.id).status == "active" and any(p.operation == "remove" for p in g.pending_changes)


def test_assistant_conflict_resolution_of_critical_content_is_pending(tmp_path):
    s, c = _bp_conflict_session(tmp_path)
    human.resolve_conflict(s, c.id, "select", "Assistant", "use quick note", active_entity_id=c.participants[0].entity_id)
    g = load_graph(s)
    assert all(g.get(p.entity_id).status == "active" for p in c.participants)
    assert any(p.operation == "resolve_conflict" for p in g.pending_changes if p.status == "pending")
    assert any(c.id in b for b in approval.blockers(s, "dentist"))


def test_decision_and_option_commit_together_regardless_of_order(tmp_path):
    items = copy.deepcopy(ITEMS)
    dec = {"key": "DC1", "type": "decision", "problem_key": "P1", "option_key": "O1",
           "attributes": {"decision": "accepted"}, "assertion_source": "patient_report",
           "evidence": [q("u9", "We'll do a filling on fourteen next week.")]}
    opt = {"key": "O1", "type": "option_discussed", "problem_key": "P1", "target": {"tooth": 14},
           "attributes": {"option": "filling"}, "assertion_source": "clinician_assessment",
           "evidence": [q("u9", "We'll do a filling on fourteen next week.")],
           "derivations": [{"attribute": "target.tooth", "rule": "spoken_tooth_number", "from": "fourteen", "to": 14}]}
    items = {"DC1": dec, **items, "O1": opt}  # decision listed before its option
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline", FakeLLM(items=items))
    g = load_graph(s)
    d, o = item_of(g, "decision"), item_of(g, "option_discussed")
    assert d.attributes["option_id"] == o.id and d.attributes["option_link"] == "linked"


def test_conflict_references_superseded_participant_after_resolution(tmp_path):
    s, c = _bp_conflict_session(tmp_path)
    keep = c.participants[1].entity_id
    human.resolve_conflict(s, c.id, "select", "Dentist", "recheck", active_entity_id=keep)
    g = load_graph(s)
    gone = next(p for p in g.conflict(c.id).participants if p.entity_id != keep)
    assert g.get(gone.entity_id, gone.version).status == "superseded"
    from pipeline.validate import validate_graph
    assert validate_graph(g) == []


def test_rerun_after_overlay_change_keeps_human_entries_and_removals(tmp_path):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    human.add_entity(s, {"kind": "item", "type": "instruction", "scope": "encounter",
                         "attributes": {"text": "warm salt water rinses"}, "assertion_source": "clinician_instruction"},
                     "Assistant", "dentist said it at the door")
    rx = item_of(load_graph(s), "prescription")
    human.remove_entity(s, rx.id, "Dentist", "not actually prescribed")
    confirm_roles(s, {"S0": "Dentist", "S1": "Patient"})
    run(s, "baseline")
    g = load_graph(s)
    assert any(e.owner == "human" and e.attributes.get("text") == "warm salt water rinses" for e in g.active("item"))
    assert not g.active_items("prescription"), "a human-removed item is not resurrected"
    assert g.get(rx.id).status == "superseded"


def test_old_semantic_pass_stops_applying_after_problem_edit(tmp_path):
    s = mini_session(tmp_path, "team")
    run(s, "team")
    g = load_graph(s)
    f = item_of(g, "finding")
    log = session_check_log(s)
    old_pass = log.latest(f, "semantic_support")
    assert old_pass["result"] == "pass"
    human.edit_entity(s, g.chief().id, {"complaint_text": "cold sensitivity, upper left"}, "Dentist", "clarify",
                      client=FakeLLM())
    f2 = load_graph(s).get(f.id)
    assert f2.support_hash != f.support_hash
    log2 = session_check_log(s)
    assert old_pass["support_hash"] != f2.support_hash
    assert log2.latest(f2, "semantic_support")["attempt"] == 3, "a new execution, not the old pass"


def test_recording_stage_run_keeps_snapshot_hash(tmp_path):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    h = snapshot_hash(load_graph(s))
    session_stage_log(s).record("E", "E2", "succeeded", run_id="x")
    assert snapshot_hash(load_graph(s)) == h


def test_changing_template_revokes_approval(tmp_path, monkeypatch):
    s = mini_session(tmp_path, "baseline")
    run(s, "baseline")
    approve_both(s)
    import pipeline.render as render
    monkeypatch.setattr(render, "RENDERER_VERSION", "2")
    assert approval.revoke_if_changed(s, "template changed")
    assert approval.load_state(s).state == "draft"
