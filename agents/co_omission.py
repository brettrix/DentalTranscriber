"""Co Omission Check: clinical statements no entity covers (team mode)."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from agents.base import Agent
from agents.extract_common import sources_text
from agents.io import Out, Quote


class Omission(Out):
    statement: str
    suggested_type: Optional[str] = Field(default=None, description="item type, or 'problem'/'relationship'")
    evidence: list[Quote]


class CoOutput(Out):
    omissions: list[Omission] = Field(default_factory=list)


class CoOmissionAgent(Agent):
    name = "Co"
    prompt_file = "co_omission.md"
    output_model = CoOutput
    tool_name = "submit_omissions"
    tool_description = "Submit every clinical statement no listed entity covers (empty list if none)."

    def find(self, sources, entity_list: str, attempt: int = 1):
        return self.call(sources_text(sources) + "\n\nEntities already recorded (type, target, key attributes, "
                                                 "evidence ids):\n" + entity_list +
                         "\n\nList clinical statements in the sources that none of these entities covers.",
                         label="omissions", attempt=attempt)
