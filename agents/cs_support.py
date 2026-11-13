"""Cs Semantic Support Check: blind re-extraction from an evidence window (team mode, one call per section)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from agents.base import Agent, read_prompt, source_block
from agents.io import Out, Quote, attribute_table

UNKNOWN = "unknown_from_window"


class ExtraAssertion(Out):
    description: str
    suggested_type: Optional[str] = None
    evidence: list[Quote] = Field(default_factory=list)


class WindowResult(Out):
    window_id: str
    values: dict[str, Any] = Field(description="attribute path -> value, null, or 'unknown_from_window'")
    extra_assertions: list[ExtraAssertion] = Field(default_factory=list)


class CsOutput(Out):
    windows: list[WindowResult]


class CsSupportAgent(Agent):
    name = "Cs"
    prompt_file = "cs_support.md"
    output_model = CsOutput
    tool_name = "submit_window_extractions"
    tool_description = "Submit what each evidence window asserts, one result per window."

    def system_prompt(self) -> str:
        return super().system_prompt() + "\n\n" + read_prompt("_extraction_guide.md")

    def check(self, section: str, windows: list[dict], problem_list: str | None, item_types: list[str], attempt: int = 1):
        parts = []
        if item_types:
            parts.append("Attribute table:\n" + attribute_table(item_types))
        if problem_list is not None:
            parts.append(source_block("problem list (raw complaint evidence only)", problem_list))
        for w in windows:
            body = f"window_id: {w['window_id']}\nentity to extract: {w['what']}\nfill these paths: " \
                   f"{', '.join(w['paths'])}\nfocus quotes:\n" + "\n".join(f"  [{q['source_id']}] {q['quote']}"
                                                                          for q in w["focus"]) + \
                   "\nwindow:\n" + w["window_text"]
            parts.append(source_block(f"window {w['window_id']}", body))
        parts.append(f"Section: {section}. For every window, extract the one assertion its focus quotes make.")
        return self.call("\n\n".join(parts), label=f"check:{section}", attempt=attempt)
