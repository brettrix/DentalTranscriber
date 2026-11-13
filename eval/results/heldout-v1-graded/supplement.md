# Supplement to heldout-v1-graded/report.md

Recomputed offline from the stored sessions (no model calls); the frozen report is unchanged. Check: the 'all matched items' row should equal the report's tooth figure.

## Tooth accuracy on tooth-bearing items (gold names a tooth)

| Type | baseline | team |
|---|---|---|
| finding | 10/11 (91%) | 11/12 (92%) |
| perio_measurement | 3/3 (100%) | 6/6 (100%) |
| radiograph | 5/5 (100%) | 5/5 (100%) |
| diagnosis | 3/4 (75%) | 3/4 (75%) |
| option_discussed | 2/7 (29%) | 2/6 (33%) |
| treatment_today | — | — |
| next_visit | 1/4 (25%) | 3/4 (75%) |
| **all tooth-bearing** | 24/34 (71%) | 30/37 (81%) |
| all matched items (report's tooth figure) | 35/61 (57%) | 37/62 (60%) |

The report's tooth figure also counts items whose gold has no tooth but the produced item names one (or the reverse): symptoms, medications, instructions, consent elements and the like.

## Raised flags not matched to gold

| Case | Pipeline | Rule | Severity | Kind | Evidence | Message |
|---|---|---|---|---|---|---|
| case4 | team | unsupported_content | high | technical | u9 | perio measurement it_015: meaning check fail. |
| case4 | team | unsupported_content | high | technical | u9 | perio measurement it_013: meaning check fail. |
| case4 | team | unsupported_content | high | technical | u9 | perio measurement it_011: meaning check fail. |
| case4 | team | unsupported_content | high | technical | u9 | perio measurement it_014: meaning check fail. |
| case4 | team | unsupported_content | high | technical | u9 | perio measurement it_010: meaning check fail. |
| case4 | team | unsupported_content | high | technical | u9 | perio measurement it_012: meaning check fail. |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): free-text details: producer "upper right quadrant; might be a little sore for a day or two; regular cleani |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.site: producer 'ML' vs checker None |
| case4 | team | open_review_task | medium | technical | u6 | Open review task (omission): Cs window extra: Last cleaning maybe three years ago |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): free-text details: uncertain (producer 'generalized; plaque moderate' vs checker 'plaque; moderate') |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 3 has no valid spoken_tooth_number derivation |
| case4 | team | open_review_task | medium | technical | u6 | Open review task (omission): Cs window extra: Last dental cleaning about three years ago |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.site: producer 'L' vs checker None |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.site: producer 'MB' vs checker None |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 3 has no valid spoken_tooth_number derivation |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 3 has no valid spoken_tooth_number derivation |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.site: producer 'DB' vs checker None |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.site: producer 'B' vs checker None |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 3 has no valid spoken_tooth_number derivation |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.site: producer 'DL' vs checker None |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 3 has no valid spoken_tooth_number derivation |
| case4 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 3 has no valid spoken_tooth_number derivation |
| case4 | team | unsupported_content | medium | technical | u15, u17 | option discussed it_001: meaning check fail. |
| case4 | team | unsupported_content | medium | technical | u11 | finding it_016: meaning check fail. |
| case5 | baseline | treatment_target_mismatch | high | clinical/target | q3, u10, u19, u2 | next visit names #9, but the problem's clinical target is #8. |
| case5 | baseline | quick_note_tooth_unclear | medium | clinical/target | q3 | Quick note q3 mentions #9, which matches neither the complaint location nor the clinical target. |
| case5 | baseline | target_not_assessable | low | technical | u10, u2 | Complaint location 'right front tooth' can't be compared with #8. |
| case5 | team | treatment_target_mismatch | high | clinical/target | q3, u10, u19, u2 | next visit names #9, but the problem's clinical target is #8. |
| case5 | team | unsupported_content | high | technical | u13 | finding it_009: normalization, meaning check fail. |
| case5 | team | open_review_task | medium | technical |  | Open review task (check_failure): assertion: producer 'present' vs checker 'absent'; attributes.response: producer 'absent' vs checker None |
| case5 | team | open_review_task | medium | technical | u10 | Open review task (omission): Co: No pulp exposure on tooth 8: no pink or bleeding seen |
| case5 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth: producer 8 vs checker 9; attributes.recommended_by_clinician: producer True vs checker None; |
| case5 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 8 has no valid spoken_tooth_number derivation |
| case5 | team | open_review_task | medium | technical |  | Open review task (check_failure): time_context: producer 'current' vs checker 'historical' |
| case5 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 8 has no valid spoken_tooth_number derivation |
| case5 | team | quick_note_tooth_unclear | medium | clinical/target | q3 | Quick note q3 mentions #9, which matches neither the complaint location nor the clinical target. |
| case5 | team | radiograph_finding_missing | medium | clinical/target | u13, u15 | Radiograph finding present but not confirmed. |
| case5 | team | unsupported_content | medium | technical | u2 | symptom it_006: meaning check fail. |
| case5 | team | unsupported_content | medium | technical | u17 | option discussed it_001: meaning check fail. |
| case5 | team | target_not_assessable | low | technical | u10, u2 | Complaint location 'right front tooth' can't be compared with #8. |
| case6 | team | unsupported_content | high | technical | u6 | medication it_004: meaning check fail. |
| case6 | team | unsupported_content | high | technical | u17 | referral it_018: meaning check fail. |
| case6 | team | unsupported_content | high | technical | q1, u9 | vital reading it_002: meaning check fail. |
| case6 | team | open_review_task | medium | technical |  | Open review task (check_failure): time_context: producer 'current' vs checker 'historical' |
| case6 | team | open_review_task | medium | technical |  | Open review task (check_failure): time_context: producer 'planned' vs checker 'current' |
| case6 | team | open_review_task | medium | technical |  | Open review task (check_failure): time_context: producer 'current' vs checker 'historical'; attributes.medication_status: producer 'current' |
| case6 | team | open_review_task | medium | technical | u10 | Open review task (omission): Cs window extra: Patient hasn't seen a doctor in a while |
| case6 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 17 has no valid spoken_tooth_number derivation |
| case6 | team | open_review_task | medium | technical |  | Open review task (check_failure): assertion_source: producer 'clinician_observation' vs checker 'assistant_record' |
| case6 | team | unsupported_content | medium | technical | u6 | symptom it_009: meaning check fail. |
| case7 | baseline | open_conflict | high | technical | q3, u7 | contradiction about tooth number of affected tooth is open. |
| case7 | baseline | open_conflict | high | technical | u13, u21 | Unmatched contradiction: self correction about treatment plan: filling vs root canal: no entity covers it |
| case7 | baseline | open_review_task | medium | technical | q2, u5 | Open review task (registry_issue): R2 contradiction about chief complaint side: no entity covers this statement |
| case7 | baseline | open_review_task | medium | technical | u13, u21 | Open review task (omission): R2 self_correction about treatment plan: filling vs root canal: no entity covers this statement |
| case7 | baseline | open_review_task | medium | technical | q3 | Open review task (omission): R2 contradiction about tooth number of affected tooth: no entity covers this statement |
| case7 | baseline | radiograph_finding_missing | medium | clinical/target | u19, u20 | Radiograph performed with no finding documented. |
| case7 | team | open_conflict | high | technical | q3, u7 | contradiction about tooth number of affected tooth is open. |
| case7 | team | unsupported_content | high | technical | u19, u21 | radiograph it_015: meaning check fail. |
| case7 | team | unsupported_content | high | technical | u27 | next visit it_024: meaning check fail. |
| case7 | team | open_conflict | medium | technical | u13, u21 | self correction about treatment plan (filling vs root canal) is open. |
| case7 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth: producer None vs checker 19 |
| case7 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth: producer None vs checker 19; free-text details: producer "a filling won't fix it", checker f |
| case7 | team | open_review_task | medium | technical | q2, u5 | Open review task (registry_issue): R2 contradiction about chief complaint side: no entity covers this statement |
| case7 | team | open_review_task | medium | technical |  | Open review task (check_failure): assertion: producer 'present' vs checker 'absent'; free-text details: uncertain (producer 'Previously on w |
| case7 | team | open_review_task | medium | technical |  | Open review task (check_failure): assertion_source: producer 'clinician_observation' vs checker 'clinician_instruction' |
| case7 | team | open_review_task | medium | technical |  | Open review task (check_failure): target.tooth = 19 has no valid spoken_tooth_number derivation |
| case7 | team | open_review_task | medium | technical | q3 | Open review task (omission): Co: Quick note records tooth #30, which conflicts with tooth 19 identified in the conversation; no entity recor |
| case7 | team | open_review_task | medium | technical |  | Open review task (check_failure): attributes.procedure: different (producer 'crown' vs checker 'root canal'); free-text details: different ( |
| case7 | team | radiograph_finding_missing | medium | clinical/target | u19, u21 | Radiograph finding present but not confirmed. |
| case7 | team | unsupported_content | medium | technical | u11, u12 | history change it_003: meaning check fail. |
| case7 | team | unsupported_content | medium | technical | u23, u25 | option discussed it_001: meaning check fail. |
| case7 | team | unsupported_content | medium | technical | u13, u21 | option discussed it_023: meaning check fail. |
| case8 | baseline | unsupported_content | high | technical | q2, u2 | problem pb_1: normalization check fail. |
| case8 | baseline | open_review_task | medium | technical |  | Open review task (registry_issue): derivation[0] clinical_target.tooth: 'Number twelve' not in evidence[0]; clinical_target.tooth = 12 has n |
| case8 | team | unsupported_content | high | technical | u7, u8 | allergy it_004: meaning check fail. |
| case8 | team | unsupported_content | high | technical | u11, u2 | problem pb_1: meaning check fail. |
| case8 | team | open_review_task | medium | technical |  | Open review task (check_failure): assertion: producer 'possible' vs checker 'present' |
| case8 | team | open_review_task | medium | technical |  | Open review task (registry_issue): free-text details: different (producer 'A piece of my filling broke off on the top left. it hurts when I  |
| case8 | team | open_review_task | medium | technical |  | Open review task (check_failure): time_context: producer 'current' vs checker 'historical' |
| case8 | team | unsupported_content | medium | technical | u3, u4 | symptom it_007: meaning check fail. |
