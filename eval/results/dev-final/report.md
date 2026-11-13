# Final development evaluation (cases 1-3 + edge-case matrix): baseline vs team

> Merged report: dev-v2, with m17_injection/team and m18_two_problems (both modes) re-run in `dev-v2-patch` after the credit outage, and Grader scores added for m16_no_bp/team and m17_injection/baseline in `dev-v2-rescore`. All other rows are unchanged dev-v2 runs.

> Prototype — test data only. Synthetic role-played cases. Gold annotations are **drafts by Claude, not yet checked by a person** (`checked_by` empty), so every number below is provisional until the gold is checked.

Provenance: git `9b5af031dddb5fb197844641b8bb1774b64a6998` (dirty), eval config hash `a3eb2fb63280957b`, schema `9dbe1baa5d0fbe62`, models claude-sonnet-5-5 (grader claude-opus-5-5), rule mode synthetic_demo, text mode.

## Candidate production and workflow

| | baseline | team |
|---|---|---|
| Runs producing a candidate | 21/21 (100%) | 21/21 (100%) |
| Reached ready_for_review | 21/21 (100%) | 21/21 (100%) |
| Dentist approval blocked before human review | 13/21 (62%) | 18/21 (86%) |

Every quality number below is computed over the runs that produced a candidate and is reported with that denominator.

## Extraction quality (final, after automated repair)

| Metric | baseline | team |
|---|---|---|
| Entity precision | 159/172 (92%) across 21 of 21 runs | 166/192 (86%) across 21 of 21 runs |
| Entity recall | 159/171 (93%) across 21 of 21 runs | 166/171 (97%) across 21 of 21 runs |
| Clinical-target accuracy | 22/22 (100%) | 21/22 (95%) |
| Matrix expectations met | 37/38 (97%) | 37/39 (95%) |

### Critical-field accuracy (matched entities)

| Field | baseline | team |
|---|---|---|
| tooth | 80/86 (93%) | 83/96 (86%) |
| relationship | 3/3 (100%) | 3/3 (100%) |
| drug | 5/5 (100%) | 5/5 (100%) |
| dose | 3/3 (100%) | 3/3 (100%) |
| negation | 7/8 (88%) | 7/7 (100%) |
| certainty | 9/9 (100%) | 9/9 (100%) |
| decision | 7/7 (100%) | 7/7 (100%) |
| allergy_status | 3/3 (100%) | 3/3 (100%) |
| medication_status | 2/2 (100%) | 2/2 (100%) |

### Per-dimension accuracy (matched entities)

| Dimension | baseline | team |
|---|---|---|
| action | 4/4 (100%) | 4/4 (100%) |
| assertion | 132/134 (99%) | 136/141 (96%) |
| assertion_source | 130/133 (98%) | 133/140 (95%) |
| attr:aspect | 27/33 (82%) | 30/36 (83%) |
| attr:certainty | 9/9 (100%) | 9/9 (100%) |
| attr:complaint_location | 22/22 (100%) | 22/22 (100%) |
| attr:complaint_text | 18/22 (82%) | 19/22 (86%) |
| attr:content | 2/2 (100%) | 2/2 (100%) |
| attr:decision | 7/7 (100%) | 7/7 (100%) |
| attr:description | 2/2 (100%) | 2/2 (100%) |
| attr:diagnosis | 9/9 (100%) | 9/9 (100%) |
| attr:diastolic | 21/21 (100%) | 21/21 (100%) |
| attr:drug | 5/5 (100%) | 5/5 (100%) |
| attr:duration_days | 2/2 (100%) | 2/2 (100%) |
| attr:duration_s | 1/1 (100%) | 1/1 (100%) |
| attr:element | 2/2 (100%) | 2/2 (100%) |
| attr:finding | 3/3 (100%) | 3/3 (100%) |
| attr:frequency_code | 3/3 (100%) | 3/3 (100%) |
| attr:lingering | 7/7 (100%) | 7/7 (100%) |
| attr:observation | 9/10 (90%) | 10/11 (91%) |
| attr:option | 9/9 (100%) | 10/11 (91%) |
| attr:procedure | 7/7 (100%) | 7/7 (100%) |
| attr:reaction | 1/1 (100%) | 1/1 (100%) |
| attr:reason | 1/1 (100%) | 1/1 (100%) |
| attr:recommended_by_clinician | 3/3 (100%) | 2/3 (67%) |
| attr:relation_kind | 3/3 (100%) | 3/3 (100%) |
| attr:response | 19/23 (83%) | 21/24 (88%) |
| attr:result_description | 4/5 (80%) | 3/5 (60%) |
| attr:score | 3/3 (100%) | 3/3 (100%) |
| attr:strength | 3/3 (100%) | 3/3 (100%) |
| attr:substance | 3/3 (100%) | 3/3 (100%) |
| attr:surface | 1/1 (100%) | 1/1 (100%) |
| attr:systolic | 21/21 (100%) | 21/21 (100%) |
| attr:test | 22/22 (100%) | 23/23 (100%) |
| attr:text | 3/3 (100%) | 3/3 (100%) |
| attr:timing | 7/7 (100%) | 7/7 (100%) |
| attr:type | 3/3 (100%) | 3/3 (100%) |
| attr:value | 26/27 (96%) | 30/30 (100%) |
| negation | 7/8 (88%) | 7/7 (100%) |
| role | 22/22 (100%) | 22/22 (100%) |
| status | 8/8 (100%) | 7/8 (88%) |
| target_relation | 53/56 (95%) | 56/60 (93%) |
| time_context | 133/134 (99%) | 139/141 (99%) |
| tooth | 80/86 (93%) | 83/96 (86%) |

### Recall by type (matched / gold; produced)

| Type | baseline | team |
|---|---|---|
| allergy | 3/3; 3 | 3/3; 3 |
| consent_element | 2/3; 3 | 2/3; 4 |
| decision | 7/7; 8 | 7/7; 8 |
| diagnosis | 9/9; 10 | 9/9; 16 |
| finding | 32/34; 34 | 34/34; 36 |
| history_change | 2/2; 3 | 2/2; 4 |
| instruction | 3/6; 4 | 3/6; 4 |
| medication | 2/2; 3 | 2/2; 5 |
| next_visit | 7/7; 7 | 7/7; 7 |
| option_discussed | 6/8; 7 | 8/8; 9 |
| prescription | 3/3; 3 | 3/3; 3 |
| problem | 22/22; 22 | 22/22; 22 |
| radiograph | 4/4; 4 | 4/4; 4 |
| relationship | 3/3; 4 | 3/3; 5 |
| symptom | 33/37; 33 | 36/37; 40 |
| treatment_today | 0/0; 3 | 0/0; 0 |
| vital_reading | 21/21; 21 | 21/21; 22 |

## Stages: raw extraction vs after automated repair

| | baseline raw | baseline repaired | team raw | team repaired |
|---|---|---|---|---|
| Recall | 159/171 (93%) | 159/171 (93%) | 165/171 (96%) | 166/171 (97%) |
| Precision | 159/172 (92%) | 159/172 (92%) | 165/185 (89%) | 166/192 (86%) |
| Tooth accuracy | 80/86 (93%) | 80/86 (93%) | 82/97 (85%) | 83/96 (86%) |

After human review: not yet measured. It needs the review sessions you run yourselves in the UI (at least two cases); `score_session` scores an approved session the same way.

## Flags (E2; E3 review questions counted separately)

| | baseline | team |
|---|---|---|
| caught | 14 | 14 |
| missed | 1 | 1 |
| duplicates | 1 | 0 |
| false alarms | 9 | 58 |
| false alarms clinical | 0 | 3 |
| false alarms technical | 9 | 55 |
| tolerated | 11 | 10 |
| questions | 8 | 6 |

Missed expected flags: m17_injection/baseline: diagnosis_or_plan_missing; m18_two_problems/team: diagnosis_or_plan_missing


`tolerated` = produced flags the draft matrix annotation lists as acceptable (not counted as false alarms); `false alarms` marked *(technical)* are safeguard flags (failed checks, open tasks), not clinical rules.

## Claim support (Grader, rendered attributes)

| Label | baseline | team |
|---|---|---|
| changed_meaning | 14 | 7 |
| supported_by_quick_notes | 42 | 45 |
| supported_by_transcript | 427 | 488 |
| unsupported | 3 | 6 |

## Cost and latency

| | baseline | team |
|---|---|---|
| Model calls | 56 | 459 |
| Extraction + checking cost (USD) | 0.907 | 5.649 |
| Shared stages R2 + E3 (USD) | 0.148 | 0.144 |
| Wall time per run, s (every run) | 30.4, 24.3, 38.4, 10.6, 10.0, 7.3, 15.2, 7.7, 7.4, 13.1, 5.2, 10.4, 8.2, 17.8, 6.5, 6.7, 7.3, 9.4, 12.8, 11.2, 10.8 | 45.2, 56.4, 60.8, 27.2, 24.7, 17.5, 29.0, 24.6, 22.8, 20.6, 24.1, 20.6, 14.2, 33.1, 23.5, 20.5, 21.3, 14.1, 19.9, 24.8, 36.0 |

Latencies are single runs at one session at a time; percentiles would be exploratory and are not given.

## Per-run rows

| Case | Pipeline | Candidate | Recall | Precision | Tooth | Flags caught/missed/false | Expectations | Forbidden | Wall s | USD |
|---|---|---|---|---|---|---|---|---|---|---|
| case1 | baseline | yes | 22/23 (96%) | 22/22 (100%) | 9/9 (100%) | 0/0/0 | 0/0 | — | 30.4 | 0.109 |
| case1 | team | yes | 22/23 (96%) | 22/23 (96%) | 9/12 (75%) | 0/0/0 | 0/0 | — | 45.2 | 0.539 |
| case2 | baseline | yes | 17/20 (85%) | 17/20 (85%) | 7/7 (100%) | 0/0/0 | 0/0 | — | 24.3 | 0.091 |
| case2 | team | yes | 18/20 (90%) | 18/23 (78%) | 8/10 (80%) | 0/0/10 | 0/0 | — | 56.4 | 0.611 |
| case3 | baseline | yes | 24/25 (96%) | 24/24 (100%) | 11/12 (92%) | 1/0/0 | 0/0 | — | 38.4 | 0.125 |
| case3 | team | yes | 23/25 (92%) | 23/25 (92%) | 11/11 (100%) | 1/0/12 | 0/0 | — | 60.8 | 0.618 |
| m01_control_tooth | baseline | yes | 7/7 (100%) | 7/7 (100%) | 5/5 (100%) | 0/0/0 | 2/2 | — | 10.6 | 0.041 |
| m01_control_tooth | team | yes | 7/7 (100%) | 7/8 (88%) | 5/5 (100%) | 0/0/3 | 2/3 | — | 27.2 | 0.224 |
| m02_treatment_on_control | baseline | yes | 7/7 (100%) | 7/8 (88%) | 5/5 (100%) | 1/0/2 | 1/1 | — | 10.0 | 0.037 |
| m02_treatment_on_control | team | yes | 7/7 (100%) | 7/7 (100%) | 4/5 (80%) | 1/0/1 | 1/1 | — | 24.7 | 0.212 |
| m03_referred_pain | baseline | yes | 5/6 (83%) | 5/6 (83%) | 4/4 (100%) | 0/0/2 | 3/3 | — | 7.3 | 0.033 |
| m03_referred_pain | team | yes | 6/6 (100%) | 6/8 (75%) | 4/5 (80%) | 0/0/0 | 3/3 | — | 17.5 | 0.184 |
| m04_self_correction | baseline | yes | 5/5 (100%) | 5/5 (100%) | 2/3 (67%) | 0/0/1 | 1/1 | — | 15.2 | 0.054 |
| m04_self_correction | team | yes | 5/5 (100%) | 5/6 (83%) | 2/3 (67%) | 0/0/1 | 1/1 | — | 29.0 | 0.262 |
| m05_dx8_tx9 | baseline | yes | 5/6 (83%) | 5/5 (100%) | 4/4 (100%) | 2/0/2 | 1/1 | — | 7.7 | 0.033 |
| m05_dx8_tx9 | team | yes | 6/6 (100%) | 6/6 (100%) | 4/4 (100%) | 2/0/2 | 1/1 | — | 24.6 | 0.220 |
| m06_negation_scope | baseline | yes | 4/5 (80%) | 4/5 (80%) | 3/3 (100%) | 1/0/0 | 4/4 | — | 7.4 | 0.032 |
| m06_negation_scope | team | yes | 5/5 (100%) | 5/6 (83%) | 3/3 (100%) | 1/0/2 | 4/4 | — | 22.8 | 0.199 |
| m07_tentative_dx | baseline | yes | 6/6 (100%) | 6/6 (100%) | 3/4 (75%) | 0/0/0 | 2/2 | — | 13.1 | 0.052 |
| m07_tentative_dx | team | yes | 6/6 (100%) | 6/6 (100%) | 3/4 (75%) | 0/0/0 | 2/2 | — | 20.6 | 0.212 |
| m08_discontinued_med | baseline | yes | 4/4 (100%) | 4/4 (100%) | — | 2/0/0 | 2/2 | — | 5.2 | 0.029 |
| m08_discontinued_med | team | yes | 4/4 (100%) | 4/7 (57%) | — | 2/0/0 | 2/2 | — | 24.1 | 0.174 |
| m09_resolved_allergy_rx | baseline | yes | 5/5 (100%) | 5/6 (83%) | 2/2 (100%) | 1/0/0 | 1/1 | — | 10.4 | 0.041 |
| m09_resolved_allergy_rx | team | yes | 5/5 (100%) | 5/5 (100%) | 2/3 (67%) | 1/0/1 | 1/1 | — | 20.6 | 0.195 |
| m10_conflicting_qn_bp | baseline | yes | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 1/0/0 | 2/2 | — | 8.2 | 0.034 |
| m10_conflicting_qn_bp | team | yes | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 1/0/0 | 2/2 | — | 14.2 | 0.148 |
| m11_wait_and_see | baseline | yes | 7/7 (100%) | 7/9 (78%) | 4/5 (80%) | 0/0/0 | 3/3 | — | 17.8 | 0.069 |
| m11_wait_and_see | team | yes | 7/7 (100%) | 7/9 (78%) | 4/5 (80%) | 0/0/6 | 3/3 | — | 33.1 | 0.309 |
| m12_no_xray_needed | baseline | yes | 5/6 (83%) | 5/5 (100%) | 3/3 (100%) | 0/0/0 | 2/2 | — | 6.5 | 0.030 |
| m12_no_xray_needed | team | yes | 6/6 (100%) | 6/7 (86%) | 3/3 (100%) | 0/0/0 | 2/2 | — | 23.5 | 0.228 |
| m13_monitor_no_option | baseline | yes | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 1/0/0 | 3/3 | — | 6.7 | 0.031 |
| m13_monitor_no_option | team | yes | 5/5 (100%) | 5/5 (100%) | 2/3 (67%) | 1/0/0 | 3/3 | — | 20.5 | 0.197 |
| m14_patient_belief | baseline | yes | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 1/0/0 | 2/3 | — | 7.3 | 0.033 |
| m14_patient_belief | team | yes | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 1/0/0 | 2/3 | — | 21.3 | 0.216 |
| m15_two_dentist_ids | baseline | yes | 4/5 (80%) | 4/4 (100%) | 2/3 (67%) | 0/0/0 | 2/2 | — | 9.4 | 0.036 |
| m15_two_dentist_ids | team | yes | 5/5 (100%) | 5/5 (100%) | 3/3 (100%) | 0/0/0 | 2/2 | — | 14.1 | 0.161 |
| m16_no_bp | baseline | yes | 5/5 (100%) | 5/5 (100%) | 3/4 (75%) | 2/0/0 | 1/1 | — | 12.8 | 0.055 |
| m16_no_bp | team | yes | 5/5 (100%) | 5/7 (71%) | 3/4 (75%) | 2/0/9 | 1/1 | — | 19.9 | 0.228 |
| m17_injection | baseline | yes | 4/4 (100%) | 4/6 (67%) | 2/2 (100%) | 0/1/2 | 4/4 | — | 11.2 | 0.052 |
| m17_injection | team | yes | 4/4 (100%) | 4/6 (67%) | 2/2 (100%) | 1/0/2 | 4/4 | — | 24.8 | 0.286 |
| m18_two_problems | baseline | yes | 8/10 (80%) | 8/10 (80%) | 5/5 (100%) | 1/0/0 | 1/1 | — | 10.8 | 0.040 |
| m18_two_problems | team | yes | 10/10 (100%) | 10/13 (77%) | 7/7 (100%) | 0/1/9 | 1/1 | — | 36.0 | 0.369 |

## Relationship correctness vs flag policy

Team relationships can suppress low target flags only when Cs passes; baseline relationships need a dentist confirmation. Relationship rows per run: m01_control_tooth/baseline: [{'tooth': 3, 'kind': 'control', 'semantic': 'not_applicable'}]; m01_control_tooth/team: [{'tooth': 3, 'kind': 'control', 'semantic': 'fail'}]; m02_treatment_on_control/baseline: [{'tooth': 3, 'kind': 'control', 'semantic': 'not_applicable'}]; m02_treatment_on_control/team: [{'tooth': 3, 'kind': 'control', 'semantic': 'pass'}]; m03_referred_pain/baseline: [{'tooth': 3, 'kind': 'referred_from', 'semantic': 'not_applicable'}]; m03_referred_pain/team: [{'tooth': 3, 'kind': 'referred_from', 'semantic': 'pass'}, {'tooth': 3, 'kind': 'control', 'semantic': 'pass'}]; m06_negation_scope/baseline: [{'tooth': 14, 'kind': 'adjacent_examined', 'semantic': 'not_applicable'}]; m06_negation_scope/team: [{'tooth': 14, 'kind': 'adjacent_examined', 'semantic': 'pass'}]

## What this does and doesn't show

- It compares one single-extractor baseline with one team configuration on the same frozen sources and overlays. It measures split extraction + registry staging + Cs/Ce/Co checks together, not agent teams in general. No ablations yet, so causal claims stay modest.
- 21 small synthetic cases, one run each: counts have wide uncertainty.
- The gold and the Grader are not independent of the system's designer (both drafted by Claude); a person must check the gold, every critical-field grade, and every baseline/team disagreement (see grader_review.csv).
- Audio/ASR quality and human review time are not measured yet.

