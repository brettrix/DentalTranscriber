"""Draft gold for tuning cases 1-3 (annotated_by: claude; checked_by left empty for a person to fill)."""
import json
from pathlib import Path

OUT = Path(__file__).parent


def ev(*ids):
    return [{"quick_note_id": i} if i.startswith("q") else {"utterance_id": i} for i in ids]


def E(gid, type, *, ev_ids, target=None, kind="item", scope=None, ka=None, assertion="present", tc="current",
      src=None, action=None, status=None, rel=None, note=None):
    scope = scope or ("encounter" if type in ("history_change", "medication", "allergy", "vital_reading") else "problem")
    return {"gid": gid, "kind": kind, "type": type, "problem_key": "P1" if scope == "problem" else None, "scope": scope,
            "target": target, "target_relation": rel if rel else ("matches_target" if target and scope == "problem" else None),
            "key_attributes": ka or {}, "assertion": assertion, "time_context": tc, "assertion_source": src,
            "action": action, "status_fields": status or {}, "evidence": ev(*ev_ids), "note": note}


def P(gid, complaint, location, target, ev_ids):
    return {"gid": gid, "kind": "problem", "type": None, "problem_key": "P1", "scope": None, "target": target,
            "target_relation": None, "key_attributes": {"role": "chief", "complaint_text": complaint,
                                                        "complaint_location": location},
            "assertion": "present", "time_context": "current", "assertion_source": None, "action": None,
            "status_fields": {}, "evidence": ev(*ev_ids)}


case1 = [
    P("p1", "sensitivity to cold, upper left", "upper left", 14, ["u2", "u15"]),
    E("s1", "symptom", ev_ids=["u2"], ka={"aspect": "trigger", "value": "cold (ice water)"}, src="patient_report"),
    E("s2", "symptom", ev_ids=["u3", "u4"], ka={"aspect": "onset", "value": "about 3 weeks, getting a little worse"}, src="patient_report"),
    E("s3", "symptom", ev_ids=["u5", "u6"], ka={"aspect": "lingering", "value": "goes away fast, about 5 seconds"}, src="patient_report"),
    E("s4", "symptom", ev_ids=["u7", "u8"], ka={"aspect": "night_pain"}, assertion="denied", src="patient_report"),
    E("s5", "symptom", ev_ids=["u7", "u8"], ka={"aspect": "spontaneous_pain"}, assertion="denied", src="patient_report"),
    E("s6", "symptom", ev_ids=["u9", "u10"], ka={"aspect": "biting_pain"}, assertion="denied", src="patient_report"),
    E("s7", "symptom", ev_ids=["u11", "u12"], ka={"aspect": "severity", "score": 4}, src="patient_report"),
    E("h1", "history_change", ev_ids=["u13", "u14", "q4"], ka={"description": "no changes to health or medications"},
      assertion="absent", src="patient_report"),
    E("a1", "allergy", ev_ids=["q4"], ka={"substance": None}, assertion="denied", status={"allergy_status": "denied"}),
    E("v1", "vital_reading", ev_ids=["q1"], ka={"systolic": 124, "diastolic": 80}, src="assistant_record"),
    E("f1", "finding", ev_ids=["u15"], target=14, ka={"observation": "existing MO amalgam (silver filling) with dark staining at the margin", "surface": "MO"}, src="clinician_observation"),
    E("f2", "finding", ev_ids=["u15", "u16"], target=14, ka={"test": "percussion", "response": "absent"}, src="test_response"),
    E("f3", "finding", ev_ids=["u17", "u18", "u19", "u20", "u21"], target=14, ka={"test": "cold", "response": "present", "lingering": False}, src="test_response"),
    E("x1", "radiograph", ev_ids=["u21", "u22", "u23"], target=14, ka={"type": "PA", "finding": "recurrent decay under the filling on the mesial, not near the pulp; no periapical pathology"}, action="performed", src="clinician_observation"),
    E("d1", "diagnosis", ev_ids=["u25"], target=14, ka={"diagnosis": "reversible pulpitis", "certainty": "definite"}, src="clinician_assessment"),
    E("o1", "option_discussed", ev_ids=["u25"], target=14, ka={"option": "replace the old filling with a composite (tooth-colored) filling"}, src="clinician_assessment"),
    E("o2", "option_discussed", ev_ids=["u26", "u27"], target=14, ka={"option": "crown", "recommended_by_clinician": False}, src="clinician_assessment",
      note="crown not needed now"),
    E("c1", "consent_element", ev_ids=["u27"], ka={"element": "consequences_of_refusal_discussed", "content": "decay will keep growing and could reach the nerve, needing a root canal"}, src="clinician_assessment"),
    E("dc1", "decision", ev_ids=["u28"], ka={"decision": "accepted", "option": "composite filling"}, src="patient_report"),
    E("n1", "next_visit", ev_ids=["u29"], target=14, ka={"procedure": "replace MO filling with composite", "timing": "next week"}, tc="planned", src="clinician_instruction"),
    E("i1", "instruction", ev_ids=["u29"], ka={"text": "use a sensitivity toothpaste"}, src="clinician_instruction"),
    E("i2", "instruction", ev_ids=["u29"], ka={"text": "avoid really cold drinks on that side"}, src="clinician_instruction"),
]
case2 = [
    P("p1", "sharp pain when chewing on the lower right, especially hard foods", "lower right", 30, ["u2", "u13"]),
    E("s1", "symptom", ev_ids=["u2"], ka={"aspect": "trigger", "value": "chewing, especially hard foods like nuts; sharp"}, src="patient_report"),
    E("s2", "symptom", ev_ids=["u3", "u4"], ka={"aspect": "onset", "value": "about a month ago after biting a popcorn kernel"}, src="patient_report"),
    E("s3", "symptom", ev_ids=["u5", "u6"], ka={"aspect": "biting_pain", "value": "quick sharp pain on biting and on release"}, src="patient_report"),
    E("s4", "symptom", ev_ids=["u7", "u8"], ka={"aspect": "trigger", "value": "a little sensitive to cold, goes away"}, src="patient_report"),
    E("s5", "symptom", ev_ids=["u9", "u10"], ka={"aspect": "severity", "score": 7}, src="patient_report"),
    E("m1", "medication", ev_ids=["u11", "u12", "q4"], ka={"drug": "lisinopril"}, status={"medication_status": "current"}, src="patient_report",
      note="started a couple months ago for blood pressure"),
    E("v1", "vital_reading", ev_ids=["q1"], ka={"systolic": 138, "diastolic": 86}, src="assistant_record"),
    E("f1", "finding", ev_ids=["u13"], target=30, ka={"observation": "large existing filling"}, src="clinician_observation"),
    E("f2", "finding", ev_ids=["u13", "u14", "u15", "u16"], target=30, ka={"test": "bite test (cusp by cusp)", "response": "present", "result_description": "pain on the distal-lingual cusp, including on release"}, src="test_response"),
    E("f3", "finding", ev_ids=["u17", "u18", "u19"], target=30, ka={"test": "cold", "response": "present", "lingering": False, "result_description": "normal response"}, src="test_response"),
    E("f4", "finding", ev_ids=["u19", "u20"], target=30, ka={"test": "percussion", "response": "absent"}, src="test_response"),
    E("x1", "radiograph", ev_ids=["u21", "u22", "u23"], target=30, ka={"type": "PA", "finding": "normal: no decay under the filling, root tips healthy"}, action="performed", src="clinician_observation"),
    E("d1", "diagnosis", ev_ids=["u23"], target=30, ka={"diagnosis": "cracked tooth", "certainty": "definite"}, src="clinician_assessment",
      note="worded 'this looks like a cracked tooth'; certainty is debatable (definite vs possible) — checker to decide"),
    E("o1", "option_discussed", ev_ids=["u25"], target=30, ka={"option": "crown", "recommended_by_clinician": True}, src="clinician_assessment"),
    E("c1", "consent_element", ev_ids=["u27"], ka={"element": "consequences_of_refusal_discussed", "content": "if delayed the crack can grow into the nerve (root canal) or split the root (extraction)"}, src="clinician_assessment"),
    E("dc1", "decision", ev_ids=["u28"], ka={"decision": "deferred", "option": "crown", "reason": "check insurance first, maybe January"}, src="patient_report"),
    E("i1", "instruction", ev_ids=["u29"], ka={"text": "chew on the other side"}, src="clinician_instruction"),
    E("i2", "instruction", ev_ids=["u29"], ka={"text": "avoid hard foods like nuts and ice"}, src="clinician_instruction"),
    E("i3", "instruction", ev_ids=["u29"], ka={"text": "call right away if it hurts on its own or wakes you up"}, src="clinician_instruction"),
]
case3 = [
    P("p1", "lower left jaw swelling since yesterday with a throbbing tooth that kept them up at night", "lower left jaw", 19, ["u2", "u13"]),
    E("s1", "symptom", ev_ids=["u2"], ka={"aspect": "swelling", "value": "lower left jaw swelling since yesterday"}, src="patient_report"),
    E("s2", "symptom", ev_ids=["u2"], ka={"aspect": "quality", "value": "throbbing"}, src="patient_report"),
    E("s3", "symptom", ev_ids=["u2"], ka={"aspect": "night_pain", "value": "kept them up last night"}, src="patient_report"),
    E("s4", "symptom", ev_ids=["u3", "u4"], ka={"aspect": "prior_treatment", "value": "hurt on and off a few months ago, then stopped"}, tc="historical", src="patient_report",
      note="aspect could also be 'onset'; the time context is the key attribute"),
    E("s5", "symptom", ev_ids=["u5", "u6"], ka={"aspect": "severity", "score": 8}, src="patient_report"),
    E("s6", "symptom", ev_ids=["u7", "u8"], ka={"aspect": "other", "value": "fever"}, assertion="denied", src="patient_report", note="'I don't think so' — no known fever"),
    E("a1", "allergy", ev_ids=["u9", "u10", "q4"], ka={"substance": "penicillin", "reaction": "hives"}, status={"allergy_status": "reported_active"}, src="patient_report"),
    E("h1", "history_change", ev_ids=["u11", "u12"], ka={"description": "no other changes to health"}, assertion="absent", src="patient_report"),
    E("v1", "vital_reading", ev_ids=["q1"], ka={"systolic": 130, "diastolic": 84}, src="assistant_record"),
    E("f1", "finding", ev_ids=["u13"], target=19, ka={"observation": "large filling"}, src="clinician_observation"),
    E("f2", "finding", ev_ids=["u13"], target=19, ka={"observation": "buccal gingival swelling next to the tooth"}, src="clinician_observation"),
    E("f3", "finding", ev_ids=["u13", "u14"], target=19, ka={"test": "palpation", "response": "present", "result_description": "tender"}, src="test_response"),
    E("f4", "finding", ev_ids=["u15", "u16"], target=19, ka={"test": "percussion", "response": "present"}, src="test_response"),
    E("f5", "finding", ev_ids=["u17", "u18", "u19"], target=19, ka={"test": "cold", "response": "absent"}, src="test_response"),
    E("x1", "radiograph", ev_ids=["u19", "u20", "u21"], target=19, ka={"type": "PA", "finding": "periapical radiolucency (dark area) around the root tips"}, action="performed", src="clinician_observation"),
    E("d1", "diagnosis", ev_ids=["u21"], target=19, ka={"diagnosis": "pulp necrosis with acute apical abscess", "certainty": "definite"}, src="clinician_assessment"),
    E("o1", "option_discussed", ev_ids=["u23"], target=19, ka={"option": "root canal then a crown"}, src="clinician_assessment"),
    E("o2", "option_discussed", ev_ids=["u23"], target=19, ka={"option": "extraction (implant or bridge later)"}, src="clinician_assessment"),
    E("c1", "consent_element", ev_ids=["u23"], ka={"element": "alternatives_discussed", "content": "root canal + crown vs extraction"}, src="clinician_assessment",
      note="the two options with their trade-offs; benefits/risks elements may also be recorded"),
    E("dc1", "decision", ev_ids=["u24", "u25"], ka={"decision": "accepted", "option": "root canal"}, src="patient_report"),
    E("rx1", "prescription", ev_ids=["u25"], ka={"drug": "amoxicillin", "strength": "500 mg", "frequency_code": "TID", "duration_days": 7}, status={"prescription_status": "prescribed_today"}, src="clinician_instruction",
      scope="problem"),
    E("rx2", "prescription", ev_ids=["u25"], ka={"drug": "ibuprofen", "strength": "600 mg", "frequency_code": "q6h PRN"}, status={"prescription_status": "prescribed_today"}, src="clinician_instruction",
      scope="problem", note="scope may be encounter"),
    E("n1", "next_visit", ev_ids=["u25"], target=19, ka={"procedure": "root canal", "timing": "within the next few days"}, tc="planned", src="clinician_instruction"),
    E("i1", "instruction", ev_ids=["u27"], ka={"text": "go to the ER if swelling spreads toward the eye or neck, or trouble swallowing or breathing"}, src="clinician_instruction"),
]
FLAGS = {
    "case1": [], "case2": [],
    "case3": [{"rule_id": "allergy_rx", "problem_key": "P1", "target": None,
               "meaning": "penicillin allergy (hives, active) and amoxicillin prescribed today: high, safety-critical",
               "evidence": ev("u10", "u25")}],
}
META = {
    "case1": {"forbidden_facts": ["skiing", "snow", "weekend"], "expected_decision": "accepted"},
    "case2": {"forbidden_facts": [], "expected_decision": "deferred"},
    "case3": {"forbidden_facts": [], "expected_decision": "accepted"},
}
for name, ents in (("case1", case1), ("case2", case2), ("case3", case3)):
    doc = {"case_id": name, "annotated_by": "claude", "checked_by": None, "entities": ents,
           "expected_flags": FLAGS[name], **META[name],
           "notes": "Draft gold from the role-play script and answer key. Needs a person to check before scoring "
                    "counts (section 14.2)."}
    (OUT / f"{name}.json").write_text(json.dumps(doc, indent=1) + "\n", "utf-8")
    print(name, len(ents))
