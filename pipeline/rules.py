"""E2 rule engine (Python, section 9.2). Reads the frozen graph; never edits it."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

import glossary
from pipeline.dispositions import accepted, satisfying_disposition, section_reviewed
from pipeline.flags import make_flag
from pipeline.normalize import NormalizationError, drug_name, spoken_tooth_number
from pipeline.storage import ROOT, sha256_text
from schemas.entities import TREATMENT_BEARING, is_critical

RULES_DIR = ROOT / "rules"
RULE_FILES = ["config.json", "drug_allergy.json", "clinical_review_rules.yaml"]
CLINICAL_CONTENT_RULES = {"bp_reading", "allergy_rx", "refusal_discussion"}
PRECAUTION = "Depends on unconfirmed information."
PENDING_LABEL = "Rule pending dentist confirmation."


@lru_cache(maxsize=1)
def rule_config() -> dict:
    return json.loads((RULES_DIR / "config.json").read_text("utf-8"))


@lru_cache(maxsize=1)
def drug_allergy() -> dict:
    return json.loads((RULES_DIR / "drug_allergy.json").read_text("utf-8"))


def rule_file_hashes() -> dict[str, str]:
    return {name: sha256_text((RULES_DIR / name).read_bytes()) for name in RULE_FILES}


def rule_hash(rule_id: str) -> str:
    return sha256_text(json.dumps(rule_config()["rules"][rule_id], sort_keys=True))[:16]


def rule_active(rule_id: str, rule_mode: str) -> bool:
    cfg = rule_config()["rules"][rule_id]
    if cfg["class"] == "technical":
        return True
    return rule_mode == "synthetic_demo" or cfg.get("status") == "approved"


@dataclass
class RuleContext:
    graph: object
    mode: str
    rule_mode: str
    sources: object
    stage_runs: list[dict] = field(default_factory=list)
    staging_open: list = field(default_factory=list)
    pending_corrections: list = field(default_factory=list)


class Engine:
    def __init__(self, ctx: RuleContext):
        self.ctx = ctx
        self.g = ctx.graph
        self.flags = []
        self.notices: list[str] = []

    # ---- helpers
    def acc(self, e) -> bool:
        return accepted(self.g, e, self.ctx.mode)

    def emit(self, rule_id: str, severity: str, message: str, entities=(), *, precautionary=None, **kw):
        cfg = rule_config()["rules"][rule_id]
        ents = list(entities)
        if precautionary is None:
            precautionary = any(not self.acc(e) for e in ents)
        if precautionary and PRECAUTION not in message:
            message = f"{message} {PRECAUTION}"
        if cfg["class"] == "clinical" and cfg.get("status") == "pending":
            message = f"{message} ({PENDING_LABEL})"
        self.flags.append(make_flag(rule_id, cfg, severity=severity, message=message, graph=self.g, entities=ents,
                                    precautionary=precautionary, rule_hash=rule_hash(rule_id), **kw))

    def items(self, *types):
        return self.g.active_items(*types)

    def run(self):
        for rule_id in rule_config()["rules"]:
            if not rule_active(rule_id, self.ctx.rule_mode):
                msg = rule_config()["rules"][rule_id].get("inactive_message", f"{rule_id} not active")
                self.notices.append(msg)
                continue
            fn = getattr(self, f"r_{rule_id}", None)
            if fn is not None:
                fn()
        return self.flags

    # ---- target rules
    def _tb_tooth(self, item):
        if item.type == "decision":
            opt = self.g.get(item.attributes.get("option_id")) if item.attributes.get("option_id") else None
            return opt.target.tooth if opt is not None else None
        return item.target.tooth

    def _treatment_bearing(self, problem_id=None):
        out = []
        for i in self.items():
            if i.scope != "problem" or (problem_id and i.problem_id != problem_id):
                continue
            if i.type in TREATMENT_BEARING or i.type == "prescription":
                out.append(i)
        return out

    def r_treatment_target_mismatch(self):
        for i in self._treatment_bearing():
            tooth = self._tb_tooth(i)
            p = self.g.get(i.problem_id)
            if tooth is None or p is None:
                continue
            target = p.clinical_target.tooth
            marked = next((r for r in self.g.active("relationship") if r.problem_id == p.id and r.tooth == tooth
                           and r.relation_kind in ("control", "adjacent_examined", "referred_from")), None)
            if target is None and marked is not None:
                # The record itself says this tooth is not the problem tooth; a relationship never explains
                # treatment (6.2), so this is a mismatch even without an identified clinical target.
                self.emit("treatment_target_mismatch", "high",
                          f"{i.type.replace('_', ' ')} names #{tooth}, which is recorded as a "
                          f"{marked.relation_kind.replace('_', ' ')} tooth; no clinical target was identified.",
                          [i, p, marked], target=tooth, problem_id=p.id)
            elif target is None:
                self.emit("target_not_assessable", "low",
                          f"{i.type} names #{tooth} but problem {p.id} has no clinical target to compare.", [i, p],
                          target=tooth, problem_id=p.id)
            elif tooth != target:
                self.emit("treatment_target_mismatch", "high",
                          f"{i.type.replace('_', ' ')} names #{tooth}, but the problem's clinical target is #{target}.",
                          [i, p], target=tooth, problem_id=p.id)

    def r_treatment_target_disagreement(self):
        for p in self.g.active("problem"):
            tb = [(i, self._tb_tooth(i)) for i in self._treatment_bearing(p.id)]
            teeth = {t for _, t in tb if t is not None}
            if len(teeth) > 1:
                ents = [i for i, t in tb if t is not None]
                self.emit("treatment_target_disagreement", "high",
                          "Treatment-bearing items for one problem name different teeth: " +
                          ", ".join(f"{i.type.replace('_', ' ')} #{t}" for i, t in tb if t is not None) + ".",
                          ents, problem_id=p.id)

    def r_unexplained_other_tooth(self):
        for i in self.items("finding", "radiograph", "perio_measurement"):
            if i.scope == "problem" and i.target.tooth is not None and i.target_relation == "unknown":
                p = self.g.get(i.problem_id)
                self.emit("unexplained_other_tooth", "low",
                          f"{i.type.replace('_', ' ')} on #{i.target.tooth} for a problem targeting "
                          f"#{p.clinical_target.tooth if p else '?'}: how does this tooth relate?", [i],
                          precautionary=False, target=i.target.tooth, problem_id=i.problem_id)

    def _quadrant_of_text(self, text: str | None):
        if not text:
            return None
        t = text.lower()
        for phrase, quad in glossary.QUADRANT_PHRASES.items():
            if phrase in t:
                return quad
        return None

    def _location(self, loc):
        """(tooth, quadrant) for a complaint location or clinical target."""
        if loc.tooth is not None:
            return loc.tooth, glossary.tooth_quadrant(loc.tooth)
        return None, self._quadrant_of_text(loc.free_text)

    def _explained_by_referral(self, p, tooth, quad):
        for r in self.g.active("relationship"):
            if r.problem_id == p.id and r.relation_kind == "referred_from" and \
                    (r.tooth == tooth or (tooth is None and quad and glossary.tooth_quadrant(r.tooth) == quad)):
                from pipeline.dispositions import relationship_eligible
                if relationship_eligible(self.g, r, self.ctx.mode):
                    return True
        return False

    def r_complaint_location_differs(self):
        for p in self.g.active("problem"):
            target = p.clinical_target.tooth
            if target is None:
                continue
            tooth, quad = self._location(p.complaint_location)
            if tooth is None and quad is None:
                if p.complaint_location.free_text:
                    self.emit("target_not_assessable", "low",
                              f"Complaint location {p.complaint_location.free_text!r} can't be compared with #{target}.",
                              [p], problem_id=p.id)
                continue
            differs = (tooth != target) if tooth is not None else (quad != glossary.tooth_quadrant(target))
            if differs and not self._explained_by_referral(p, tooth, quad):
                where = f"#{tooth}" if tooth is not None else (p.complaint_location.free_text or quad)
                self.emit("complaint_location_differs", "low",
                          f"Patient-reported location ({where}) differs from the clinical target #{target}.", [p],
                          precautionary=False, problem_id=p.id, target=target)

    # ---- quick-note target rules
    def _quick_note_teeth(self):
        """(note, label kind or None, tooth or None, quadrant or None) per quick-note line with a location."""
        out = []
        for q in self.ctx.sources.quick_notes.notes:
            text = q.text.strip()
            label = None
            for prefix, kind in glossary.QUICK_NOTE_LABELS.items():
                if text.lower().startswith(prefix.lower()):
                    label = kind
                    text = text[len(prefix):]
                    break
            teeth = []
            for m in re.finditer(r"(#\s?\d{1,2}|\btooth\s+\d{1,2}|\bnumber\s+[a-z\-]+)", text, re.I):
                try:
                    teeth.append(spoken_tooth_number(m.group(0)))
                except NormalizationError:
                    pass
            quad = self._quadrant_of_text(text)
            if teeth or (label == "complaint_location" and quad):
                out.append((q, label, teeth, quad))
        return out

    def _qn_span(self, q):
        from schemas.entities import Span
        return [Span(source_type="quick_note", source_id=q.id, source_version=self.ctx.sources.quick_notes.version,
                     start=0, end=len(q.text), text=q.text)]

    def r_quick_note_target_conflict(self):
        problems = self.g.active("problem")
        for q, label, teeth, _ in self._quick_note_teeth():
            if label != "clinical_target":
                continue
            for tooth in teeth:
                if not any(p.clinical_target.tooth == tooth for p in problems):
                    chief = self.g.chief()
                    self.emit("quick_note_target_conflict", "high",
                              f"Quick note {q.id} ({q.text!r}) names #{tooth}, but the clinical target is "
                              f"#{chief.clinical_target.tooth if chief else '?'}.", [chief] if chief else [],
                              evidence=self._qn_span(q), target=tooth, precautionary=False)

    def r_quick_note_complaint_mismatch(self):
        chief = self.g.chief()
        if chief is None:
            return
        ctooth, cquad = self._location(chief.complaint_location)
        for q, label, teeth, quad in self._quick_note_teeth():
            if label != "complaint_location":
                continue
            qtooth = teeth[0] if teeth else None
            qquad = glossary.tooth_quadrant(qtooth) if qtooth else quad
            if (ctooth is None and cquad is None) or (qtooth is None and qquad is None):
                continue
            differs = (qtooth != ctooth) if (qtooth is not None and ctooth is not None) else (qquad != cquad)
            if differs:
                self.emit("quick_note_complaint_mismatch", "low",
                          f"Quick note {q.id} complaint location ({q.text!r}) differs from the patient-reported "
                          f"location ({chief.complaint_location.free_text or ctooth}).", [chief],
                          evidence=self._qn_span(q), precautionary=False)

    def r_quick_note_tooth_unclear(self):
        problems = self.g.active("problem")
        for q, label, teeth, _ in self._quick_note_teeth():
            if label is not None:
                continue
            for tooth in teeth:
                matched = False
                for p in problems:
                    ctooth, cquad = self._location(p.complaint_location)
                    if p.clinical_target.tooth == tooth or ctooth == tooth or \
                            (ctooth is None and cquad and glossary.tooth_quadrant(tooth) == cquad):
                        matched = True
                if not matched:
                    self.emit("quick_note_tooth_unclear", "medium",
                              f"Quick note {q.id} mentions #{tooth}, which matches neither the complaint location "
                              f"nor the clinical target.", [], evidence=self._qn_span(q), target=tooth,
                              precautionary=False)

    # ---- clinical-content rules
    def _allergen_members(self, substance: str | None):
        if not substance:
            return None
        da = drug_allergy()
        s = substance.lower().strip()
        s = da["allergen_aliases"].get(s, s)
        if s in da["allergen_groups"]:
            return set(da["allergen_groups"][s]) | {s}
        try:
            generic = drug_name(s)
        except NormalizationError:
            return None
        members = set(glossary_ingredients(generic))
        for group, drugs in da["allergen_groups"].items():
            if generic in drugs or group == generic:
                members |= set(drugs) if generic == group else set()
        return members

    def r_allergy_rx(self):
        allergies = [a for a in self.items("allergy") if a.attributes.get("allergy_status") != "denied"
                     and a.assertion not in ("denied", "absent")]
        for rx in self.items("prescription"):
            status = rx.attributes.get("prescription_status")
            if status not in ("prescribed_today", "discussed_not_prescribed"):
                continue
            drug = rx.attributes.get("drug")
            ingr = set(glossary_ingredients(drug)) if drug else None
            for a in allergies:
                members = self._allergen_members(a.attributes.get("substance") or a.attributes.get("original_wording"))
                astatus = a.attributes.get("allergy_status")
                label = a.attributes.get("substance") or a.attributes.get("original_wording") or "unspecified"
                if ingr is None or members is None:
                    self.emit("allergy_rx", "medium",
                              f"Allergy ({label}) and prescription ({drug or rx.attributes.get('original_wording')}) "
                              f"could not be compared (drug or substance not recognized).", [rx, a])
                    continue
                if not (ingr & members):
                    continue
                if status == "discussed_not_prescribed":
                    self.emit("allergy_rx", "medium", f"{drug} was discussed (not prescribed); allergy to {label} "
                                                      f"({astatus}).", [rx, a], safety_critical=False)
                elif astatus == "reported_resolved":
                    self.emit("allergy_rx", "medium", f"{drug} prescribed; allergy to {label} reported resolved; "
                                                      f"confirm.", [rx, a], safety_critical=False)
                else:
                    self.emit("allergy_rx", "high", f"{drug} prescribed today; allergy to {label} is "
                                                    f"{(astatus or 'unknown status').replace('_', ' ')}.", [rx, a],
                              safety_critical=True)
        if not self.flags or all(f.rule_id != "allergy_rx" for f in self.flags):
            self.notices.append("Allergy/prescription check: checked against a limited list, not a safety clearance.")

    def r_bp_reading(self):
        cfg = rule_config()["rules"]["bp_reading"]
        readings = sorted(self.items("vital_reading"), key=lambda v: (v.attributes.get("sequence") or 0, v.id))
        if not readings:
            self.emit("bp_reading", "low", "No blood pressure reading is documented.", [], precautionary=False)
            return
        level = 0
        for v in readings:
            s, d = v.attributes.get("systolic") or 0, v.attributes.get("diastolic") or 0
            if s >= cfg["level_b"]["systolic"] or d >= cfg["level_b"]["diastolic"]:
                level = max(level, 2)
            elif s >= cfg["level_a"]["systolic"] or d >= cfg["level_a"]["diastolic"]:
                level = max(level, 1)
        if level:
            listing = "; ".join(f"{v.attributes.get('label') or 'reading'} {v.attributes.get('systolic')}/"
                                f"{v.attributes.get('diastolic')} mmHg" for v in readings)
            self.emit("bp_reading", "high" if level == 2 else "medium",
                      f"Blood pressure at level {'B' if level == 2 else 'A'}: {listing}.", readings,
                      safety_critical=level == 2)

    def r_refusal_discussion(self):
        for d in self.items("decision"):
            if d.attributes.get("decision") not in ("declined", "deferred"):
                continue
            opt = self.g.get(d.attributes.get("option_id")) if d.attributes.get("option_id") else None
            if opt is None:
                continue
            rec = opt.attributes.get("recommended_by_clinician")
            if rec is None:
                self.emit("refusal_discussion", "low", "Declined/deferred option: was it recommended by the dentist?",
                          [d, opt], precautionary=False)
                continue
            if rec is not True:
                continue
            documented = [c for c in self.items("consent_element")
                          if c.attributes.get("element") == "consequences_of_refusal_discussed"
                          and (c.attributes.get("option_id") == opt.id or c.attributes.get("decision_id") == d.id)
                          and self.acc(c)]
            if not documented:
                unconfirmed = [c for c in self.items("consent_element")
                               if c.attributes.get("element") == "consequences_of_refusal_discussed"
                               and (c.attributes.get("option_id") == opt.id or c.attributes.get("decision_id") == d.id)]
                msg = ("Recommended option was declined/deferred and the consequences of refusal are not documented."
                       if not unconfirmed else
                       "Consequences of refusal present but not confirmed.")
                self.emit("refusal_discussion", "low", msg, [d, opt] + unconfirmed, precautionary=False)

    # ---- documentation rules (only accepted entities satisfy them)
    def r_chief_problem_minimum(self):
        chief = self.g.chief()
        if chief is None:
            return
        findings = [f for f in self.items("finding") if f.problem_id == chief.id and self.acc(f)]
        if chief.clinical_target.tooth is None and chief.clinical_target.free_text is None and not findings:
            self.emit("chief_problem_minimum", "medium", "Chief problem has no clinical target and no confirmed finding.",
                      [chief], precautionary=False)

    def r_diagnosis_or_plan_missing(self):
        chief = self.g.chief()
        if chief is None:
            return
        on = [i for i in self.items() if i.problem_id == chief.id and self.acc(i)]
        has_dx = any(i.type == "diagnosis" for i in on)
        has_decision = any(i.type == "decision" for i in on)
        workup = any((i.type == "radiograph" and i.attributes.get("action") == "planned") or i.type == "referral" or
                     (i.type == "decision" and i.attributes.get("decision") == "monitor") or
                     (i.type == "next_visit") for i in on)
        if not has_dx and not has_decision and not workup:
            present = [i for i in self.items("diagnosis", "decision") if i.problem_id == chief.id]
            msg = "No diagnosis or decision is documented for the chief problem." if not present else \
                "Diagnosis or decision present but not confirmed."
            self.emit("diagnosis_or_plan_missing", "low", msg, [chief] + present, precautionary=False)

    def r_radiograph_finding_missing(self):
        for x in self.items("radiograph"):
            if x.attributes.get("action") != "performed":
                continue
            if not x.attributes.get("finding"):
                self.emit("radiograph_finding_missing", "medium", "Radiograph performed with no finding documented.",
                          [x], precautionary=False)
            elif not self.acc(x):
                self.emit("radiograph_finding_missing", "medium", "Radiograph finding present but not confirmed.",
                          [x], precautionary=False)

    # ---- technical safeguards
    def r_unsupported_content(self):
        for e in self.g.active():
            c = e.checks
            bad = [k for k, v in (("span", c.span_valid), ("normalization", c.normalization_valid),
                                  ("meaning", c.semantic_support)) if v in ("fail", "not_assessed_due_to_failure")]
            if bad and satisfying_disposition(self.g, e) is None:
                self.emit("unsupported_content", "high" if is_critical(e) else "medium",
                          f"{_label(e)}: {', '.join(bad)} check {'/'.join(sorted({getattr(c, _f(k)) for k in bad}))}.",
                          [e], precautionary=False)

    def r_incomplete_section(self):
        for s in self.g.section_records:
            if s.status in ("failed", "not_run") and section_reviewed(self.g, s.section) is None:
                self.emit("incomplete_section", "high", f"Section {s.section} {s.status.replace('_', ' ')} "
                                                        f"({s.owner}). Review the transcript.", [], precautionary=False)

    def r_stage_failure(self):
        for run in self.ctx.stage_runs:
            if run["status"] != "failed":
                continue
            task = next((t for t in self.g.tasks if t.stage_run_id == run["id"]), None)
            if task is not None and task.status == "completed":
                continue
            sev = "high" if run["agent"] in ("Br", "B0", "B1", "B2", "B3", "B4", "Linker", "Cs", "Ce") else "medium"
            self.emit("stage_failure", sev, f"Stage {run['stage']} {run['agent']} failed: {run.get('error')}", [],
                      task_ids=[task.id] if task else [], precautionary=False)

    def r_open_conflict(self):
        for c in self.g.conflicts:
            open_for_dentist = c.status == "open" or (c.resolution and c.resolution.pending_change_id)
            if not open_for_dentist:
                continue
            ents = [self.g.get(p.entity_id, p.version) for p in c.participants]
            ents = [e for e in ents if e is not None]
            sev = "high" if any(is_critical(e) for e in ents) else "medium"
            self.emit("open_conflict", sev, f"{c.kind.replace('_', ' ')} about {c.subject or 'the same subject'} is "
                                            f"open.", ents, conflict_ids=[c.id], evidence=c.evidence,
                      precautionary=False, safety_critical=False)
        for t in self.g.tasks:
            if t.kind == "unmatched_contradiction" and t.status == "open":
                self.emit("open_conflict", "high", f"Unmatched contradiction: {t.reason}", [], task_ids=[t.id],
                          evidence=t.evidence, precautionary=False)

    def r_open_review_task(self):
        for t in self.g.tasks:
            if t.status == "open" and t.kind not in ("unmatched_contradiction", "stage_failure", "unknown_option_link"):
                self.emit("open_review_task", "medium", f"Open review task ({t.kind}): {t.reason}", [],
                          task_ids=[t.id], evidence=t.evidence, precautionary=False)

    def r_unknown_option_link(self):
        for d in self.items("decision"):
            if d.attributes.get("option_link") == "unknown":
                self.emit("unknown_option_link", "low", "Decision is not linked to a discussed option.", [d],
                          precautionary=False)

    def r_pending_critical_correction(self):
        for c in self.ctx.pending_corrections:
            self.emit("pending_critical_correction", "high", f"Critical correction pending: {c}", [],
                      precautionary=False)


def _f(k):
    return {"span": "span_valid", "normalization": "normalization_valid", "meaning": "semantic_support"}[k]


def _label(e) -> str:
    if e.kind == "item":
        return f"{e.type.replace('_', ' ')} {e.id}"
    return f"{e.kind} {e.id}"


def glossary_ingredients(generic: str) -> list[str]:
    return glossary.ingredients(generic)


def run_rules(ctx: RuleContext):
    eng = Engine(ctx)
    flags = eng.run()
    return flags, eng.notices
