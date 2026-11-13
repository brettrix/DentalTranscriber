"""The evaluation machinery end to end, offline: pipeline + Grader + report, rescore, merge, fault injection."""
import json
import os

import pytest

import eval.run_eval as run_eval
import pipeline.storage as storage
from pipeline import ledger
from tests.fake_llm import MINI_QUICK_NOTES, MINI_TRANSCRIPT, FakeLLM

os.environ["SCRIBE_NO_SLEEP"] = "1"

GOLD = {
    "case_id": "mini", "annotated_by": "test", "checked_by": None,
    "entities": [
        {"gid": "p1", "kind": "problem", "problem_key": "P1", "target": 14,
         "key_attributes": {"role": "chief", "complaint_text": "upper left tooth hurts with cold",
                            "complaint_location": "upper left"}, "evidence": [{"utterance_id": "u2"}]},
        {"gid": "f1", "kind": "item", "type": "finding", "problem_key": "P1", "scope": "problem", "target": 14,
         "key_attributes": {"test": "cold", "response": "present"}, "evidence": [{"utterance_id": "u5"}]},
        {"gid": "a1", "kind": "item", "type": "allergy", "scope": "encounter",
         "key_attributes": {"substance": "penicillin"}, "status_fields": {"allergy_status": "reported_active"},
         "evidence": [{"utterance_id": "u4"}]},
        {"gid": "rx1", "kind": "item", "type": "prescription", "scope": "encounter",
         "key_attributes": {"drug": "ibuprofen", "strength": "600 mg"}, "evidence": [{"utterance_id": "u8"}]},
    ],
    "expected_flags": [], "forbidden_facts": ["skiing"],
}


@pytest.fixture
def eval_env(tmp_path, monkeypatch):
    ev = tmp_path / "eval"
    case = ev / "cases" / "mini"
    case.mkdir(parents=True)
    (case / "transcript.txt").write_text(MINI_TRANSCRIPT)
    (case / "quick_notes.txt").write_text(MINI_QUICK_NOTES)
    (case / "visit_meta.json").write_text(json.dumps({"date": "2026-11-12", "provider": "Dr. Test"}))
    (ev / "gold").mkdir()
    (ev / "gold" / "mini.json").write_text(json.dumps(GOLD))
    monkeypatch.setattr(run_eval, "EVAL_DIR", ev)
    monkeypatch.setattr(storage, "SESSIONS_DIR", tmp_path / "sessions")
    return case, tmp_path / "results"


def test_run_eval_offline_end_to_end(eval_env):
    case, out = eval_env
    run_eval.GRADER_TRACE[0] = out / "grader_traces.jsonl"
    rows = [run_eval.run_one(case, mode, 0, out, True, "synthetic_demo", client=FakeLLM())
            for mode in ("baseline", "team")]
    for r in rows:
        assert r["candidate"] and r["scored"] and r["grader_error"] is None
        assert r["final"]["recall"] == [4, 4], r["final"]["omissions"]
        assert r["claims"].get("supported_by_transcript", 0) > 0
    run_eval.finish(rows, out, {"git_hash": "test", "git_dirty": False, "eval_config_hash": "x", "schema_version": "y",
                                "models": {"defaults": "fake", "Grader": "fake"}, "transcriber": "text"}, "Offline test")
    report = (out / "report.md").read_text()
    assert "baseline" in report and "team" in report and "4/4 (100%)" in report
    assert (out / "results.csv").exists() and (out / "grader_review.csv").exists()
    assert (out / "grader_traces.jsonl").exists(), "Grader calls are traced to the results folder"
    assert ledger.totals()["calls"] == 0, "fake calls are never ledgered as real"


def test_rescore_and_merge_offline(eval_env):
    case, out = eval_env
    run_eval.run_one(case, "baseline", 0, out, False, "synthetic_demo", client=FakeLLM())
    row = run_eval.load_rows(out)[0]
    assert row["claims"] == {}, "no grading on the first pass"
    out2 = out.parent / "rescored"
    rescored = run_eval.rescore(out, out2, client=FakeLLM())
    assert rescored[0]["claims"].get("supported_by_transcript", 0) > 0
    merged = run_eval.merge(out, [out2])
    assert len(merged) == 1 and merged[0]["merged_from"] == "rescored"


def test_fault_injection_offline(tmp_path):
    from eval import fault_injection
    rows = fault_injection.run(["m01_control_tooth"], tmp_path / "faults", client=FakeLLM())
    r = rows[0]
    assert r["false_rejections"]["Cv"] == [], "Cv passes unmodified gold"
    caught = {f["fault"]: f["Cv_caught"] for f in r["faults"] if f["applicable"]}
    assert caught["tooth_swap"] and caught["negation_flip"], "derivation-breaking faults are caught by Cv"
    assert (tmp_path / "faults" / "fault_report.md").exists()


def test_freeze_detects_changes_and_guards_heldout(tmp_path, monkeypatch):
    import sys

    from eval import freeze
    monkeypatch.setattr(freeze, "FROZEN", tmp_path / "FROZEN.json")
    assert freeze.check() == ["not frozen yet"]
    rec = freeze.freeze()
    assert rec["eval_config_hash"] and freeze.check() == []
    real = freeze.file_hashes
    monkeypatch.setattr(freeze, "file_hashes", lambda: {**real(), "prompts/cs_support.md": "edited"})
    assert freeze.check() == ["prompts/cs_support.md"]
    monkeypatch.setattr(sys, "argv", ["run_eval", "--cases", "eval/heldout", "--out", str(tmp_path / "r")])
    with pytest.raises(SystemExit, match="frozen evaluation configuration"):
        run_eval.main()


def test_scoring_reports_tooth_bearing_breakdown_and_unmatched_flags(eval_env):
    case, out = eval_env
    row = run_eval.run_one(case, "baseline", 0, out, False, "synthetic_demo", client=FakeLLM())
    tb = row["final"]["tooth_by_type"]
    assert tb["finding"] == [1, 1], tb
    unmatched = row["final"]["flags"]["unmatched_detail"]
    assert len(unmatched) == len(row["final"]["flags"]["false_alarms"]) + len(row["final"]["flags"]["tolerated"])
    run_eval.finish([row], out, {"git_hash": "t", "git_dirty": False, "eval_config_hash": "x", "schema_version": "y",
                                 "models": {"defaults": "f", "Grader": "f"}, "transcriber": "text"}, "t")
    report = (out / "report.md").read_text()
    assert "Tooth accuracy on tooth-bearing items" in report and "Raised flags not matched to gold" in report
