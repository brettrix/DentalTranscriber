"""A visit shaped like the "Bear" test visit: tooth #2 vs #3 across statements, the plan and a quick note; an
allergy the quick note denies; a prescription in the allergy's drug class; two blood pressure readings."""
from __future__ import annotations

from tests.fake_llm import FakeLLM, d, q

TRANSCRIPT = """DENTIST: What brings you in today?
PATIENT: My upper right tooth hurts when I bite.
DENTIST: Any allergies to medications?
PATIENT: Penicillin gives me hives.
DENTIST: Tapping on number three, that's the sore one.
DENTIST: This is a cracked tooth on number three.
DENTIST: I'll prescribe amoxicillin 500 milligrams three times a day.
DENTIST: We'll do a crown on number two next week.
DENTIST: Blood pressure is 184 over 112.
"""
QUICK_NOTES = "BP 132/84\nAllergy: none\nTx: #2\n"

PROBLEM = {"key": "P1", "role": "chief", "complaint_text": "upper right tooth hurts when biting",
           "complaint_location": {"free_text": "upper right", "tooth": None},
           "clinical_target": {"tooth": 3, "free_text": None}, "assertion_source": "clinician_assessment",
           "evidence": [q("u2", "My upper right tooth hurts when I bite."), q("u5", "Tapping on number three")],
           "derivations": [d("clinical_target.tooth", "spoken_tooth_number", "number three", 3, 1)]}

ITEMS = {
    "A1": {"key": "A1", "type": "allergy", "attributes": {"substance": "penicillin", "reaction": "hives",
                                                          "allergy_status": "reported_active"},
           "assertion_source": "patient_report", "evidence": [q("u4", "Penicillin gives me hives.")],
           "derivations": [d("attributes.substance", "drug_name", "Penicillin", "penicillin")]},
    "A2": {"key": "A2", "type": "allergy", "assertion": "denied",
           "attributes": {"substance": None, "original_wording": "Allergy: none", "allergy_status": "denied"},
           "assertion_source": "assistant_record", "evidence": [q("q2", "Allergy: none", "quick_note")]},
    "V1": {"key": "V1", "type": "vital_reading", "attributes": {"systolic": 132, "diastolic": 84, "sequence": 1},
           "assertion_source": "assistant_record", "evidence": [q("q1", "BP 132/84", "quick_note")],
           "derivations": [d("attributes.systolic", "bp_reading", "132/84", 132),
                           d("attributes.diastolic", "bp_reading", "132/84", 84)]},
    "V2": {"key": "V2", "type": "vital_reading", "attributes": {"systolic": 184, "diastolic": 112, "sequence": 2},
           "assertion_source": "clinician_observation", "evidence": [q("u9", "Blood pressure is 184 over 112.")],
           "derivations": [d("attributes.systolic", "bp_reading", "184 over 112", 184),
                           d("attributes.diastolic", "bp_reading", "184 over 112", 112)]},
    "F1": {"key": "F1", "type": "finding", "problem_key": "P1", "target": {"tooth": 3},
           "attributes": {"test": "percussion", "response": "present"}, "assertion_source": "test_response",
           "evidence": [q("u5", "Tapping on number three, that's the sore one.")],
           "derivations": [d("target.tooth", "spoken_tooth_number", "number three", 3)]},
    "D1": {"key": "D1", "type": "diagnosis", "problem_key": "P1", "target": {"tooth": 3},
           "attributes": {"diagnosis": "cracked tooth", "certainty": "definite"},
           "assertion_source": "clinician_assessment",
           "evidence": [q("u6", "This is a cracked tooth on number three.")],
           "derivations": [d("target.tooth", "spoken_tooth_number", "number three", 3)]},
    "RX1": {"key": "RX1", "type": "prescription",
            "attributes": {"drug": "amoxicillin", "strength": "500 mg", "frequency_code": "TID",
                           "prescription_status": "prescribed_today"},
            "assertion_source": "clinician_instruction",
            "evidence": [q("u7", "I'll prescribe amoxicillin 500 milligrams three times a day.")],
            "derivations": [d("attributes.drug", "drug_name", "amoxicillin", "amoxicillin"),
                            d("attributes.strength", "dose", "500 milligrams", "500 mg"),
                            d("attributes.frequency_code", "frequency", "three times a day", "TID")]},
    "N1": {"key": "N1", "type": "next_visit", "problem_key": "P1", "target": {"tooth": 2},
           "attributes": {"procedure": "crown", "timing": "next week"}, "time_context": "planned",
           "assertion_source": "clinician_instruction",
           "evidence": [q("u8", "We'll do a crown on number two next week.")],
           "derivations": [d("target.tooth", "spoken_tooth_number", "number two", 2)]},
    "T1": {"key": "T1", "type": "treatment_today", "problem_key": "P1", "target": {"tooth": 2},
           "attributes": {"procedure": "treatment"}, "assertion_source": "assistant_record",
           "evidence": [q("q3", "Tx: #2", "quick_note")],
           "derivations": [d("target.tooth", "spoken_tooth_number", "#2", 2)]},
}
R2 = [{"kind": "contradiction", "subject": "which tooth is treated", "later": "second",
       "first": {"source_type": "transcript", "source_id": "u6", "quote": "This is a cracked tooth on number three."},
       "second": {"source_type": "transcript", "source_id": "u8", "quote": "We'll do a crown on number two next week."}}]


def bear_session(tmp_path, patient="Bear", assistant="Kirstin"):
    from pipeline.orchestrator import run_pipeline
    from pipeline.storage import Session
    from pipeline.transcribe import transcribe_text, write_quick_notes, write_visit_meta
    s = Session.create(root=tmp_path, patient=patient, pipeline_mode="baseline", rule_mode="synthetic_demo")
    transcribe_text(s, TRANSCRIPT)
    write_quick_notes(s, QUICK_NOTES)
    write_visit_meta(s, date="2026-11-13", provider="Dr. Patel", assistant=assistant)
    run_pipeline(s, mode="baseline", client=FakeLLM(items=ITEMS, problem=PROBLEM, r2=R2))
    return s
