"""Shared extractor behaviour for B0, Br and B1-B4: build the source block, extract, and repair."""
from __future__ import annotations

import json

from agents.base import Agent, read_prompt, source_block
from agents.io import ItemsOutput, RepairOutput, attribute_table
from pipeline.template import types_of_agent


# Extraction guidance added after the evaluation configuration was frozen. It lives here, not in prompts/, so the
# frozen prompt files and their hashes stay exactly as the held-out run used them. It is sent after the guide.
EXTRACTION_ADDENDUM = """## Additions to the guide (these take precedence where they differ)
- Allergy `reaction` holds only a reaction that was actually stated (hives, rash, swelling, trouble breathing, upset stomach). If no reaction was stated, `reaction` is null. Never put a hedge or filler ("I think", "maybe", "not sure") in `reaction`: uncertainty belongs in `allergy_status` (uncertain, reported_resolved) and stays in the quote.
- Finding results: when a test or check has a described result beyond positive or negative, such as what was seen, felt or marked ("heavy mark on the new filling" for a bite-paper check, "catches on the distal margin"), put those words in `result_description`. Keep it; don't drop it and don't fold it into `test`.
- Quick-note labels such as "Tx: #3", "Tooth: #3" or "Dx: #3" only identify a tooth. A line that is just a label and a tooth is not evidence that a treatment was done today, planned, or diagnosed: never create a `treatment_today`, `next_visit`, `diagnosis`, `option_discussed` or `decision` item from it. A quick note that names an actual procedure ("Tx: temp filling #3") can be extracted.
- A quick note "Allergy: none" (or "NKDA") is one allergy item with `substance` null, `allergy_status` denied and assertion denied. Do not copy the note's text into `substance` or `original_wording`."""


def sources_text(sources) -> str:
    vm = sources.visit_meta
    meta = f"date: {vm.date or 'unknown'}; provider: {vm.provider or 'unknown'}; assistant: {vm.assistant or 'unknown'}; " \
           f"visit type: {vm.visit_type}"
    return "\n\n".join([
        source_block("visit_meta", meta),
        source_block("transcript (each line: [utterance id] (speaker id, role) text)", sources.transcript_block()),
        source_block("quick notes (each line: [note id] text)", sources.quick_notes_block()),
    ])


def registry_text(graph_problems, graph_relationships) -> str:
    """The registry B1-B4 receive: problem keys, complaint text, clinical targets, relationships."""
    lines = []
    for p in graph_problems:
        lines.append(f"- problem_key {p['key']}: role {p['role']}; complaint: {p.get('complaint_text')!r}; "
                     f"patient-reported location: {p.get('complaint_location')}; clinical target: {p.get('clinical_target')}")
    for r in graph_relationships:
        lines.append(f"- relationship: tooth {r['tooth']} is {r['relation_kind']} for problem {r['problem_key']}")
    return "\n".join(lines) or "(no problems registered)"


class ExtractorAgent(Agent):
    item_types: list[str] = []
    tool_name = "submit_extraction"
    tool_description = "Submit every entity you extracted."

    def system_prompt(self) -> str:
        return (super().system_prompt() + "\n\n" + read_prompt("_extraction_guide.md") + "\n\n" + EXTRACTION_ADDENDUM +
                "\n\n## Attribute table for your item types\n" + attribute_table(self.types()))

    def types(self) -> list[str]:
        return self.item_types or types_of_agent(self.name)

    def extract(self, sources, registry: str | None = None):
        parts = [sources_text(sources)]
        if registry is not None:
            parts.append("Problem registry (link problem-scoped items with these problem keys):\n" + registry)
        parts.append(f"Extract your entity types ({', '.join(self.types())}) from the sources above.")
        return self.call("\n\n".join(parts), label="extract")

    def repair(self, sources, issues: list[dict], entities: list[dict], registry: str | None = None):
        """One repair call for all of this agent's open issues (section 10)."""
        parts = [sources_text(sources)]
        if registry is not None:
            parts.append("Problem registry:\n" + registry)
        parts.append(read_prompt("_repair.md"))
        parts.append("Your current entities (graph ids shown as `id`):\n" + json.dumps(entities, indent=1))
        parts.append("Open issues:\n" + json.dumps(issues, indent=1))
        agent = _RepairView(self)
        return agent.call("\n\n".join(parts), label="repair", attempt=2)


class _RepairView(Agent):
    """The same agent and prompt, returning RepairOutput."""
    output_model = RepairOutput
    tool_name = "submit_repair"
    tool_description = "Submit revised items (same id) and new items (no id), and the issues you could not fix."

    def __init__(self, base: ExtractorAgent):
        super().__init__(client=base._client, tracer=base.tracer, config=base.config)
        self.name = base.name
        self._base = base

    def system_prompt(self) -> str:
        return self._base.system_prompt()
