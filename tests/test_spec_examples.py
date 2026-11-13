"""Invariant 8: the examples in BUILD_PROMPT.md pass the validators against tests/fixtures/."""
import json
from pathlib import Path

from pipeline.graph import content_hash, fill_speakers, rehash_all, support_hash
from pipeline.overlays import sources_from_objects
from pipeline.validate import validate_graph
from pipeline.verify import check_normalization, check_spans
from schemas.entities import Item, Problem
from schemas.graph import Graph
from schemas.sources import RolesOverlay, UtterancesSource

FIX = Path(__file__).parent / "fixtures"

# Section 6.4, verbatim.
SPEC_6_4 = r'''
{
  "id": "it_007", "kind": "item", "type": "finding", "scope": "problem", "problem_id": "pb_1",
  "version": 1, "status": "active",
  "target": {"tooth": 3, "surface": null, "site": null, "free_text": null},
  "target_relation": "matches_target",
  "attributes": {"test": "cold", "response": "present", "result_description": null, "intensity": "sharp", "lingering": false, "duration_s": null},
  "assertion": "present", "time_context": "current",
  "assertion_source": "test_response", "speaker_ids": ["S0", "S1"], "roles": ["Dentist", "Patient"],
  "evidence": [
    {"source_type": "transcript", "source_id": "u21", "source_version": 1, "start": 0, "end": 21, "text": "Cold on number three."},
    {"source_type": "transcript", "source_id": "u22", "source_version": 1, "start": 0, "end": 22, "text": "Ow, yes, that's sharp."},
    {"source_type": "transcript", "source_id": "u24", "source_version": 1, "start": 0, "end": 24, "text": "It's gone already, yeah."}
  ],
  "derivations": [
    {"attribute": "target.tooth", "rule": "spoken_tooth_number", "from": "number three", "to": 3, "evidence_index": 0},
    {"attribute": "attributes.response", "rule": "semantic", "from": "Ow, yes", "to": "present", "evidence_index": 1},
    {"attribute": "attributes.intensity", "rule": "semantic", "from": "sharp", "to": "sharp", "evidence_index": 1},
    {"attribute": "attributes.lingering", "rule": "semantic", "from": "It's gone already", "to": false, "evidence_index": 2}
  ],
  "checks": {"span_valid": "pass", "normalization_valid": "pass", "semantic_support": "not_applicable"},
  "dispositions": []
}
'''


def _setup():
    utt = UtterancesSource.model_validate(json.loads((FIX / "spec_example_utterances.json").read_text()))
    roles = RolesOverlay.model_validate(json.loads((FIX / "spec_example_roles.json").read_text()))
    sources = sources_from_objects(utt, roles=roles)
    problem = Problem.model_validate(json.loads((FIX / "spec_example_registry.json").read_text()))
    item = Item.model_validate(json.loads(SPEC_6_4))
    item.owner = "B0"
    graph = Graph(pipeline_mode="baseline", entities=[problem, item])
    rehash_all(graph, roles)
    return sources, roles, graph, problem, item


def test_example_fixture_text_matches_spec_offsets():
    sources, *_ = _setup()
    assert sources.utterance("u21").text == "Cold on number three."
    assert sources.utterance("u22").text == "Ow, yes, that's sharp."
    assert sources.utterance("u24").text == "It's gone already, yeah."


def test_example_item_passes_cv():
    sources, _, _, _, item = _setup()
    assert check_spans(item, sources) == ("pass", [])
    assert check_normalization(item, sources) == ("pass", [])


def test_example_registry_passes_cv():
    sources, _, _, problem, _ = _setup()
    assert check_spans(problem, sources)[0] == "pass"
    assert check_normalization(problem, sources)[0] == "pass"


def test_example_graph_is_structurally_valid():
    _, _, graph, _, _ = _setup()
    assert validate_graph(graph) == []


def test_example_hashes_recompute_and_exclude_derived_fields():
    _, roles, graph, problem, item = _setup()
    assert item.content_hash == content_hash(item)
    assert item.support_hash == support_hash(item, roles, problem)
    changed = item.model_copy(deep=True)
    changed.target_relation = "unknown"
    changed.checks.span_valid = "fail"
    assert content_hash(changed) == item.content_hash, "derived fields and checks are outside content_hash"
    changed.target.tooth = 4
    assert content_hash(changed) != item.content_hash


def test_example_speakers_come_from_role_overlay():
    sources, _, _, _, item = _setup()
    copy = item.model_copy(deep=True)
    copy.speaker_ids, copy.roles = [], []
    fill_speakers(copy, sources)
    assert copy.speaker_ids == ["S0", "S1"] and copy.roles == ["Dentist", "Patient"]


def test_example_support_hash_tracks_problem_and_roles():
    _, roles, graph, problem, item = _setup()
    edited = problem.model_copy(deep=True)
    edited.clinical_target.tooth = 4
    edited.content_hash = content_hash(edited)
    assert support_hash(item, roles, edited) != item.support_hash
    other_roles = roles.model_copy(deep=True)
    other_roles.entries["S1"].role = "Other"
    assert support_hash(item, other_roles, problem) != item.support_hash
