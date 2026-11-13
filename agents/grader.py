"""Grader (eval only): free-text equivalence for matching, and claim support for rendered attributes."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from agents.base import Agent, source_block
from agents.extract_common import sources_text
from agents.io import Out


class PairGrade(Out):
    pair_id: str
    verdict: Literal["equivalent", "different", "uncertain"]
    confidence: float = Field(ge=0, le=1)


class EquivalenceOutput(Out):
    grades: list[PairGrade]


class ClaimGrade(Out):
    claim_id: str
    label: Literal["supported_by_transcript", "supported_by_quick_notes", "supported_by_visit_meta",
                   "supported_only_by_reviewer_entry", "unsupported", "changed_meaning"]
    quote: Optional[str] = None
    confidence: float = Field(ge=0, le=1)


class ClaimOutput(Out):
    grades: list[ClaimGrade]


class GraderEquivalence(Agent):
    name = "Grader"
    prompt_file = "grader_equivalence.md"
    output_model = EquivalenceOutput
    tool_name = "submit_grades"
    tool_description = "Submit one grade per pair."

    def grade(self, pairs: list[dict]):
        lines = [f"- pair_id {p['pair_id']} | {p['attribute']} | gold: {p['gold']!r} | produced: {p['produced']!r}"
                 for p in pairs]
        return self.call("Pairs:\n" + "\n".join(lines), label="equivalence")


class GraderClaims(Agent):
    name = "Grader"
    prompt_file = "grader_claims.md"
    output_model = ClaimOutput
    tool_name = "submit_claim_grades"
    tool_description = "Submit one grade per claim."

    def grade(self, sources, claims: list[dict], human_entries: str):
        lines = [f"- claim_id {c['claim_id']} | {c['attribute']} = {c['value']!r} (line: {c['line']!r})" for c in claims]
        return self.call(sources_text(sources) + "\n\n" + source_block("reviewer entries", human_entries or "(none)")
                         + "\n\nClaims to grade:\n" + "\n".join(lines), label="claims")
