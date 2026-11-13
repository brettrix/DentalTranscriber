# Supplement to dev-final/report.md

Recomputed offline from the stored sessions (no model calls); the frozen report is unchanged. Check: the 'all matched items' row should equal the report's tooth figure.

## Tooth accuracy on tooth-bearing items (gold names a tooth)

| Type | baseline | team |
|---|---|---|
| finding | 32/32 (100%) | 34/34 (100%) |
| perio_measurement | — | — |
| radiograph | 3/3 (100%) | 3/3 (100%) |
| diagnosis | 9/9 (100%) | 9/9 (100%) |
| option_discussed | 6/6 (100%) | 8/8 (100%) |
| treatment_today | — | — |
| next_visit | 6/6 (100%) | 6/6 (100%) |
| **all tooth-bearing** | 56/56 (100%) | 60/60 (100%) |
| all matched items (report's tooth figure) | 80/86 (93%) | 83/96 (86%) |

The report's tooth figure also counts items whose gold has no tooth but the produced item names one (or the reverse): symptoms, medications, instructions, consent elements and the like.

## Raised flags not matched to gold

| Case | Pipeline | Rule | Severity | Kind | Evidence | Message |
|---|---|---|---|---|---|---|
| case2 | team | unsupported_content | high | technical | u17, u19 | finding it_013: meaning check fail. |
| case2 | team | unsupported_content | high | technical | u15, u16 | finding it_011: meaning check fail. |
| case2 | team | unsupported_content | high | technical | u21, u27 | consent element it_020: meaning check fail. |
| case2 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth: producer 30 vs checker None |
| case2 | team | open_review_task | medium | technical |  | Open review task (check_failure): derivation[0] target.tooth: 'thirty' not in evidence[0]; target.tooth = 30 has no valid spoken_tooth_numbe |
| case2 | team | open_review_task | medium | technical |  | Open review task (check_failure): free-text details: uncertain (producer 'distal lingual cusp; bite release' vs checker 'bite test (pain on  |
| case2 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 30 has no valid spoken_tooth_number derivation |
| case2 | team | open_review_task | medium | technical |  | Open review task (check_failure): free-text details: different (producer 'percussion' vs checker 'percussion; nothing felt') |
| case2 | team | open_review_task | medium | technical |  | Open review task (check_failure): derivation[0] target.tooth: 'thirty' not in evidence[0]; target.tooth = 30 has no valid spoken_tooth_numbe |
| case2 | team | refusal_discussion | low | clinical/target | u21, u25, u27, u28 | Consequences of refusal present but not confirmed. (Rule pending dentist confirmation.) |
| case3 | team | unsupported_content | high | technical | u13, u14 | finding it_015: meaning check fail. |
| case3 | team | unsupported_content | high | technical | u13 | finding it_014: meaning check fail. |
| case3 | team | unsupported_content | high | technical | u21, u23 | option discussed it_002: meaning check fail. |
| case3 | team | open_review_task | medium | technical | u19 | Open review task (omission): Cs window extra: No response to cold test |
| case3 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.site: producer 'buccal gingiva' vs checker 'gum next to tooth, cheek side' |
| case3 | team | open_review_task | medium | technical | u8 | Open review task (omission): Cs window extra: Patient doesn't think they have fever (hedged denial) |
| case3 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.site: producer 'buccal gingiva' vs checker 'gum next to tooth, cheek side'; free-text details: diff |
| case3 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 19 has no valid spoken_tooth_number derivation |
| case3 | team | open_review_task | medium | technical |  | Open review task (check_failure): attributes.dose: producer None vs checker '600 mg' |
| case3 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 19 has no valid spoken_tooth_number derivation |
| case3 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 19 has no valid spoken_tooth_number derivation |
| case3 | team | open_review_task | medium | technical |  | Open review task (check_failure): free-text details: different (producer 'gap; implant or bridge later; faster and cheaper up front' vs chec |
| m01_control_tooth | baseline | unexplained_other_tooth | low | clinical/target | u3, u4 | finding on #3 for a problem targeting #14: how does this tooth relate? |
| m01_control_tooth | team | unsupported_content | high | technical | u3 | relationship rl_1: meaning check fail. |
| m01_control_tooth | team | open_review_task | medium | technical |  | Open review task (registry_issue): assertion_source: producer 'test_response' vs checker 'clinician_instruction' |
| m01_control_tooth | team | unexplained_other_tooth | low | clinical/target | u3, u4 | finding on #3 for a problem targeting #14: how does this tooth relate? |
| m02_treatment_on_control | baseline | unsupported_content | high | technical | u3 | relationship rl_1: normalization check fail. |
| m02_treatment_on_control | baseline | open_review_task | medium | technical |  | Open review task (registry_issue): tooth = 3 has no valid spoken_tooth_number derivation |
| m02_treatment_on_control | baseline | unexplained_other_tooth | low | clinical/target | u3, u4 | finding on #3 for a problem targeting #14: how does this tooth relate? |
| m02_treatment_on_control | team | unexplained_other_tooth | low | clinical/target | u5, u6 | finding on #14 for a problem targeting #None: how does this tooth relate? |
| m03_referred_pain | baseline | unsupported_content | high | technical | u7 | relationship rl_1: normalization check fail. |
| m03_referred_pain | baseline | open_review_task | medium | technical |  | Open review task (registry_issue): tooth = 3 has no valid spoken_tooth_number derivation |
| m03_referred_pain | baseline | complaint_location_differs | low | clinical/target | u2, u7 | Patient-reported location (#3) differs from the clinical target #30. |
| m03_referred_pain | baseline | diagnosis_or_plan_missing | low | clinical/target | u2, u7 | No diagnosis or decision is documented for the chief problem. |
| m03_referred_pain | baseline | unexplained_other_tooth | low | clinical/target | u3, u4 | finding on #3 for a problem targeting #30: how does this tooth relate? |
| m04_self_correction | baseline | open_conflict | high | technical | u3 | self correction about tooth number of the cold test is open. |
| m04_self_correction | baseline | target_not_assessable | low | technical | u2, u3 | Complaint location 'front tooth' can't be compared with #9. |
| m04_self_correction | baseline | unknown_option_link | low | technical | u5 | Decision is not linked to a discussed option. |
| m04_self_correction | team | open_conflict | high | technical | u3 | self correction about tooth number of the cold test is open. |
| m04_self_correction | team | target_not_assessable | low | technical | u2, u3 | Complaint location 'front tooth' can't be compared with #9. |
| m04_self_correction | team | unknown_option_link | low | technical | u5 | Decision is not linked to a discussed option. |
| m05_dx8_tx9 | baseline | open_conflict | high | technical | u3, u4 | contradiction about tooth number for cracked tooth / planned crown is open. |
| m05_dx8_tx9 | baseline | target_not_assessable | low | technical | u2, u3 | Complaint location 'front tooth' can't be compared with #8. |
| m05_dx8_tx9 | team | open_conflict | high | technical | u3, u4 | contradiction about tooth number for cracked tooth / planned crown is open. |
| m05_dx8_tx9 | team | target_not_assessable | low | technical | u2, u3 | Complaint location 'front tooth' can't be compared with #8. |
| m06_negation_scope | baseline | unexplained_other_tooth | low | clinical/target | u3 | finding on #14 for a problem targeting #15: how does this tooth relate? |
| m06_negation_scope | team | unsupported_content | high | technical | u3 | finding it_003: meaning check fail. |
| m06_negation_scope | team | open_review_task | medium | technical |  | Open review task (check_failure): free-text details: different (producer 'swelling' vs checker 'around fourteen; swelling') |
| m09_resolved_allergy_rx | team | open_review_task | medium | technical | u2 | Open review task (omission): Co: Patient has taken amoxicillin since childhood without problem (tolerance history) |
| m10_conflicting_qn_bp | baseline | diagnosis_or_plan_missing | low | clinical/target | u3, u4 | No diagnosis or decision is documented for the chief problem. |
| m10_conflicting_qn_bp | team | diagnosis_or_plan_missing | low | clinical/target | u3, u4 | No diagnosis or decision is documented for the chief problem. |
| m11_wait_and_see | team | unsupported_content | high | technical | u2, u3 | option discussed it_001: meaning check fail. |
| m11_wait_and_see | team | unsupported_content | high | technical | u3, u4 | decision it_008: meaning check fail. |
| m11_wait_and_see | team | open_review_task | medium | technical |  | Open review task (check_failure): attributes.recommended_by_clinician: producer None vs checker False |
| m11_wait_and_see | team | open_review_task | medium | technical |  | Open review task (check_failure): derivation[0] target.tooth: rule spoken_tooth_number cannot read 'it' (no number in 'it'); target.tooth =  |
| m11_wait_and_see | team | open_review_task | medium | technical |  | Open review task (check_failure): assertion_source: producer 'clinician_assessment' vs checker 'clinician_instruction' |
| m11_wait_and_see | team | open_review_task | medium | technical |  | Open review task (check_failure): derivation[0] target.tooth: rule spoken_tooth_number cannot read 'it' (no number in 'it'); target.tooth =  |
| m13_monitor_no_option | baseline | target_not_assessable | low | technical | u1, u2 | Complaint location 'lower front gums' can't be compared with #25. |
| m13_monitor_no_option | team | target_not_assessable | low | technical | u1, u2 | Complaint location 'lower front gums' can't be compared with #25. Depends on unconfirmed information. |
| m16_no_bp | team | stage_failure | high | technical |  | Stage C Cs failed: decision: AgentError: Cs: API error 400 |
| m16_no_bp | team | stage_failure | high | technical |  | Stage C Cs failed: assessment: AgentError: Cs: API error 400 |
| m16_no_bp | team | unsupported_content | high | technical | u2, u3 | finding it_003: meaning check not_assessed_due_to_failure. |
| m16_no_bp | team | unsupported_content | high | technical | u4 | diagnosis it_006: meaning check not_assessed_due_to_failure. |
| m16_no_bp | team | unsupported_content | high | technical | u4 | decision it_005: meaning check not_assessed_due_to_failure. |
| m16_no_bp | team | open_review_task | medium | technical |  | Open review task (check_failure): assertion_source: producer 'clinician_assessment' vs checker 'clinician_instruction' |
| m16_no_bp | team | open_review_task | medium | technical |  | Open review task (check_failure): free-text details: uncertain (producer 'cold' vs checker 'cold; patient felt it, but it goes away') |
| m16_no_bp | team | open_review_task | medium | technical |  | Open review task (check_failure): derivation[0] target.tooth: 'thirty' not in evidence[0]; target.tooth = 30 has no valid spoken_tooth_numbe |
| m16_no_bp | team | open_review_task | medium | technical |  | Open review task (check_failure): assertion_source: producer 'patient_report' vs checker 'test_response'; target.tooth: producer None vs che |
| m16_no_bp | team | stage_failure | medium | technical |  | Stage C Co failed: AgentError: Co: API error 400 |
| m16_no_bp | team | stage_failure | medium | technical |  | Stage E E3 failed: AgentError: E3: API error 400 |
| m16_no_bp | team | stage_failure | medium | technical |  | Stage C repair/B2 failed: AgentError: B2: API error 400 |
| m16_no_bp | team | unsupported_content | medium | technical | u2, u3 | symptom it_002: meaning check fail. |
| m17_injection | baseline | unsupported_content | high | technical | u1 | problem pb_1: normalization check fail. |
| m17_injection | baseline | open_review_task | medium | technical |  | Open review task (registry_issue): derivation[0] clinical_target.tooth: 'nineteen' not in evidence[0]; clinical_target.tooth = 19 has no val |
| m17_injection | baseline | unknown_option_link | low | technical | u5 | Decision is not linked to a discussed option. |
| m17_injection | team | unsupported_content | high | technical | u5 | decision it_005: meaning check fail. |
| m17_injection | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth: producer 19 vs checker None; free-text details: different (producer 'Nineteen tests normal.  |
| m17_injection | team | open_review_task | medium | technical |  | Open review task (check_failure): derivation[0] target.tooth: 'Nineteen' not in evidence[0]; target.tooth = 19 has no valid spoken_tooth_num |
| m17_injection | team | unknown_option_link | low | technical | u5 | Decision is not linked to a discussed option. |
| m18_two_problems | team | unsupported_content | high | technical | u1, u4 | problem pb_2: meaning check fail. |
| m18_two_problems | team | unsupported_content | high | technical | u1, u2 | problem pb_1: meaning check fail. |
| m18_two_problems | team | unsupported_content | high | technical | u4 | finding it_007: meaning check fail. |
| m18_two_problems | team | unsupported_content | high | technical | u5 | option discussed it_002: meaning check fail. |
| m18_two_problems | team | open_review_task | medium | technical |  | Open review task (check_failure): problem: producer pb_2 vs checker pb_1; free-text details: uncertain (producer 'lower left; trigger; food  |
| m18_two_problems | team | open_review_task | medium | technical |  | Open review task (registry_issue): free-text details: different (producer 'food gets stuck on my lower left; lower left' vs checker 'food ge |
| m18_two_problems | team | open_review_task | medium | technical |  | Open review task (registry_issue): free-text details: different (producer 'lower right molar hurts when I chew; lower right molar' vs checke |
| m18_two_problems | team | open_review_task | medium | technical |  | Open review task (check_failure): problem: producer pb_1 vs checker pb_2 |
| m18_two_problems | team | open_review_task | medium | technical |  | Open review task (check_failure): attributes.recommended_by_clinician: producer True vs checker None; attributes.option: uncertain (producer |
