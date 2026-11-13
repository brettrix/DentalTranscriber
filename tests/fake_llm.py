"""A fake Anthropic client for offline pipeline tests. Routes each call by tool name and agent prompt header."""
from __future__ import annotations

import copy
import re
from types import SimpleNamespace

import anthropic
import httpx2

MINI_TRANSCRIPT = """DENTIST: What brings you in today?
PATIENT: My upper left tooth hurts with cold.
DENTIST: Any allergies to medications?
PATIENT: Penicillin gives me hives.
DENTIST: Cold on number fourteen.
PATIENT: Yes, that's sharp.
DENTIST: This is reversible pulpitis on fourteen.
DENTIST: I'll prescribe ibuprofen 600 milligrams every six hours as needed.
DENTIST: We'll do a filling on fourteen next week.
DENTIST: Blood pressure is 150 over 95.
"""
MINI_QUICK_NOTES = "BP 124/80\n"


def q(uid, text, st="transcript"):
    return {"source_type": st, "source_id": uid, "quote": text}


def d(attr, rule, frm, to, i=0):
    return {"attribute": attr, "rule": rule, "from": frm, "to": to, "evidence_index": i}


PROBLEM = {"key": "P1", "role": "chief", "complaint_text": "upper left tooth hurts with cold",
           "complaint_location": {"free_text": "upper left", "tooth": None},
           "clinical_target": {"tooth": 14, "free_text": None}, "assertion_source": "clinician_assessment",
           "evidence": [q("u2", "My upper left tooth hurts with cold."), q("u5", "Cold on number fourteen.")],
           "derivations": [d("clinical_target.tooth", "spoken_tooth_number", "number fourteen", 14, 1)]}

ITEMS = {
    "A1": {"key": "A1", "type": "allergy", "attributes": {"substance": "penicillin", "reaction": "hives",
                                                          "allergy_status": "reported_active"},
           "assertion_source": "patient_report", "evidence": [q("u4", "Penicillin gives me hives.")],
           "derivations": [d("attributes.substance", "drug_name", "Penicillin", "penicillin")]},
    "V1": {"key": "V1", "type": "vital_reading", "attributes": {"systolic": 124, "diastolic": 80, "sequence": 1},
           "assertion_source": "assistant_record", "evidence": [q("q1", "BP 124/80", "quick_note")],
           "derivations": [d("attributes.systolic", "bp_reading", "124/80", 124),
                           d("attributes.diastolic", "bp_reading", "124/80", 80)]},
    "S1": {"key": "S1", "type": "symptom", "problem_key": "P1", "attributes": {"aspect": "trigger", "value": "cold"},
           "assertion_source": "patient_report", "evidence": [q("u2", "My upper left tooth hurts with cold.")]},
    "F1": {"key": "F1", "type": "finding", "problem_key": "P1", "target": {"tooth": 14},
           "attributes": {"test": "cold", "response": "present", "intensity": "sharp"},
           "assertion_source": "test_response",
           "evidence": [q("u5", "Cold on number fourteen."), q("u6", "Yes, that's sharp.")],
           "derivations": [d("target.tooth", "spoken_tooth_number", "number fourteen", 14)]},
    "D1": {"key": "D1", "type": "diagnosis", "problem_key": "P1", "target": {"tooth": 14},
           "attributes": {"diagnosis": "reversible pulpitis", "certainty": "definite"},
           "assertion_source": "clinician_assessment",
           "evidence": [q("u7", "This is reversible pulpitis on fourteen.")],
           "derivations": [d("target.tooth", "spoken_tooth_number", "fourteen", 14)]},
    "RX1": {"key": "RX1", "type": "prescription",
            "attributes": {"drug": "ibuprofen", "strength": "600 mg", "frequency_code": "q6h PRN", "as_needed": True,
                           "prescription_status": "prescribed_today"},
            "assertion_source": "clinician_instruction",
            "evidence": [q("u8", "I'll prescribe ibuprofen 600 milligrams every six hours as needed.")],
            "derivations": [d("attributes.drug", "drug_name", "ibuprofen", "ibuprofen"),
                            d("attributes.strength", "dose", "600 milligrams", "600 mg"),
                            d("attributes.frequency_code", "frequency", "every six hours as needed", "q6h PRN")]},
    "N1": {"key": "N1", "type": "next_visit", "problem_key": "P1", "target": {"tooth": 14},
           "attributes": {"procedure": "filling", "timing": "next week"}, "time_context": "planned",
           "assertion_source": "clinician_instruction",
           "evidence": [q("u9", "We'll do a filling on fourteen next week.")],
           "derivations": [d("target.tooth", "spoken_tooth_number", "fourteen", 14)]},
}
TEAM_ITEMS = {"B1": ["A1", "V1"], "B2": ["S1"], "B3": ["F1"], "B4": ["D1", "RX1", "N1"]}

AGENT_HEADERS = {"# B0 Extraction Agent": "B0", "# Br Problem Registry Agent": "Br", "# B1 Medical": "B1",
                 "# B2 Complaint": "B2", "# B3 Findings": "B3", "# B4 Assessment": "B4"}


def _agent_of(system: str) -> str:
    for header, name in AGENT_HEADERS.items():
        if header in system:
            return name
    return "?"


def _path(obj, path):
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


DEFAULTS = {"assertion": "present", "time_context": "current"}


class FakeLLM:
    """Configurable fake. `items`/`problem` are what extractors return; `fail` maps agent -> exception or 'invalid';
    `cs_override` maps a focus quote to {path: value} the checker reads differently."""

    def __init__(self, *, items=None, problem=None, fail=None, cs_override=None, co_omissions=None, r2=None,
                 repair=None, ce_verdict="equivalent"):
        self.repair = repair
        self.ce_verdict = ce_verdict
        self.items = copy.deepcopy(items or ITEMS)
        self.problem = copy.deepcopy(problem or PROBLEM)
        self.fail = dict(fail or {})
        self.cs_override = cs_override or {}
        self.co_omissions = co_omissions or []
        self.r2 = r2 or []
        self.calls: list[str] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def with_options(self, **_):
        return self

    # ---- routing
    def create(self, **kw):
        tool = kw["tools"][0]["name"]
        system = kw["system"]
        agent = {"submit_extraction": _agent_of(system), "submit_repair": "repair:" + _agent_of(system),
                 "submit_contradictions": "R2", "submit_window_extractions": "Cs", "submit_verdicts": "Ce",
                 "submit_omissions": "Co", "submit_questions": "E3", "submit_grades": "Grader",
                 "submit_claim_grades": "Grader"}[tool]
        self.calls.append(agent)
        failure = self.fail.get(agent)
        if isinstance(failure, Exception):
            raise failure
        if failure == "invalid" or (failure == "invalid_once" and self.calls.count(agent) == 1
                                    and len(kw["messages"]) == 1):
            return self._tool_response(tool, {"nonsense": True})
        user = kw["messages"][0]["content"]
        return self._tool_response(tool, getattr(self, "_" + tool)(agent, user))

    @staticmethod
    def _tool_response(tool, data):
        block = SimpleNamespace(type="tool_use", id="toolu_fake", name=tool, input=data,
                                model_dump=lambda **_: {"type": "tool_use", "id": "toolu_fake", "name": tool,
                                                        "input": data})
        return SimpleNamespace(content=[block], stop_reason="tool_use", model="fake-model",
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))

    # ---- handlers
    def _submit_extraction(self, agent, user):
        if agent == "B0":
            return {"problems": [self.problem], "relationships": [], "items": list(self.items.values())}
        if agent == "Br":
            return {"problems": [self.problem], "relationships": []}
        keys = re.findall(r"- problem_key (\S+?):", user)
        out = [copy.deepcopy(self.items[k]) for k in TEAM_ITEMS.get(agent, []) if k in self.items]
        for it in out:
            if it.get("problem_key") and keys:
                it["problem_key"] = keys[0]
        return {"items": out}

    def _submit_repair(self, agent, user):
        if self.repair is not None:
            return self.repair(agent, user)
        return {"items": [], "unresolved": re.findall(r'"issue_id": "([^"]+)"', user)}

    def _submit_contradictions(self, agent, user):
        return {"findings": self.r2}

    def _submit_window_extractions(self, agent, user):
        windows = []
        for block in re.findall(r"window_id: (W\d+)\nentity to extract: (.*?)\nfill these paths: (.*?)\nfocus quotes:\n"
                                r"\s+\[(\w+)\] (.*?)\n", user, re.S):
            wid, what, paths, sid, quote = block
            source = self._source_for(sid, quote, what)
            values = {}
            for p in [x.strip() for x in paths.split(",")]:
                v = _path(source, p) if source else None
                if v is None and p in DEFAULTS:
                    v = source.get(p, DEFAULTS[p]) if source else DEFAULTS[p]
                values[p] = v
            values.update(self.cs_override.get(quote, {}))
            windows.append({"window_id": wid, "values": values, "extra_assertions": []})
        return {"windows": windows}

    def _source_for(self, sid, quote, what):
        cands = [self.problem] if what.startswith("one problem") else \
            [i for i in self.items.values() if what == f"one {i['type']} item"]
        for obj in cands:
            ev = obj["evidence"][0]
            if ev["source_id"] == sid and ev["quote"] == quote:
                obj = copy.deepcopy(obj)
                if obj.get("type") == "vital_reading":
                    obj["attributes"].setdefault("unit", "mmHg")
                return obj
        return None

    def _submit_verdicts(self, agent, user):
        return {"verdicts": [{"pair_id": pid, "verdict": self.ce_verdict}
                             for pid in re.findall(r"pair_id (\S+) \|", user)]}

    def _submit_omissions(self, agent, user):
        return {"omissions": self.co_omissions}

    def _submit_grades(self, agent, user):
        return {"grades": [{"pair_id": pid, "verdict": "equivalent", "confidence": 0.9}
                           for pid in re.findall(r"pair_id (\S+) \|", user)]}

    def _submit_claim_grades(self, agent, user):
        return {"grades": [{"claim_id": cid, "label": "supported_by_transcript", "quote": None, "confidence": 0.8}
                           for cid in re.findall(r"claim_id (\S+) \|", user)]}

    def _submit_questions(self, agent, user):
        out = []
        for rid, ver, body in re.findall(r"rule (\w+) v(\S+): [\s\S]*?\nentities:\n((?:  - [^\n]*\n?)+)", user):
            ids = re.findall(r"  - (\w+):", body)
            out.append({"rule_id": rid, "rule_version": ver, "entity_ids": ids[:3], "question": f"Review {rid}?"})
        return {"questions": out}


def timeout_error():
    return anthropic.APITimeoutError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))


def mini_session(tmp_path, mode="baseline", rule_mode="synthetic_demo"):
    from pipeline.storage import Session
    from pipeline.transcribe import transcribe_text, write_quick_notes, write_visit_meta
    s = Session.create(root=tmp_path, pipeline_mode=mode, rule_mode=rule_mode)
    transcribe_text(s, MINI_TRANSCRIPT)
    write_quick_notes(s, MINI_QUICK_NOTES)
    write_visit_meta(s, date="2026-11-12", provider="Dr. Test")
    return s
