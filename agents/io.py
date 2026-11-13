"""What extraction agents return (before the Linker turns it into graph entities), plus prompt helpers."""
from __future__ import annotations

import typing
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from schemas.entities import ATTRIBUTE_MODELS, ITEM_SCOPES

AssertionSourceT = Literal["patient_report", "clinician_assessment", "clinician_observation", "test_response",
                           "clinician_instruction", "assistant_record", "unknown"]


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Quote(Out):
    source_type: Literal["transcript", "quick_note", "visit_meta"]
    source_id: str = Field(description="Utterance id like u12, or quick-note id like q2")
    quote: str = Field(description="Exact characters copied from that one source line")


class DerivationOut(Out):
    attribute: str = Field(description="Path of the value, e.g. target.tooth, attributes.strength")
    rule: str = Field(description="spoken_number | spoken_tooth_number | bp_reading | dose | frequency | duration | "
                                  "surface_code | drug_name | mm_measure | semantic | negation")
    from_: str = Field(alias="from", description="The exact words inside the cited quote this value comes from")
    to: Any = Field(default=None, description="The resulting value, identical to the entity's value")
    evidence_index: int = Field(default=0, description="Index into this entity's evidence list")
    concept: Optional[str] = Field(default=None, description="negation only: the words naming what is negated")
    concept_evidence_index: Optional[int] = None


class LocationOut(Out):
    free_text: Optional[str] = None
    tooth: Optional[int] = None


class ProblemOut(Out):
    key: str = Field(description="Local key like P1")
    id: Optional[str] = Field(default=None, description="Existing graph id, only when revising")
    role: Literal["chief", "secondary"]
    complaint_text: Optional[str] = None
    complaint_location: LocationOut = Field(default_factory=LocationOut,
                                            description="Where the PATIENT says it hurts")
    clinical_target: LocationOut = Field(default_factory=LocationOut,
                                         description="The tooth the CLINICIAN identified as the problem")
    assertion_source: AssertionSourceT
    evidence: list[Quote]
    derivations: list[DerivationOut] = Field(default_factory=list)


class RelationshipOut(Out):
    key: str = Field(description="Local key like R1")
    id: Optional[str] = None
    problem_key: str = Field(description="Key (or existing id) of the problem this relates to")
    tooth: int
    relation_kind: Literal["control", "referred_from", "adjacent_examined", "secondary_problem"]
    note: Optional[str] = None
    assertion_source: AssertionSourceT
    evidence: list[Quote]
    derivations: list[DerivationOut] = Field(default_factory=list)


class TargetOut(Out):
    tooth: Optional[int] = None
    surface: Optional[str] = None
    site: Optional[str] = None
    free_text: Optional[str] = None


class ItemOut(Out):
    key: str = Field(description="Local key like F1")
    id: Optional[str] = Field(default=None, description="Existing graph id, only when revising")
    type: Literal[tuple(ATTRIBUTE_MODELS)]  # type: ignore[valid-type]
    problem_key: Optional[str] = Field(default=None, description="Problem key or id; null for encounter items")
    target: TargetOut = Field(default_factory=TargetOut)
    attributes: dict[str, Any] = Field(default_factory=dict)
    option_key: Optional[str] = Field(default=None, description="decision/consent_element: key or id of the option")
    decision_key: Optional[str] = Field(default=None, description="consent_element: key or id of the decision")
    assertion: Literal["present", "absent", "denied", "possible", "unintelligible"] = "present"
    time_context: Literal["current", "historical", "planned"] = "current"
    assertion_source: AssertionSourceT
    evidence: list[Quote]
    derivations: list[DerivationOut] = Field(default_factory=list)


class RegistryOutput(Out):
    problems: list[ProblemOut]
    relationships: list[RelationshipOut] = Field(default_factory=list)


class ItemsOutput(Out):
    items: list[ItemOut] = Field(default_factory=list)


class FullOutput(Out):
    problems: list[ProblemOut]
    relationships: list[RelationshipOut] = Field(default_factory=list)
    items: list[ItemOut] = Field(default_factory=list)


class RepairOutput(Out):
    items: list[ItemOut] = Field(default_factory=list,
                                 description="Revised items (keep their id) and new items (no id)")
    unresolved: list[str] = Field(default_factory=list, description="Issue ids you could not fix from the sources")


# ---------------------------------------------------------------- prompt helpers

def _type_label(annotation) -> str:
    args = typing.get_args(annotation)
    lits = [a for a in args if typing.get_origin(a) is Literal]
    if typing.get_origin(annotation) is Literal:
        return " | ".join(map(str, typing.get_args(annotation)))
    if lits:
        return " | ".join(map(str, typing.get_args(lits[0])))
    names = [getattr(a, "__name__", str(a)) for a in args if a is not type(None)]
    return names[0] if names else getattr(annotation, "__name__", str(annotation))


LINKER_SET = {"option_id", "decision_id", "link", "option_link"}  # set by the Linker from option_key/decision_key


def attribute_table(item_types: list[str]) -> str:
    lines = []
    for t in item_types:
        model = ATTRIBUTE_MODELS[t]
        parts = []
        for name, info in model.model_fields.items():
            if name in LINKER_SET:
                continue
            meta = info.json_schema_extra or {}
            rule = f" [derive: {meta['rule']}]" if meta.get("rule") else ""
            parts.append(f"{name}: {_type_label(info.annotation)}{rule}")
        scope = "/".join(sorted(ITEM_SCOPES[t]))
        lines.append(f"- {t} (scope {scope}): " + "; ".join(parts))
    return "\n".join(lines)
