"""Ce Equivalence Check: free-text meaning comparison, batched per section, no sources."""
from __future__ import annotations

from typing import Literal

from agents.base import Agent
from agents.io import Out


class PairVerdict(Out):
    pair_id: str
    verdict: Literal["equivalent", "different", "uncertain"]


class CeOutput(Out):
    verdicts: list[PairVerdict]


class CeEquivalenceAgent(Agent):
    name = "Ce"
    prompt_file = "ce_equivalence.md"
    output_model = CeOutput
    tool_name = "submit_verdicts"
    tool_description = "Submit one verdict per pair."

    def compare(self, section: str, pairs: list[dict], attempt: int = 1):
        lines = [f"- pair_id {p['pair_id']} | attribute {p['attribute']} | A: {p['a']!r} | B: {p['b']!r}" for p in pairs]
        return self.call(f"Section: {section}\nPairs:\n" + "\n".join(lines), label=f"compare:{section}", attempt=attempt)
