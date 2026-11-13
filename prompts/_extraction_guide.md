# How to record extracted entities

You record what was stated in a dental limited exam, from the transcript and the assistant's quick notes. You never decide anything clinical. Each entity is one distinct clinical statement, tied to exact evidence.

## Evidence
- Cite every source line the entity depends on: for a question and its answer, cite both lines (the question first). For a test, cite the clinician's line naming the test and tooth and the patient's response line.
- `quote` is an exact, character-for-character copy of part of ONE line's text (no id, no speaker label). Short quotes are fine; never paraphrase or join lines.
- Quick notes are evidence (`source_type: "quick_note"`, `source_id` like `q2`). When the transcript and a quick note state the same fact with the same value, make one entity citing both. When they state different values, make separate entities — never pick one.
- Visit details come from visit metadata (`source_type: "visit_meta"`, `source_id: "visit_meta"`, quote the value).

## Who said it
`assertion_source` is the kind of statement:
- `patient_report`: the patient describes symptoms, history, beliefs. A patient guessing a diagnosis ("I think it's infected") is a `symptom` (aspect `other`) or history note from the patient, never a `diagnosis`.
- `clinician_observation`: the clinician describes what they see on exam or on an image.
- `test_response`: a clinical test and the patient's response to it.
- `clinician_assessment`: the dentist's diagnosis, assessment, or recommendation.
- `clinician_instruction`: the clinician's instructions, prescriptions, plans.
- `assistant_record`: something the assistant recorded or did (including quick notes the assistant typed, unless the line is clearly the dentist's assessment).
Speaker roles are shown on each transcript line; do not change them.

## Status and time
- `assertion`: `present` (stated as so), `absent` (stated as not so, e.g. "no swelling"), `denied` (patient denies, e.g. "no allergies"), `possible` (hedged), `unintelligible`.
- `time_context` is about when the fact holds: `current` (true now, or said or done during this visit — including options discussed, decisions made, instructions given and prescriptions written today), `historical` (in the past, e.g. a medicine stopped last year), `planned` (a future procedure or imaging that has not happened yet; `next_visit` items are `planned`).
- Use `denied` when the patient says no to a question about themselves (symptoms, history, allergies); use `absent` when a clinician reports something is not there.
- Never infer from silence: if something was not discussed, do not create an entity for it, and leave unstated attributes `null`.

## Values and derivations
Some attributes are normalized values. For each one, add a derivation `{attribute, rule, from, to, evidence_index}`:
- `from` is the exact words inside the quote at `evidence_index` (e.g. `"number fourteen"`), `to` is the value you put on the entity, and `attribute` is its path (`target.tooth`, `clinical_target.tooth`, `attributes.strength`, …).
- Rules and value formats:
  - `spoken_tooth_number`: tooth numbers 1–32 (Universal). "number fourteen", "#14", "tooth 14", "fourteen" → 14.
  - `spoken_number`: plain numbers such as a pain score or seconds. "a four" → 4.
  - `bp_reading`: blood pressure. Write two derivations, `attributes.systolic` (to = 172) and `attributes.diastolic` (to = 104), both with from = "172 over 104" or "172/104".
  - `dose`: strengths and doses as "<number> <unit>" with unit mg, g, mcg, mL, units or %. "five hundred milligrams" → "500 mg".
  - `frequency`: TID, BID, QD, QID, QHS, q<N>h, with " PRN" appended for "as needed". "every six hours as needed" → "q6h PRN".
  - `duration`: whole days as an integer. "for seven days" → 7.
  - `surface_code`: tooth surfaces as letters (M, O, D, B, L, F, I). "M O D" → "MOD".
  - `drug_name`: the generic name in lowercase ("Motrin" → "ibuprofen"). Combination products as "a/b". If you do not recognize the drug, leave `drug` (or `substance`) null and keep the words in `original_wording`.
  - `mm_measure`: periodontal measurements in millimeters.
- Every attribute marked `[derive: …]` in the attribute table, and every tooth, needs a derivation when it is not null. If you cannot quote words that produce the value, leave the value null.
- Interpretations (response, lingering, certainty, decisions, statuses, free text) may carry a `semantic` derivation pointing at the words they come from. These are optional but helpful.
- An `absent` or `denied` entity needs a `negation` derivation: `from` is the negation word or phrase ("no", "not really", "nope"), `concept` is the words naming what is negated, and `concept_evidence_index` points to the quote containing the concept. The concept must be in the same quote as the cue, or in the clinician's question line directly before the patient's answer (cite both).

## Problems and relationships
- A problem is a complaint the visit addresses. Its `assertion_source` is `patient_report` when the patient raised the complaint (the usual case) and `clinician_assessment` when the clinician raised it. Exactly one `chief` problem (the main reason for the visit); others are `secondary`.
- `complaint_location`: where the patient says it hurts (their words in `free_text`; a tooth only if the patient names one).
- `clinical_target`: the tooth the clinician identifies as the problem tooth. Leave it null if the clinician never identifies one.
- A relationship links a problem to another tooth, only when the source states or clearly shows it: `control` (a tooth tested for comparison), `referred_from` (the complaint is felt in one place but comes from the problem tooth; `tooth` is where it is felt), `adjacent_examined` (a neighbouring tooth examined), `secondary_problem` (another tooth with its own problem).

## Items
Each item has a `type`, a `problem_key` (null for encounter items), a `target` (tooth/surface/site/free_text), `attributes` from the table below, `assertion`, `time_context`, `assertion_source`, evidence and derivations.
- One finding per test or observation per tooth. A test that was done is `assertion: present` whatever its result; a negative result is `response: absent`. `response`: present (felt / positive), absent (nothing felt / negative), uncertain. `lingering`: true, false, or null if not discussed. `duration_s`: seconds if stated.
- Radiograph `action`: performed, discussed, planned, declined, not_needed. Put what the image shows in `finding`.
- Diagnosis only from a clinician's assessment. `certainty`: `possible` when hedged ("could be", "might", "probably", "rule out"), otherwise `definite`.
- `option_discussed.recommended_by_clinician`: true only when the dentist recommends it; false when the dentist advises against it; otherwise null.
- `decision`: link the option it decides with `option_key` (the option's key). If no option was discussed, leave `option_key` null — never invent an option. A dentist's own wait-and-see plan is `monitor`. Accepting an option does not imply any consent element.
- `consent_element`: one per element actually discussed (risks, benefits, alternatives, consequences of refusal or delay, questions answered), linked with `option_key` or `decision_key`.
- `prescription_status`: prescribed_today, discussed_not_prescribed, continuing.
- `medication_status`: current, discontinued, historical, unknown. `allergy_status`: reported_active, denied, uncertain, disputed, reported_resolved. A blanket "no allergies" is one allergy item with substance null, allergy_status denied, assertion denied.
- A blanket "no changes to health or medications" is one `history_change` item with assertion absent.
- Every BP reading is its own `vital_reading`, in order (`sequence` 1, 2, …; `label` initial or recheck if stated).
- Self-corrections ("eight — sorry, nine"): record the corrected value and cite the line.
- Small talk (weather, weekend plans, pleasantries) is not clinical and is never extracted.
