"""R2 Contradiction Detection (both modes, Stage C)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from agents.base import Agent
from agents.extract_common import sources_text
from agents.io import Out, Quote


class ContradictionOut(Out):
    kind: Literal["self_correction", "contradiction"]
    subject: str = Field(description="What the statements are about, e.g. 'tooth number of the cold test'")
    first: Quote
    second: Quote
    later: Literal["first", "second", "unknown"] = Field(
        description="Which statement came later; quick notes have no time, so use 'unknown' when one is a quick note")
    explanation: Optional[str] = None
    suggested_type: Optional[str] = Field(default=None, description="Item type the subject belongs to, e.g. finding, "
                                          "vital_reading, prescription; or problem")


class R2Output(Out):
    findings: list[ContradictionOut] = Field(default_factory=list)


class R2ContradictionAgent(Agent):
    name = "R2"
    prompt_file = "r2_contradictions.md"
    output_model = R2Output
    tool_name = "submit_contradictions"
    tool_description = "Submit every self-correction and contradiction found (empty list if none)."

    def detect(self, sources):
        return self.call(sources_text(sources) + "\n\nFind self-corrections and contradictions in these sources.",
                         label="detect")
