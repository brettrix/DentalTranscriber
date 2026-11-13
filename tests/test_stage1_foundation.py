"""Stage 1: storage, sources/overlays, transcriber, structural validation."""
import json
import threading

import pytest

from pipeline.graph import load_graph, rehash_all, save_graph, snapshot_hash
from pipeline.overlays import confirm_roles, load_sources
from pipeline.stage_runs import StageRunLog
from pipeline.storage import Session, SessionBusy, append_jsonl, atomic_write_json, read_json, read_jsonl
from pipeline.transcribe import (TranscriptFormatError, normalize_deepgram, parse_text_transcript, transcribe_text,
                                 write_quick_notes, write_visit_meta)
from pipeline.validate import validate_graph
from schemas.entities import Item, Problem, Span
from schemas.graph import Graph


@pytest.fixture
def session(tmp_path):
    return Session.create(root=tmp_path)


def test_atomic_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "a" / "x.json"
    atomic_write_json(p, {"a": 1})
    atomic_write_json(p, {"a": 2})
    assert read_json(p) == {"a": 2}
    assert [f.name for f in p.parent.iterdir()] == ["x.json"]


def test_jsonl_is_append_only(tmp_path):
    p = tmp_path / "log.jsonl"
    append_jsonl(p, {"n": 1})
    append_jsonl(p, {"n": 2})
    assert [r["n"] for r in read_jsonl(p)] == [1, 2]


def test_session_lock_blocks_duplicate_run(session):
    with session.lock():
        with pytest.raises(SessionBusy):
            with session.lock():
                pass
    with session.lock():
        pass


def test_text_transcript_any_case_prefixes():
    utts, roles = parse_text_transcript("DENTIST: Hi there.\nPatient: Hello.\nassistant: PA done.\ndentist: Okay.")
    assert [u.id for u in utts] == ["u1", "u2", "u3", "u4"]
    assert utts[0].speaker == utts[3].speaker == "S0"
    assert {k: v.role for k, v in roles.items()} == {"S0": "Dentist", "S1": "Patient", "S2": "Assistant"}
    assert utts[0].text == "Hi there."


def test_text_transcript_explicit_speaker_ids_allow_two_ids_one_role():
    utts, roles = parse_text_transcript("DENTIST [S0]: One.\nPATIENT [S1]: Two.\nDENTIST [S2]: Three.")
    assert roles["S0"].role == roles["S2"].role == "Dentist"
    assert utts[2].speaker == "S2"


def test_text_transcript_needs_prefix():
    with pytest.raises(TranscriptFormatError):
        parse_text_transcript("hello there")


def test_sources_are_hashed_and_roles_versioned(session):
    transcribe_text(session, "DENTIST: Cold on fourteen.\nPATIENT: Yes.")
    write_quick_notes(session, "BP 124/80\n#14\n")
    write_visit_meta(session, date="2026-11-12", provider="Dr. Test")
    src = load_sources(session)
    assert src.quick_notes.notes[1].id == "q2" and src.quick_notes.notes[1].text == "#14"
    assert set(src.hashes) >= {"utterances", "quick_notes", "visit_meta", "roles", "provider_response"}
    assert (session.path("sources", "provider_response.txt")).read_text() == "DENTIST: Cold on fourteen.\nPATIENT: Yes."
    before = src.hashes["roles"]
    confirm_roles(session, {"S0": "Dentist", "S1": "Other"})
    src2 = load_sources(session)
    assert src2.roles.version == 2 and src2.hashes["roles"] != before


def test_deepgram_normalization_contract():
    resp = {"metadata": {"duration": 12.0}, "results": {"utterances": [
        {"start": 0.1, "end": 1.2, "speaker": 0, "transcript": "Cold on fourteen."},
        {"start": 1.5, "end": 2.0, "speaker": 1, "transcript": "Yes."}]}}
    utts = normalize_deepgram(resp)
    assert [(u.id, u.speaker, u.text) for u in utts] == [("u1", "S0", "Cold on fourteen."), ("u2", "S1", "Yes.")]


def _problem(**kw):
    base = dict(id="pb_1", key="P1", role="chief", owner="B0", clinical_target={"tooth": 14},
                evidence=[Span(source_type="transcript", source_id="u1", text="x", start=0, end=1)])
    base.update(kw)
    return Problem(**base)


def _item(**kw):
    base = dict(id="it_001", type="finding", scope="problem", problem_id="pb_1", owner="B3",
                target={"tooth": 14}, evidence=[Span(source_type="transcript", source_id="u1", text="x", start=0, end=1)])
    base.update(kw)
    return Item(**base)


def test_structural_validation_catches_bad_graphs():
    good = Graph(entities=[_problem(), _item()])
    assert validate_graph(good) == []
    assert any("outside 1-32" in e for e in validate_graph(Graph(entities=[_problem(), _item(target={"tooth": 33})])))
    assert any("missing" in e for e in validate_graph(Graph(entities=[_problem(), _item(problem_id="pb_9")])))
    assert any("chief" in e for e in validate_graph(Graph(entities=[_item()])))
    two = Graph(entities=[_problem(), _problem(id="pb_2")])
    assert any("exactly one chief" in e for e in validate_graph(two))
    bad_scope = _item(type="medication", scope="problem")
    assert any("scope" in e for e in validate_graph(Graph(entities=[_problem(), bad_scope])))
    human = _item(owner="human")
    assert any("human-entry" in e for e in validate_graph(Graph(entities=[_problem(), human])))


def test_decision_cannot_point_to_superseded_option():
    opt = _item(id="it_002", type="option_discussed", status="superseded")
    dec = _item(id="it_003", type="decision", attributes={"option_id": "it_002", "option_link": "linked"})
    errs = validate_graph(Graph(entities=[_problem(), opt, dec]))
    assert any("superseded" in e for e in errs)


def test_supersession_cycle_detected():
    a = _item(id="it_001", version=1, status="superseded", superseded_by="it_002@1")
    b = _item(id="it_002", version=1, status="superseded", superseded_by="it_001@1")
    assert any("cycle" in e for e in validate_graph(Graph(entities=[_problem(), a, b])))


def test_graph_versions_and_snapshot_hash(session):
    transcribe_text(session, "DENTIST: x")
    src = load_sources(session)
    g = Graph(entities=[_problem(), _item()])
    rehash_all(g, src.roles)
    g1 = save_graph(session, g)
    g2 = save_graph(session, g1)
    assert (g1.version, g2.version) == (1, 2)
    assert load_graph(session).version == 2
    assert snapshot_hash(g1) != snapshot_hash(g2)  # version is part of the snapshot


def test_stage_run_records_are_terminal(tmp_path):
    log = StageRunLog(path=tmp_path / "stage_runs.json")
    rec = log.record("B", "B1", "failed", error="timeout", run_id="r1")
    assert StageRunLog(path=tmp_path / "stage_runs.json").get(rec["id"])["status"] == "failed"
    with pytest.raises(AssertionError):
        log.record("B", "B1", "running")
