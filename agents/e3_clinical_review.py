"""E3 Clinical Review Agent: turns runnable review rules into questions for the dentist. Never edits entities."""
from __future__ import annotations

from pydantic import Field

from agents.base import Agent
from agents.io import Out


class Question(Out):
    rule_id: str
    rule_version: str
    entity_ids: list[str] = Field(description="Ids of the entities the question is about (from the rule's list)")
    question: str


class E3Output(Out):
    questions: list[Question] = Field(default_factory=list)


class E3ClinicalReviewAgent(Agent):
    name = "E3"
    prompt_file = "e3_clinical_review.md"
    output_model = E3Output
    tool_name = "submit_questions"
    tool_description = "Submit one review question per runnable rule instance."

    def review(self, rule_instances: list[dict]):
        blocks = []
        for r in rule_instances:
            blocks.append(f"rule {r['rule_id']} v{r['version']}: {r['description']}\nsuggested wording: "
                          f"{r['template']}\nentities:\n" + "\n".join(f"  - {e}" for e in r["entities"]))
        return self.call("Runnable review rules and the documented entities each one concerns:\n\n" +
                         "\n\n".join(blocks), label="review")
