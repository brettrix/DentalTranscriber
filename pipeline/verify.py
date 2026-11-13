"""Cv: Evidence & Normalization Verifier (sections 7.1-7.2), and the append-only check log (7.4)."""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

import glossary
from pipeline import normalize
from pipeline.storage import append_jsonl, hash_obj, now, read_jsonl
from schemas.entities import compare_table, get_path

CV_VERSION = "cv-1"
CV_CONFIG_HASH = hash_obj({"version": CV_VERSION, "drugs": glossary.DRUG_NAMES,
                           "teeth": glossary.SPOKEN_TOOTH_NUMBERS})[:16]

NEGATION_CUES = re.compile(r"\b(no|not|never|none|nothing|nope|denies|denied|without|negative|don't|doesn't|didn't|"
                           r"isn't|wasn't|haven't|hasn't|can't|n't|neither|nor)\b", re.I)

# Attributes that may also be derived by a second rule (BP parts read one number at a time).
ALT_RULES = {"bp_reading": {"spoken_number"}, "spoken_tooth_number": set(), "dose": set()}


# ---------------------------------------------------------------- the check log

@dataclass
class CheckLog:
    path: Path | None = None
    records: list[dict] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        if self.path is not None:
            self.records = read_jsonl(self.path)

    def record(self, entity, check: str, result: str, details, config_hash: str, attempt: int = 1,
               run_id: str | None = None) -> dict:
        rec = {"id": f"cr_{len(self.records) + 1}_{hash_obj([entity.ref, check, now()])[:6]}",
               "entity_id": entity.id, "entity_version": entity.version, "content_hash": entity.content_hash,
               "support_hash": entity.support_hash, "check": check, "check_config_hash": config_hash,
               "attempt": attempt, "result": result, "details": details, "timestamp": now(), "run_id": run_id}
        with self._lock:
            self.records.append(rec)
            if self.path is not None:
                append_jsonl(self.path, rec)
        return rec

    def latest(self, entity, check: str, config_hash: str | None = None) -> dict | None:
        """Latest execution bound to the entity's current hashes (and config, when given)."""
        for rec in reversed(self.records):
            if (rec["entity_id"] == entity.id and rec["check"] == check
                    and rec["content_hash"] == entity.content_hash and rec["support_hash"] == entity.support_hash
                    and (config_hash is None or rec["check_config_hash"] == config_hash)):
                return rec
        return None

    def history(self, entity_id: str) -> list[dict]:
        return [r for r in self.records if r["entity_id"] == entity_id]


def session_check_log(session) -> CheckLog:
    return CheckLog(path=session.path("check_runs.jsonl"))


# ---------------------------------------------------------------- span locating (Linker helper)

def locate_span(span, sources) -> None:
    """Fill offsets for an agent quote. Exact match first; otherwise rapidfuzz finds the nearest candidate,
    whose offsets are recorded while span.text keeps the agent's quote, so Cv's exact check then fails."""
    if span.source_type not in ("transcript", "quick_note"):
        return
    text = sources.source_text(span.source_type, span.source_id)
    if text is None or not span.text:
        return
    idx = text.find(span.text)
    if idx >= 0:
        span.start, span.end = idx, idx + len(span.text)
        return
    lowered = text.lower().find(span.text.lower())
    if lowered >= 0:
        span.start, span.end = lowered, lowered + len(span.text)
        return
    al = fuzz.partial_ratio_alignment(span.text, text)
    if al is not None and al.score >= 60:
        span.start, span.end = al.dest_start, al.dest_end


# ---------------------------------------------------------------- span validity

def check_spans(entity, sources) -> tuple[str, list[str]]:
    if entity.is_human:
        return "not_applicable", ["human entry"]
    problems: list[str] = []
    checked = 0
    for i, s in enumerate(entity.evidence):
        if s.source_type == "visit_meta":
            continue
        if s.source_type == "human_entry":
            problems.append(f"evidence[{i}] is human_entry on a source-backed entity")
            continue
        checked += 1
        text = sources.source_text(s.source_type, s.source_id)
        if text is None:
            problems.append(f"evidence[{i}]: source {s.source_id} not found")
            continue
        expected_version = sources.utterances.version if s.source_type == "transcript" else sources.quick_notes.version
        if s.source_version != expected_version:
            problems.append(f"evidence[{i}]: source version {s.source_version} != {expected_version}")
        if s.start is None or s.end is None:
            problems.append(f"evidence[{i}]: quote not found in {s.source_id}")
            continue
        if text[s.start:s.end] != s.text:
            problems.append(f"evidence[{i}]: quote {s.text!r} does not match {s.source_id}[{s.start}:{s.end}] = "
                            f"{text[s.start:s.end]!r}")
    if checked == 0 and not problems:
        return "not_applicable", ["visit metadata only"]
    return ("fail", problems) if problems else ("pass", [])


# ---------------------------------------------------------------- normalization validity

def required_rule_attributes(entity) -> dict[str, str]:
    """Attribute path -> deterministic rule, for non-null attributes that need a derivation."""
    table = compare_table(entity.kind, getattr(entity, "type", None))
    out = {}
    for path, meta in table.items():
        rule = meta.get("rule")
        if rule and get_path(entity, path) is not None:
            out[path] = rule
    return out


def _expected_component(rule: str, path: str, value):
    if rule == "bp_reading" and isinstance(value, str) and "/" in value:
        sys_, dia = value.split("/")
        return int(sys_) if path.endswith("systolic") else int(dia)
    return value


def check_normalization(entity, sources) -> tuple[str, list[str]]:
    if entity.is_human:
        return "not_applicable", ["human entry"]
    problems: list[str] = []
    required = required_rule_attributes(entity)
    derived: dict[str, set[str]] = {}
    for k, d in enumerate(entity.derivations):
        if not 0 <= d.evidence_index < len(entity.evidence):
            problems.append(f"derivation[{k}] {d.attribute}: evidence_index {d.evidence_index} out of range")
            continue
        span = entity.evidence[d.evidence_index]
        if span.source_type not in ("visit_meta",) and d.from_.lower() not in span.text.lower():
            problems.append(f"derivation[{k}] {d.attribute}: {d.from_!r} not in evidence[{d.evidence_index}]")
            continue
        if d.rule == "negation":
            problems += _check_negation(entity, d, k, sources)
            continue
        if d.rule == "semantic":
            continue
        if d.rule not in normalize.DETERMINISTIC_RULES:
            problems.append(f"derivation[{k}] {d.attribute}: unknown rule {d.rule!r}")
            continue
        try:
            recomputed = _expected_component(d.rule, d.attribute, normalize.apply(d.rule, d.from_))
        except normalize.NormalizationError as exc:
            problems.append(f"derivation[{k}] {d.attribute}: rule {d.rule} cannot read {d.from_!r} ({exc})")
            continue
        if not normalize.values_equal(recomputed, d.to):
            problems.append(f"derivation[{k}] {d.attribute}: {d.rule}({d.from_!r}) = {recomputed!r}, not {d.to!r}")
            continue
        actual = get_path(entity, d.attribute)
        if not normalize.values_equal(actual, d.to):
            problems.append(f"derivation[{k}] {d.attribute}: entity value {actual!r} != derived {d.to!r}")
            continue
        derived.setdefault(d.attribute, set()).add(d.rule)
    for path, rule in required.items():
        ok_rules = {rule} | ALT_RULES.get(rule, set())
        if not derived.get(path, set()) & ok_rules:
            problems.append(f"{path} = {get_path(entity, path)!r} has no valid {rule} derivation")
    if entity.kind == "item" and entity.assertion in ("absent", "denied"):
        if not any(d.rule == "negation" for d in entity.derivations):
            problems.append(f"assertion {entity.assertion} needs a negation derivation citing the cue and concept")
    if not required and not entity.derivations and not problems:
        return "not_applicable", []
    return ("fail", problems) if problems else ("pass", [])


def _check_negation(entity, d, k, sources) -> list[str]:
    """Cue and concept must appear in the same span. A clinician question and the patient's direct answer
    (adjacent utterances, both cited) count as one span for this purpose (DECISIONS.md)."""
    out = []
    cue_span = entity.evidence[d.evidence_index]
    if not NEGATION_CUES.search(d.from_):
        out.append(f"derivation[{k}]: {d.from_!r} is not a negation cue")
    if not d.concept:
        return out + [f"derivation[{k}]: negation derivation names no concept"]
    ci = d.evidence_index if d.concept_evidence_index is None else d.concept_evidence_index
    if not 0 <= ci < len(entity.evidence):
        return out + [f"derivation[{k}]: concept_evidence_index out of range"]
    concept_span = entity.evidence[ci]
    if d.concept.lower() not in concept_span.text.lower():
        out.append(f"derivation[{k}]: concept {d.concept!r} not in evidence[{ci}]")
    if ci != d.evidence_index:
        adjacent = (cue_span.source_type == concept_span.source_type == "transcript"
                    and sources.utterance_index(cue_span.source_id) - sources.utterance_index(concept_span.source_id) == 1
                    and concept_span.text.rstrip().endswith("?"))
        if not adjacent:
            out.append(f"derivation[{k}]: negation cue and concept are in different spans that are not a direct "
                       f"question and answer")
    return out


def run_cv(entities, sources, log: CheckLog, attempt: int = 1, run_id: str | None = None) -> dict[str, dict]:
    """Run span and normalization checks on each entity; append executions; return {entity ref: results}."""
    out = {}
    for e in entities:
        sres, sdet = check_spans(e, sources)
        nres, ndet = check_normalization(e, sources)
        log.record(e, "span_valid", sres, sdet, CV_CONFIG_HASH, attempt, run_id)
        log.record(e, "normalization_valid", nres, ndet, CV_CONFIG_HASH, attempt, run_id)
        out[e.ref] = {"span_valid": (sres, sdet), "normalization_valid": (nres, ndet)}
    return out
