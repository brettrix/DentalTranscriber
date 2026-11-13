"""Entities: problems, relationships, items (sections 6.1-6.3).

Every clinical attribute declares how Cs compares it (section 8): exact, normalized (after a 7.2 rule),
semantic (through Ce), or excluded with a reason. `rule` names the deterministic rule Cv requires a derivation
for; `critical` marks attributes whose `unknown_from_window` makes a semantic check `unconfirmed`.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CheckSummary = Literal["pass", "fail", "unconfirmed", "not_run", "not_applicable", "not_assessed_due_to_failure"]
SourceType = Literal["transcript", "quick_note", "visit_meta", "human_entry"]
AssertionSource = Literal["patient_report", "clinician_assessment", "clinician_observation", "test_response",
                          "clinician_instruction", "assistant_record", "unknown"]
Status = Literal["active", "stale", "superseded"]
Role = Literal["Dentist", "Assistant", "Patient", "Other"]


def attr(compare: str, *, rule: str | None = None, critical: bool = False, reason: str | None = None,
         default: Any = None):
    assert compare in ("exact", "normalized", "semantic", "excluded")
    assert compare != "excluded" or reason, "excluded attributes need a reason"
    assert compare != "normalized" or rule, "normalized attributes need a rule"
    return Field(default=default, json_schema_extra={"compare": compare, "rule": rule, "critical": critical,
                                                     "reason": reason})


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Span(Strict):
    source_type: SourceType
    source_id: str
    source_version: int = 1
    start: Optional[int] = None
    end: Optional[int] = None
    text: str
    correction_id: Optional[str] = None
    correction_version: Optional[int] = None


class Derivation(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    attribute: str
    rule: str
    from_: str = Field(alias="from")
    to: Any = None
    evidence_index: int = 0
    # Negation derivations (rule "negation") name the concept the cue applies to and where it appears.
    concept: Optional[str] = None
    concept_evidence_index: Optional[int] = None


class Checks(Strict):
    span_valid: CheckSummary = "not_run"
    normalization_valid: CheckSummary = "not_run"
    semantic_support: CheckSummary = "not_run"


# ---------------------------------------------------------------- item attributes (section 6.3)

class HistoryChangeAttrs(Strict):
    description: Optional[str] = attr("semantic")


class MedicationAttrs(Strict):
    drug: Optional[str] = attr("normalized", rule="drug_name", critical=True)
    strength: Optional[str] = attr("normalized", rule="dose", critical=True)
    dose: Optional[str] = attr("normalized", rule="dose", critical=True)
    route: Optional[str] = attr("exact")
    frequency: Optional[str] = attr("normalized", rule="frequency", critical=True)
    medication_status: Optional[Literal["current", "discontinued", "historical", "unknown"]] = attr("exact", critical=True)
    original_wording: Optional[str] = attr("excluded", reason="verbatim wording; the normalized drug is compared")


class AllergyAttrs(Strict):
    substance: Optional[str] = attr("normalized", rule="drug_name", critical=True)
    reaction: Optional[str] = attr("semantic")
    allergy_status: Optional[Literal["reported_active", "denied", "uncertain", "disputed", "reported_resolved"]] = attr(
        "exact", critical=True)
    original_wording: Optional[str] = attr("excluded", reason="verbatim substance wording when not in the drug table")


class VitalReadingAttrs(Strict):
    systolic: Optional[int] = attr("normalized", rule="bp_reading", critical=True)
    diastolic: Optional[int] = attr("normalized", rule="bp_reading", critical=True)
    unit: Literal["mmHg"] = attr("exact", default="mmHg")
    sequence: Optional[int] = attr("excluded", reason="bookkeeping order number, not a source value")
    label: Optional[Literal["initial", "recheck"]] = attr("exact")


class SymptomAttrs(Strict):
    aspect: Optional[Literal["onset", "duration", "quality", "trigger", "lingering", "severity", "swelling",
                             "night_pain", "spontaneous_pain", "prior_treatment", "location", "biting_pain",
                             "other"]] = attr("semantic")
    value: Optional[str] = attr("semantic")
    score: Optional[float] = attr("normalized", rule="spoken_number", critical=True)


class FindingAttrs(Strict):
    test: Optional[str] = attr("semantic")
    observation: Optional[str] = attr("semantic")
    response: Optional[Literal["present", "absent", "uncertain"]] = attr("exact", critical=True)
    result_description: Optional[str] = attr("semantic")
    intensity: Optional[str] = attr("semantic")
    lingering: Optional[bool] = attr("exact", critical=True)
    duration_s: Optional[float] = attr("normalized", rule="spoken_number")


class PerioMeasurementAttrs(Strict):
    site: Optional[Literal["DB", "B", "MB", "DL", "L", "ML"]] = attr("exact", critical=True)
    probing_depth_mm: Optional[float] = attr("normalized", rule="mm_measure", critical=True)
    bleeding: Optional[bool] = attr("exact")
    recession_mm: Optional[float] = attr("normalized", rule="mm_measure")
    attachment_loss_mm: Optional[float] = attr("normalized", rule="mm_measure")


class RadiographAttrs(Strict):
    type: Optional[Literal["PA", "BWX", "FMX", "pano"]] = attr("exact", critical=True)
    target: Optional[str] = attr("semantic")
    finding: Optional[str] = attr("semantic")
    bone_loss: Optional[bool] = attr("exact")
    action: Optional[Literal["performed", "discussed", "planned", "declined", "not_needed"]] = attr("exact", critical=True)


class DiagnosisAttrs(Strict):
    diagnosis: Optional[str] = attr("semantic", critical=True)
    certainty: Optional[Literal["definite", "possible"]] = attr("exact", critical=True)


class OptionDiscussedAttrs(Strict):
    option: Optional[str] = attr("semantic", critical=True)
    risks: Optional[str] = attr("semantic")
    benefits: Optional[str] = attr("semantic")
    recommended_by_clinician: Optional[bool] = attr("exact", critical=True)


class DecisionAttrs(Strict):
    option_id: Optional[str] = attr("excluded", reason="graph id; the link status and option text are compared")
    option_link: Optional[Literal["linked", "unknown"]] = attr("exact")
    decision: Optional[Literal["accepted", "declined", "deferred", "undecided", "monitor"]] = attr("exact", critical=True)
    reason: Optional[str] = attr("semantic")


class ConsentElementAttrs(Strict):
    element: Optional[Literal["risks_discussed", "benefits_discussed", "alternatives_discussed",
                              "consequences_of_refusal_discussed", "questions_answered"]] = attr("exact", critical=True)
    content: Optional[str] = attr("semantic")
    option_id: Optional[str] = attr("excluded", reason="graph id")
    decision_id: Optional[str] = attr("excluded", reason="graph id")
    link: Optional[Literal["linked", "unknown"]] = attr("exact")


class TreatmentTodayAttrs(Strict):
    procedure: Optional[str] = attr("semantic", critical=True)


class PrescriptionAttrs(Strict):
    drug: Optional[str] = attr("normalized", rule="drug_name", critical=True)
    strength: Optional[str] = attr("normalized", rule="dose", critical=True)
    dose: Optional[str] = attr("normalized", rule="dose", critical=True)
    route: Optional[str] = attr("exact")
    frequency_code: Optional[str] = attr("normalized", rule="frequency", critical=True)
    duration_days: Optional[int] = attr("normalized", rule="duration", critical=True)
    as_needed: Optional[bool] = attr("exact")
    prescription_status: Optional[Literal["prescribed_today", "discussed_not_prescribed", "continuing"]] = attr(
        "exact", critical=True)
    original_wording: Optional[str] = attr("excluded", reason="verbatim wording; normalized fields are compared")


class ReferralAttrs(Strict):
    to: Optional[str] = attr("semantic", critical=True)
    purpose: Optional[str] = attr("semantic")


class NextVisitAttrs(Strict):
    procedure: Optional[str] = attr("semantic", critical=True)
    timing: Optional[str] = attr("semantic")


class InstructionAttrs(Strict):
    text: Optional[str] = attr("semantic")


ATTRIBUTE_MODELS: dict[str, type[Strict]] = {
    "history_change": HistoryChangeAttrs,
    "medication": MedicationAttrs,
    "allergy": AllergyAttrs,
    "vital_reading": VitalReadingAttrs,
    "symptom": SymptomAttrs,
    "finding": FindingAttrs,
    "perio_measurement": PerioMeasurementAttrs,
    "radiograph": RadiographAttrs,
    "diagnosis": DiagnosisAttrs,
    "option_discussed": OptionDiscussedAttrs,
    "decision": DecisionAttrs,
    "consent_element": ConsentElementAttrs,
    "treatment_today": TreatmentTodayAttrs,
    "prescription": PrescriptionAttrs,
    "referral": ReferralAttrs,
    "next_visit": NextVisitAttrs,
    "instruction": InstructionAttrs,
}
ItemType = Literal["history_change", "medication", "allergy", "vital_reading", "symptom", "finding",
                   "perio_measurement", "radiograph", "diagnosis", "option_discussed", "decision", "consent_element",
                   "treatment_today", "prescription", "referral", "next_visit", "instruction"]

ITEM_SCOPES: dict[str, set[str]] = {
    "history_change": {"encounter"}, "medication": {"encounter"}, "allergy": {"encounter"},
    "vital_reading": {"encounter"}, "prescription": {"problem", "encounter"}, "instruction": {"problem", "encounter"},
}
for _t in ATTRIBUTE_MODELS:
    ITEM_SCOPES.setdefault(_t, {"problem"})

TREATMENT_BEARING = {"diagnosis", "option_discussed", "decision", "treatment_today", "next_visit"}
CRITICAL_TYPES = {"allergy", "medication", "prescription", "vital_reading", "diagnosis", "decision", "consent_element"}


# ---------------------------------------------------------------- entities

class EntityCommon(Strict):
    id: str
    version: int = 1
    content_hash: Optional[str] = None
    support_hash: Optional[str] = None
    status: Status = "active"
    evidence: list[Span] = Field(default_factory=list)
    derivations: list[Derivation] = Field(default_factory=list)
    speaker_ids: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    assertion_source: AssertionSource = "unknown"
    checks: Checks = Field(default_factory=Checks)
    dispositions: list[str] = Field(default_factory=list)
    # Bookkeeping, outside content_hash: who produced it, its local key, and supersession links.
    owner: Optional[str] = None
    local_key: Optional[str] = None
    superseded_by: Optional[str] = None
    supersede_reason: Optional[str] = None

    @property
    def is_human(self) -> bool:
        return bool(self.evidence) and all(s.source_type == "human_entry" for s in self.evidence)

    @property
    def ref(self) -> str:
        return f"{self.id}@{self.version}"


class Location(Strict):
    free_text: Optional[str] = attr("semantic")
    tooth: Optional[int] = attr("normalized", rule="spoken_tooth_number", critical=True)


class Problem(EntityCommon):
    kind: Literal["problem"] = "problem"
    key: str = attr("excluded", reason="local key", default="")
    role: Literal["chief", "secondary"] = attr("exact", critical=True, default="chief")
    complaint_text: Optional[str] = attr("semantic")
    complaint_location: Location = Field(default_factory=Location)
    clinical_target: Location = Field(default_factory=Location)


class Relationship(EntityCommon):
    kind: Literal["relationship"] = "relationship"
    problem_id: str = attr("exact", critical=True, default="")
    tooth: Optional[int] = attr("normalized", rule="spoken_tooth_number", critical=True)
    relation_kind: Literal["control", "referred_from", "adjacent_examined", "secondary_problem"] = attr(
        "exact", critical=True, default="control")
    note: Optional[str] = attr("semantic")


class ItemTarget(Strict):
    tooth: Optional[int] = attr("normalized", rule="spoken_tooth_number", critical=True)
    surface: Optional[str] = attr("normalized", rule="surface_code")
    site: Optional[str] = attr("exact")
    free_text: Optional[str] = attr("semantic")


TargetRelation = Literal["matches_target", "control", "referred_from", "adjacent_examined", "secondary_problem",
                         "unknown"]


class Item(EntityCommon):
    kind: Literal["item"] = "item"
    type: ItemType = attr("exact", critical=True, default="instruction")
    scope: Literal["encounter", "problem"] = attr("exact", default="encounter")
    problem_id: Optional[str] = attr("exact", critical=True)
    target: ItemTarget = Field(default_factory=ItemTarget)
    target_relation: Optional[TargetRelation] = attr("excluded", reason="Stage D derived field")
    attributes: dict[str, Any] = Field(default_factory=dict)
    assertion: Literal["present", "absent", "denied", "possible", "unintelligible"] = attr(
        "exact", critical=True, default="present")
    time_context: Literal["current", "historical", "planned"] = attr("exact", critical=True, default="current")

    @model_validator(mode="after")
    def _validate_attributes(self):
        model = ATTRIBUTE_MODELS[self.type]
        self.attributes = model.model_validate(self.attributes).model_dump()
        return self

    def attrs(self):
        return ATTRIBUTE_MODELS[self.type].model_validate(self.attributes)


Entity = Annotated[Union[Problem, Relationship, Item], Field(discriminator="kind")]

# Top-level compare declarations for fields not on the Field() metadata of EntityCommon.
COMMON_COMPARE = {
    "assertion_source": {"compare": "exact", "critical": True, "rule": None},
    "evidence": {"compare": "excluded", "reason": "span boundaries need only overlap"},
    "derivations": {"compare": "excluded", "reason": "checked by Cv"},
    "speaker_ids": {"compare": "excluded", "reason": "set by Linker from the role overlay"},
    "roles": {"compare": "excluded", "reason": "set by Linker from the role overlay"},
}


def field_meta(model: type[BaseModel], name: str) -> dict:
    info = model.model_fields[name]
    return dict(info.json_schema_extra or {})


def compare_table(entity_kind: str, item_type: str | None = None) -> dict[str, dict]:
    """Flattened attribute path -> compare declaration for one entity kind/type."""
    out: dict[str, dict] = {"assertion_source": COMMON_COMPARE["assertion_source"]}
    if entity_kind == "problem":
        for name in ("key", "role", "complaint_text"):
            out[name] = field_meta(Problem, name)
        for loc in ("complaint_location", "clinical_target"):
            for name in Location.model_fields:
                out[f"{loc}.{name}"] = field_meta(Location, name)
    elif entity_kind == "relationship":
        for name in ("problem_id", "tooth", "relation_kind", "note"):
            out[name] = field_meta(Relationship, name)
    else:
        for name in ("type", "scope", "problem_id", "assertion", "time_context", "target_relation"):
            out[name] = field_meta(Item, name)
        for name in ItemTarget.model_fields:
            out[f"target.{name}"] = field_meta(ItemTarget, name)
        model = ATTRIBUTE_MODELS[item_type]
        for name in model.model_fields:
            out[f"attributes.{name}"] = field_meta(model, name)
    return out


def get_path(entity: Any, path: str):
    cur: Any = entity
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


def set_path(data: dict, path: str, value) -> None:
    parts = path.split(".")
    cur = data
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def entity_section(entity) -> str:
    """Template section id an entity renders in (also the Cs/Co batching unit)."""
    if entity.kind in ("problem", "relationship"):
        return "chief_complaint"
    return ITEM_SECTION[entity.type]


ITEM_SECTION = {
    "history_change": "medical_history", "medication": "medical_history", "allergy": "medical_history",
    "vital_reading": "medical_history", "symptom": "hpi", "finding": "clinical_findings",
    "perio_measurement": "perio", "radiograph": "radiographs", "diagnosis": "assessment",
    "option_discussed": "options", "decision": "decision", "consent_element": "discussion_elements",
    "treatment_today": "treatment_today", "prescription": "prescriptions", "referral": "referral",
    "next_visit": "next_visit", "instruction": "instructions",
}

TEAM_OWNER_BY_TYPE = {
    "history_change": "B1", "medication": "B1", "allergy": "B1", "vital_reading": "B1",
    "symptom": "B2",
    "finding": "B3", "perio_measurement": "B3", "radiograph": "B3",
}
for _t in ("diagnosis", "option_discussed", "decision", "consent_element", "treatment_today", "prescription",
           "referral", "next_visit", "instruction"):
    TEAM_OWNER_BY_TYPE[_t] = "B4"


def is_critical(entity) -> bool:
    """Critical types (section 9.2 footnote): tooth targets count, so any item with a tooth is critical."""
    if entity.kind == "problem":
        return True
    if entity.kind == "relationship":
        return True
    return entity.type in CRITICAL_TYPES or entity.target.tooth is not None
