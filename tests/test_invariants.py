"""Section 1.1 invariants, one or more tests each (offline, fake LLM)."""
import copy
import os

import pytest

from pipeline.graph import load_graph, snapshot_hash
from pipeline.orchestrator import reconcile_graph, run_pipeline
from pipeline.overlays import confirm_roles, load_sources
from pipeline.render import RenderError, render_note
from pipeline.stage_runs import TERMINAL, session_stage_log
from pipeline.storage import read_json, read_jsonl
from pipeline.validate import validate_graph
from pipeline.verify import session_check_log
from tests.fake_llm import ITEMS, FakeLLM, mini_session

os.environ["SCRIBE_NO_SLEEP"] = "1"
SOURCE_STAGE_OWNERS = {"B0", "Br", "B1", "B2", "B3", "B4"}


@pytest.fixture(params=["baseline", "team"])
def ran(request, tmp_path):
    s = mini_session(tmp_path, request.param)
    fake = FakeLLM()
    result = run_pipeline(s, mode=request.param, client=fake)
    return s, result, request.param


# 1. One authoritative snapshot per version; execution history is outside it.
def test_inv1_execution_history_outside_snapshot(ran):
    s, result, mode = ran
    g = load_graph(s)
    before = snapshot_hash(g)
    session_stage_log(s).record("E", "E1", "succeeded", run_id="extra")
    session_check_log(s).record(g.active()[0], "span_valid", "pass", [], "cfg")
    assert snapshot_hash(load_graph(s)) == before
    assert "stage_runs" not in g.model_dump() and "check_runs" not in g.model_dump()
    latest = read_json(s.path("outputs", "latest.json"))
    assert latest["graph_version"] == g.version and latest["snapshot_hash"] == before
    assert latest["note"]["graph_version"] == g.version


# 2. Source support.
def test_inv2_frozen_graph_has_terminal_checks_and_stage_b_origin(ran):
    s, result, mode = ran
    g = load_graph(s)
    assert g.frozen
    for e in g.active():
        if e.is_human:
            continue
        assert e.owner in SOURCE_STAGE_OWNERS, "source-backed entities come only from Stage B"
        for check in ("span_valid", "normalization_valid", "semantic_support"):
            assert getattr(e.checks, check) != "not_run", f"{e.ref} {check} not run in a frozen graph"


def test_inv2_stage_d_creates_derived_records_only(ran):
    s, result, mode = ran
    g = load_graph(s)
    snapshot = {(e.ref, e.content_hash, e.support_hash, e.status) for e in g.entities}
    reconcile_graph(g, load_sources(s), mode, [], None)
    assert {(e.ref, e.content_hash, e.support_hash, e.status) for e in g.entities} == snapshot


# 3. Structural validity is never optional.
def test_inv3_every_committed_version_is_structurally_valid(ran):
    s, result, mode = ran
    versions = sorted(int(p.stem.split("_v")[1]) for p in s.path("graphs").glob("graph_v*.json"))
    assert versions
    for v in versions:
        assert validate_graph(load_graph(s, v)) == [], f"graph v{v} invalid"


# 4. Check results are append-only; old passes don't apply to changed inputs.
def test_inv4_check_log_is_append_only_and_hash_bound(ran):
    s, result, mode = ran
    log = session_check_log(s)
    n = len(log.records)
    e = load_graph(s).active("item")[0]
    log.record(e, "span_valid", "fail", ["test"], "cfg")
    assert len(read_jsonl(s.path("check_runs.jsonl"))) == n + 1
    assert read_jsonl(s.path("check_runs.jsonl"))[:n] == log.records[:n]
    changed = copy.deepcopy(e)
    changed.content_hash = "different"
    from pipeline.verify import summarize
    summarize(changed, session_check_log(s), mode)
    assert changed.checks.span_valid == "not_run"


def test_inv4_failure_kept_after_repair(tmp_path):
    items = copy.deepcopy(ITEMS)
    items["F1"]["evidence"][0]["quote"] = "Cold on tooth fourteen."  # not an exact quote: Cv fails
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items))
    fails = [r for r in read_jsonl(s.path("check_runs.jsonl")) if r["result"] == "fail"]
    assert fails, "the failure stays in the execution history"
    g = load_graph(s)
    f = next(e for e in g.active("item") if e.type == "finding")
    assert f.checks.span_valid == "fail"
    assert any(t.kind == "check_failure" for t in g.tasks)


# 5. No stale entity is rendered.
def test_inv5_stale_graph_not_rendered(ran):
    s, result, mode = ran
    g = load_graph(s)
    confirm_roles(s, {"S0": "Dentist", "S1": "Patient"})
    run_pipeline(s, mode=mode, client=FakeLLM())
    old = load_graph(s, g.version)
    assert old.stale and all(e.status != "active" for e in old.entities)
    with pytest.raises(RenderError):
        render_note(old, load_sources(s), mode)


# 6. Changes revoke approval.
def test_inv6_overlay_change_revokes_approval(ran):
    s, result, mode = ran
    from pipeline.approval import approve_dentist, approve_assistant, load_state, force_approve_for_test
    force_approve_for_test(s, "Dentist")
    assert load_state(s).state == "dentist_approved"
    confirm_roles(s, {"S0": "Dentist", "S1": "Other"})
    run_pipeline(s, mode=mode, client=FakeLLM())
    assert load_state(s).state == "draft"


# 7. Evidence and agent output are never silently discarded.
def test_inv7_invalid_output_stays_in_staging_with_task(tmp_path):
    items = copy.deepcopy(ITEMS)
    items["BAD"] = {"key": "BAD", "type": "finding", "problem_key": "P1", "target": {"tooth": 40},
                    "attributes": {"test": "cold"}, "assertion_source": "test_response",
                    "evidence": [{"source_type": "transcript", "source_id": "u5", "quote": "Cold on number fourteen."}]}
    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items))
    staging = read_json(s.path("staging.json"))
    bad = [r for r in staging["records"] if r["raw"].get("key") == "BAD"]
    assert bad and bad[0]["status"] == "staged" and bad[0]["raw"]["target"]["tooth"] == 40, "kept unchanged"
    g = load_graph(s)
    assert any(t.kind == "staged_record" and bad[0]["id"] in t.staging_ids for t in g.tasks)


# 8. Spec examples pass the validators (see tests/test_spec_examples.py).
def test_inv8_spec_example_tests_exist():
    import tests.test_spec_examples as t
    assert hasattr(t, "test_example_item_passes_cv")


# 9. Every stage records a terminal result; every failure creates a task.
def test_inv9_terminal_stage_runs_and_failure_tasks(tmp_path):
    from tests.fake_llm import timeout_error
    s = mini_session(tmp_path, "team")
    result = run_pipeline(s, mode="team", client=FakeLLM(fail={"Co": timeout_error()}))
    runs = session_stage_log(s).for_run(result["run"]["run_id"])
    assert all(r["status"] in TERMINAL for r in runs)
    failed = [r for r in runs if r["status"] == "failed"]
    assert [r["agent"] for r in failed] == ["Co"]
    g = load_graph(s)
    assert any(t.kind == "stage_failure" and t.stage_run_id == failed[0]["id"] for t in g.tasks)
    assert result["status"]["processing_finished"] and result["status"]["ready_for_review"]


def test_repair_revision_naming_local_problem_key_commits(tmp_path):
    """Regression: a repair call referring to its problem by local key ('P1') must resolve."""
    import json as _json
    items = copy.deepcopy(ITEMS)
    items["F1"]["evidence"][0]["quote"] = "Cold on tooth fourteen."

    def repair(agent, user):
        fixed = copy.deepcopy(ITEMS["F1"])
        ids = [e["id"] for e in _json.loads(user.split("Your current entities (graph ids shown as `id`):\n")[1]
                                            .split("\n\nOpen issues:")[0])]
        fixed["id"] = ids[0]
        fixed["problem_key"] = "P1"
        return {"items": [fixed], "unresolved": []}

    s = mini_session(tmp_path, "baseline")
    run_pipeline(s, mode="baseline", client=FakeLLM(items=items, repair=repair))
    g = load_graph(s)
    f = next(e for e in g.active("item") if e.type == "finding")
    assert f.version == 2 and f.checks.span_valid == "pass"
    assert g.get(f.id, 1).status == "superseded"
