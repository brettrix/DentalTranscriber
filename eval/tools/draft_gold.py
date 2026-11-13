"""Draft held-out gold from each case's transcript and answer key (section 14.2), for a person to check.

Evaluation tooling, outside the frozen configuration: its prompt is inline here and it reads, but never edits,
the frozen schemas, rules and prompts. Output is marked annotated_by "grader (claude-sonnet-5-5)" with
checked_by null; scoring must wait until a person has checked it.

SCRIBE_ALLOW_REAL=1 python -m eval.tools.draft_gold --cases case4 case5 case6 case7 case8
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from pydantic import Field

from agents.base import Agent, read_prompt, source_block
from agents.io import Out
from pipeline.rules import rule_config
from pipeline.storage import ROOT
from pipeline.trace import Tracer
from pipeline.transcribe import parse_text_transcript
from schemas.entities import ATTRIBUTE_MODELS
from schemas.gold import GoldCase, GoldEntity, GoldFlag

MODEL = "claude-sonnet-5-5"
HELDOUT = ROOT / "eval" / "heldout"
GOLD = ROOT / "eval" / "gold"

PROMPT = """# Gold drafter (evaluation only)

Your job: write the gold annotation for one dental limited-exam case, from its transcript, quick notes and the
answer key that came with the script. A person will check your draft before it is used for scoring, so be exact
and do not guess.

Entities (one per distinct clinical fact the answer key lists; small talk and forbidden facts are never entities):
- `kind`: problem, relationship, or item. Every case has exactly one problem with key_attributes.role "chief".
  Problems use `problem_key` "P1" (then "P2"…), `target` = the clinical target tooth (Universal 1–32) or null,
  and key_attributes {role, complaint_text, complaint_location} (the patient's words for where it hurts).
- Relationships: `target` = the other tooth, key_attributes {relation_kind: control | referred_from |
  adjacent_examined | secondary_problem}, only when the script states it.
- Items: `type` from the attribute table below; `scope` encounter for history_change, medication, allergy and
  vital_reading (problem_key null), otherwise problem (problem_key "P1" unless it belongs to another problem);
  `target` = tooth number or null; `target_relation` = matches_target when the tooth is the problem's clinical
  target, otherwise the relationship kind, or unknown.
- `key_attributes` hold the clinical values, using the attribute names in the table (plus "surface" for a tooth
  surface code, and "option" with the option's text for a decision). Numbers as numbers; doses like "500 mg";
  frequencies as TID, BID, q6h PRN; durations as whole days; drug names as lowercase generics.
- Status enums go in `status_fields` (allergy_status, medication_status, prescription_status); a radiograph's
  action goes in `action`.
- `assertion`: present, absent (clinician says it isn't there), denied (patient says no), possible (hedged).
  `time_context`: current, historical, planned (next_visit items are planned).
- `assertion_source`: patient_report, clinician_observation, test_response, clinician_assessment,
  clinician_instruction, assistant_record (quick notes the assistant typed).
- `evidence`: every source line the fact depends on, as {"utterance_id": "u12"} or {"quick_note_id": "q2"},
  using the ids shown in the sources. Cite a clinician's question together with the patient's answer.
- `gid`: short unique ids (p1, s1, f1, x1, d1, o1, dc1, c1, rx1, n1, i1, v1, a1, m1, h1).
- Use `note` for anything a checker should look at (an ambiguous certainty, a fact the answer key implies but
  the script states only loosely).

Expected flags: only the ones the answer key names, with `rule_id` from the rule list below, `problem_key`,
`target` (tooth or null), `meaning` (one sentence), and `evidence` ids. Do not add flags the answer key doesn't
name. Also return the answer key's forbidden facts and expected decision.
"""


class DraftOutput(Out):
    entities: list[GoldEntity]
    expected_flags: list[GoldFlag] = Field(default_factory=list)
    forbidden_facts: list[str] = Field(default_factory=list)
    expected_decision: Optional[str] = None


class GoldDrafter(Agent):
    name = "GoldDrafter"
    output_model = DraftOutput
    tool_name = "submit_gold"
    tool_description = "Submit the complete gold annotation for this case."

    def system_prompt(self) -> str:
        table = "\n".join(f"- {t}: {', '.join(m.model_fields)}" for t, m in ATTRIBUTE_MODELS.items())
        rules = ", ".join(rule_config()["rules"]) + ", perio_rationale, endo_findings_review, diagnosis_without_findings"
        return (read_prompt("_shared_rules.md") + "\n\n" + PROMPT + "\n## Attribute table\n" + table +
                "\n\n## Rule ids\n" + rules)

    def draft(self, case_dir: Path):
        utts, roles = parse_text_transcript((case_dir / "transcript.txt").read_text("utf-8"))
        transcript = "\n".join(f"[{u.id}] ({u.speaker} {roles[u.speaker].role}) {u.text}" for u in utts)
        notes = [l.strip() for l in (case_dir / "quick_notes.txt").read_text("utf-8").splitlines() if l.strip()]
        quick = "\n".join(f"[q{i + 1}] {t}" for i, t in enumerate(notes)) or "(none)"
        body = "\n\n".join([source_block("transcript", transcript), source_block("quick notes", quick),
                            source_block("answer key", (case_dir / "answer_key.md").read_text("utf-8"))])
        return self.call(body + "\n\nWrite the gold annotation for this case.", label=f"gold:{case_dir.name}")


def check_ids(case: GoldCase, case_dir: Path) -> list[str]:
    utts, _ = parse_text_transcript((case_dir / "transcript.txt").read_text("utf-8"))
    n_notes = len([l for l in (case_dir / "quick_notes.txt").read_text("utf-8").splitlines() if l.strip()])
    ok = {u.id for u in utts} | {f"q{i + 1}" for i in range(n_notes)}
    bad = []
    for e in case.entities:
        for ev in e.evidence:
            sid = ev.utterance_id or ev.quick_note_id
            if sid not in ok:
                bad.append(f"{e.gid}: unknown evidence id {sid}")
    chiefs = [e for e in case.entities if e.kind == "problem" and e.key_attributes.get("role") == "chief"]
    if len(chiefs) != 1:
        bad.append(f"{len(chiefs)} chief problems")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", required=True)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    out_dir = ROOT / "eval" / "results" / "heldout-gold-draft"
    out_dir.mkdir(parents=True, exist_ok=True)
    tracer = Tracer(path=out_dir / "gold_drafter_traces.jsonl")
    cfg = {"model": MODEL, "effort": "medium", "max_tokens": 16000, "timeout_s": 240, "fallbacks": "default"}
    for name in args.cases:
        target = GOLD / f"{name}.json"
        if target.exists() and not args.overwrite:
            print(f"{name}: gold exists, skipped")
            continue
        case_dir = HELDOUT / name
        out = GoldDrafter(tracer=tracer, config=cfg).draft(case_dir)
        case = GoldCase(case_id=name, annotated_by=f"grader ({MODEL})", checked_by=None,
                        entities=out.entities, expected_flags=out.expected_flags,
                        forbidden_facts=out.forbidden_facts, expected_decision=out.expected_decision,
                        notes="Drafted by the gold drafter from the transcript and answer key. Must be checked by a "
                              "person (fill checked_by) before held-out scoring.")
        problems = check_ids(case, case_dir)
        target.write_text(json.dumps(case.model_dump(mode="json"), indent=1) + "\n", "utf-8")
        print(f"{name}: {len(case.entities)} entities, {len(case.expected_flags)} expected flags, "
              f"problems: {problems or 'none'}")


if __name__ == "__main__":
    main()
