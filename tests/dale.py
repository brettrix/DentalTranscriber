"""A visit rebuilt from the lines quoted for the "Dale" visit. The original transcript is not in the repository,
so the conversation around those lines is reconstructed; the quoted lines are kept word for word. The fake model
returns what the real run returned wrong (fever as "possible", strengths missing, no discussion elements), so the
tests show the corrections working on the same mistakes."""
from __future__ import annotations

from tests.fake_llm import FakeLLM, d, q

TRANSCRIPT = """DENTIST: What brings you in today, Dale?
PATIENT: My lower left back tooth has been throbbing for three days.
DENTIST: Any fever?
PATIENT: I don't think so.
DENTIST: Are you taking any medications?
PATIENT: Eliquis, for my heart.
DENTIST: Any allergies?
PATIENT: Codeine makes me throw up, but that's not really an allergy.
DENTIST: Tapping on number nineteen.
PATIENT: Ow, yes, that one.
DENTIST: This is an abscess on number nineteen.
DENTIST: We can do a root canal, which will save the tooth and stop the pain.
DENTIST: The alternative is an extraction.
PATIENT: Let's do the root canal.
DENTIST: Take ibuprofen six hundred and Tylenol five hundred together every six hours.
"""
QUICK_NOTES = "BP 128/82\n"

PROBLEM = {"key": "P1", "role": "chief", "complaint_text": "lower left back tooth throbbing for three days",
           "complaint_location": {"free_text": "lower left", "tooth": None},
           "clinical_target": {"tooth": 19, "free_text": None}, "assertion_source": "clinician_assessment",
           "evidence": [q("u2", "My lower left back tooth has been throbbing for three days."),
                        q("u9", "Tapping on number nineteen.")],
           "derivations": [d("clinical_target.tooth", "spoken_tooth_number", "number nineteen", 19, 1)]}

RX_LINE = "Take ibuprofen six hundred and Tylenol five hundred together every six hours."
ITEMS = {
    "V1": {"key": "V1", "type": "vital_reading", "attributes": {"systolic": 128, "diastolic": 82, "sequence": 1},
           "assertion_source": "assistant_record", "evidence": [q("q1", "BP 128/82", "quick_note")],
           "derivations": [d("attributes.systolic", "bp_reading", "128/82", 128),
                           d("attributes.diastolic", "bp_reading", "128/82", 82)]},
    # As the real run returned it: an unsure "no" recorded as a possible finding.
    "S1": {"key": "S1", "type": "symptom", "problem_key": "P1", "assertion": "possible",
           "attributes": {"aspect": "other", "value": "fever"}, "assertion_source": "patient_report",
           "evidence": [q("u4", "I don't think so.")]},
    "M1": {"key": "M1", "type": "medication",
           "attributes": {"drug": "apixaban", "original_wording": "Eliquis", "medication_status": "current"},
           "assertion_source": "patient_report", "evidence": [q("u6", "Eliquis, for my heart.")],
           "derivations": [d("attributes.drug", "drug_name", "Eliquis", "apixaban")]},
    "A1": {"key": "A1", "type": "allergy",
           "attributes": {"substance": "codeine", "reaction": "makes me throw up", "allergy_status": "reported_active"},
           "assertion_source": "patient_report",
           "evidence": [q("u8", "Codeine makes me throw up, but that's not really an allergy.")],
           "derivations": [d("attributes.substance", "drug_name", "Codeine", "codeine")]},
    "F1": {"key": "F1", "type": "finding", "problem_key": "P1", "target": {"tooth": 19},
           "attributes": {"test": "percussion", "response": "present"}, "assertion_source": "test_response",
           "evidence": [q("u9", "Tapping on number nineteen."), q("u10", "Ow, yes, that one.")],
           "derivations": [d("target.tooth", "spoken_tooth_number", "number nineteen", 19)]},
    "D1": {"key": "D1", "type": "diagnosis", "problem_key": "P1", "target": {"tooth": 19},
           "attributes": {"diagnosis": "abscess", "certainty": "definite"}, "assertion_source": "clinician_assessment",
           "evidence": [q("u11", "This is an abscess on number nineteen.")],
           "derivations": [d("target.tooth", "spoken_tooth_number", "number nineteen", 19)]},
    "O1": {"key": "O1", "type": "option_discussed", "problem_key": "P1",
           "attributes": {"option": "root canal", "benefits": "will save the tooth and stop the pain",
                          "recommended_by_clinician": None},
           "assertion_source": "clinician_assessment",
           "evidence": [q("u12", "We can do a root canal, which will save the tooth and stop the pain.")]},
    "O2": {"key": "O2", "type": "option_discussed", "problem_key": "P1",
           "attributes": {"option": "extraction"}, "assertion_source": "clinician_assessment",
           "evidence": [q("u13", "The alternative is an extraction.")]},
    "DEC": {"key": "DEC", "type": "decision", "problem_key": "P1", "option_key": "O1",
            "attributes": {"decision": "accepted"}, "assertion_source": "patient_report",
            "evidence": [q("u14", "Let's do the root canal.")]},
    # As the real run returned them: the spoken strengths were dropped because no unit was said.
    "RX1": {"key": "RX1", "type": "prescription",
            "attributes": {"drug": "ibuprofen", "frequency_code": "q6h", "prescription_status": "prescribed_today"},
            "assertion_source": "clinician_instruction", "evidence": [q("u15", RX_LINE)],
            "derivations": [d("attributes.drug", "drug_name", "ibuprofen", "ibuprofen"),
                            d("attributes.frequency_code", "frequency", "every six hours", "q6h")]},
    "RX2": {"key": "RX2", "type": "prescription",
            "attributes": {"drug": "acetaminophen", "original_wording": "Tylenol", "frequency_code": "q6h",
                           "prescription_status": "prescribed_today"},
            "assertion_source": "clinician_instruction", "evidence": [q("u15", RX_LINE)],
            "derivations": [d("attributes.drug", "drug_name", "Tylenol", "acetaminophen"),
                            d("attributes.frequency_code", "frequency", "every six hours", "q6h")]},
}


def dale_session(tmp_path, patient="Dale"):
    from pipeline.orchestrator import run_pipeline
    from pipeline.storage import Session
    from pipeline.transcribe import transcribe_text, write_quick_notes, write_visit_meta
    s = Session.create(root=tmp_path, patient=patient, pipeline_mode="baseline", rule_mode="synthetic_demo")
    transcribe_text(s, TRANSCRIPT)
    write_quick_notes(s, QUICK_NOTES)
    write_visit_meta(s, date="2026-11-13", provider="Dr. Patel", assistant="Kirstin")
    run_pipeline(s, mode="baseline", client=FakeLLM(items=ITEMS, problem=PROBLEM))
    return s
