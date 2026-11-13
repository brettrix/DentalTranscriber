# Development evaluation (cases 1-3 + edge-case matrix): baseline vs team

> Prototype — test data only. Synthetic role-played cases. Gold annotations are **drafts by Claude, not yet checked by a person** (`checked_by` empty), so every number below is provisional until the gold is checked.

Provenance: git `1038669c5b79914a8d007efaaa2e7a52bc850d4f` (dirty), eval config hash `21027c4801ed8ca1`, schema `ef873209bfd17b3a`, models claude-sonnet-5-5 (grader claude-opus-5-5), rule mode synthetic_demo, text mode.

## Candidate production and workflow

| | baseline | team |
|---|---|---|
| Runs producing a candidate | 21/21 (100%) | 21/21 (100%) |
| Reached ready_for_review | 21/21 (100%) | 21/21 (100%) |
| Dentist approval blocked before human review | 14/21 (67%) | 20/21 (95%) |

Every quality number below is computed over the runs that produced a candidate and is reported with that denominator.

## Extraction quality (final, after automated repair)

| Metric | baseline | team |
|---|---|---|
| Entity precision | 160/170 (94%) across 21 of 21 runs | 168/192 (88%) across 21 of 21 runs |
| Entity recall | 160/171 (94%) across 21 of 21 runs | 168/171 (98%) across 21 of 21 runs |
| Clinical-target accuracy | 22/22 (100%) | 21/22 (95%) |
| Matrix expectations met | 37/38 (97%) | 36/39 (92%) |

### Critical-field accuracy (matched entities)

| Field | baseline | team |
|---|---|---|
| tooth | 77/86 (90%) | 79/94 (84%) |
| relationship | 3/3 (100%) | 3/3 (100%) |
| drug | 5/5 (100%) | 5/5 (100%) |
| dose | 3/3 (100%) | 3/3 (100%) |
| negation | 7/8 (88%) | 8/8 (100%) |
| certainty | 9/9 (100%) | 9/9 (100%) |
| decision | 7/7 (100%) | 7/7 (100%) |
| allergy_status | 3/3 (100%) | 3/3 (100%) |
| medication_status | 2/2 (100%) | 2/2 (100%) |

### Per-dimension accuracy (matched entities)

| Dimension | baseline | team |
|---|---|---|
| action | 4/4 (100%) | 4/4 (100%) |
| assertion | 132/135 (98%) | 141/143 (99%) |
| assertion_source | 131/134 (98%) | 134/142 (94%) |
| attr:aspect | 28/34 (82%) | 31/37 (84%) |
| attr:certainty | 9/9 (100%) | 9/9 (100%) |
| attr:complaint_location | 22/22 (100%) | 22/22 (100%) |
| attr:complaint_text | 19/22 (86%) | 16/22 (73%) |
| attr:content | 2/2 (100%) | 2/2 (100%) |
| attr:decision | 7/7 (100%) | 7/7 (100%) |
| attr:description | 2/2 (100%) | 2/2 (100%) |
| attr:diagnosis | 9/9 (100%) | 8/9 (89%) |
| attr:diastolic | 21/21 (100%) | 21/21 (100%) |
| attr:drug | 5/5 (100%) | 5/5 (100%) |
| attr:duration_days | 2/2 (100%) | 2/2 (100%) |
| attr:duration_s | 1/1 (100%) | 1/1 (100%) |
| attr:element | 2/2 (100%) | 2/2 (100%) |
| attr:finding | 3/3 (100%) | 3/3 (100%) |
| attr:frequency_code | 3/3 (100%) | 3/3 (100%) |
| attr:lingering | 7/7 (100%) | 7/7 (100%) |
| attr:observation | 9/10 (90%) | 10/11 (91%) |
| attr:option | 8/9 (89%) | 10/11 (91%) |
| attr:procedure | 7/7 (100%) | 7/7 (100%) |
| attr:reaction | 1/1 (100%) | 1/1 (100%) |
| attr:reason | 1/1 (100%) | 1/1 (100%) |
| attr:recommended_by_clinician | 3/3 (100%) | 2/3 (67%) |
| attr:relation_kind | 3/3 (100%) | 3/3 (100%) |
| attr:response | 20/23 (87%) | 21/24 (88%) |
| attr:result_description | 4/5 (80%) | 4/5 (80%) |
| attr:score | 3/3 (100%) | 3/3 (100%) |
| attr:strength | 3/3 (100%) | 3/3 (100%) |
| attr:substance | 3/3 (100%) | 3/3 (100%) |
| attr:surface | 1/1 (100%) | 1/1 (100%) |
| attr:systolic | 21/21 (100%) | 21/21 (100%) |
| attr:test | 22/22 (100%) | 23/23 (100%) |
| attr:text | 3/3 (100%) | 3/4 (75%) |
| attr:timing | 7/7 (100%) | 7/7 (100%) |
| attr:type | 3/3 (100%) | 3/3 (100%) |
| attr:value | 27/28 (96%) | 30/31 (97%) |
| negation | 7/8 (88%) | 8/8 (100%) |
| role | 22/22 (100%) | 22/22 (100%) |
| status | 8/8 (100%) | 8/8 (100%) |
| target_relation | 50/56 (89%) | 50/60 (83%) |
| time_context | 134/135 (99%) | 140/143 (98%) |
| tooth | 77/86 (90%) | 79/94 (84%) |

### Recall by type (matched / gold; produced)

| Type | baseline | team |
|---|---|---|
| allergy | 3/3; 3 | 3/3; 3 |
| consent_element | 2/3; 2 | 2/3; 3 |
| decision | 7/7; 8 | 7/7; 8 |
| diagnosis | 9/9; 11 | 9/9; 16 |
| finding | 32/34; 33 | 34/34; 35 |
| history_change | 2/2; 3 | 2/2; 4 |
| instruction | 3/6; 3 | 4/6; 5 |
| medication | 2/2; 3 | 2/2; 5 |
| next_visit | 7/7; 7 | 7/7; 7 |
| option_discussed | 6/8; 7 | 8/8; 10 |
| prescription | 3/3; 3 | 3/3; 3 |
| problem | 22/22; 22 | 22/22; 22 |
| radiograph | 4/4; 4 | 4/4; 4 |
| relationship | 3/3; 4 | 3/3; 5 |
| symptom | 34/37; 34 | 37/37; 41 |
| treatment_today | 0/0; 2 | 0/0; 0 |
| vital_reading | 21/21; 21 | 21/21; 21 |

## Stages: raw extraction vs after automated repair

| | baseline raw | baseline repaired | team raw | team repaired |
|---|---|---|---|---|
| Recall | 160/171 (94%) | 160/171 (94%) | 166/171 (97%) | 168/171 (98%) |
| Precision | 160/170 (94%) | 160/170 (94%) | 166/187 (89%) | 168/192 (88%) |
| Tooth accuracy | 77/87 (89%) | 77/86 (90%) | 82/96 (85%) | 79/94 (84%) |

After human review: not yet measured. It needs the review sessions you run yourselves in the UI (at least two cases); `score_session` scores an approved session the same way.

## Flags (E2; E3 review questions counted separately)

| | baseline | team |
|---|---|---|
| caught | 14 | 14 |
| missed | 1 | 1 |
| duplicates | 0 | 0 |
| false alarms | 11 | 73 |
| tolerated | 11 | 6 |
| questions | 8 | 7 |

`tolerated` = produced flags the draft matrix annotation lists as acceptable (not counted as false alarms); `false alarms` marked *(technical)* are safeguard flags (failed checks, open tasks), not clinical rules.

## Claim support (Grader, rendered attributes)

| Label | baseline | team |
|---|---|---|
| changed_meaning | 10 | 9 |
| supported_by_quick_notes | 42 | 43 |
| supported_by_transcript | 422 | 484 |
| unsupported | 3 | 4 |

## Cost and latency

| | baseline | team |
|---|---|---|
| Model calls | 56 | 474 |
| Extraction + checking cost (USD) | 0.890 | 5.856 |
| Shared stages R2 + E3 (USD) | 0.148 | 0.148 |
| Wall time per run, s (every run) | 30.8, 21.6, 29.7, 11.3, 9.7, 8.0, 8.4, 8.2, 7.1, 12.9, 5.8, 10.4, 7.8, 18.4, 6.5, 10.2, 6.7, 8.8, 16.9, 8.1, 10.2 | 54.8, 58.0, 58.4, 16.4, 28.8, 23.4, 21.4, 22.6, 24.4, 20.2, 19.3, 22.9, 14.6, 32.9, 22.5, 21.2, 21.6, 14.1, 31.1, 26.6, 30.8 |

Latencies are single runs at one session at a time; percentiles would be exploratory and are not given.

## Per-run rows

| Case | Pipeline | Candidate | Recall | Precision | Tooth | Flags caught/missed/false | Expectations | Forbidden | Wall s | USD |
|---|---|---|---|---|---|---|---|---|---|---|
| case1 | baseline | yes | 22/23 (96%) | 22/22 (100%) | 9/9 (100%) | 0/0/0 | 0/0 | — | 30.8 | 0.110 |
| case1 | team | yes | 22/23 (96%) | 22/23 (96%) | 9/11 (82%) | 0/0/6 | 0/0 | — | 54.8 | 0.593 |
| case2 | baseline | yes | 17/20 (85%) | 17/18 (94%) | 7/7 (100%) | 0/0/0 | 0/0 | — | 21.6 | 0.084 |
| case2 | team | yes | 19/20 (95%) | 19/24 (79%) | 8/10 (80%) | 0/0/11 | 0/0 | — | 58.0 | 0.635 |
| case3 | baseline | yes | 24/25 (96%) | 24/24 (100%) | 8/11 (73%) | 1/0/0 | 0/0 | — | 29.7 | 0.102 |
| case3 | team | yes | 24/25 (96%) | 24/27 (89%) | 7/11 (64%) | 1/0/22 | 0/0 | — | 58.4 | 0.683 |
| m01_control_tooth | baseline | yes | 7/7 (100%) | 7/7 (100%) | 5/5 (100%) | 0/0/2 | 2/2 | — | 11.3 | 0.043 |
| m01_control_tooth | team | yes | 7/7 (100%) | 7/7 (100%) | 5/5 (100%) | 0/0/3 | 2/3 | — | 16.4 | 0.182 |
| m02_treatment_on_control | baseline | yes | 7/7 (100%) | 7/7 (100%) | 5/5 (100%) | 1/0/2 | 1/1 | — | 9.7 | 0.037 |
| m02_treatment_on_control | team | yes | 7/7 (100%) | 7/7 (100%) | 4/5 (80%) | 0/1/5 | 0/1 | — | 28.8 | 0.221 |
| m03_referred_pain | baseline | yes | 5/6 (83%) | 5/6 (83%) | 4/4 (100%) | 0/0/0 | 3/3 | — | 8.0 | 0.035 |
| m03_referred_pain | team | yes | 6/6 (100%) | 6/8 (75%) | 4/4 (100%) | 0/0/4 | 3/3 | — | 23.4 | 0.220 |
| m04_self_correction | baseline | yes | 5/5 (100%) | 5/5 (100%) | 2/3 (67%) | 0/0/1 | 1/1 | — | 8.4 | 0.033 |
| m04_self_correction | team | yes | 5/5 (100%) | 5/6 (83%) | 2/3 (67%) | 0/0/3 | 1/1 | — | 21.4 | 0.222 |
| m05_dx8_tx9 | baseline | yes | 6/6 (100%) | 6/6 (100%) | 4/4 (100%) | 2/0/2 | 1/1 | — | 8.2 | 0.034 |
| m05_dx8_tx9 | team | yes | 6/6 (100%) | 6/6 (100%) | 4/4 (100%) | 2/0/2 | 1/1 | — | 22.6 | 0.214 |
| m06_negation_scope | baseline | yes | 4/5 (80%) | 4/5 (80%) | 3/3 (100%) | 1/0/2 | 4/4 | — | 7.1 | 0.031 |
| m06_negation_scope | team | yes | 5/5 (100%) | 5/7 (71%) | 3/3 (100%) | 1/0/6 | 4/4 | — | 24.4 | 0.230 |
| m07_tentative_dx | baseline | yes | 6/6 (100%) | 6/6 (100%) | 3/4 (75%) | 0/0/0 | 2/2 | — | 12.9 | 0.056 |
| m07_tentative_dx | team | yes | 6/6 (100%) | 6/6 (100%) | 3/4 (75%) | 0/0/0 | 2/2 | — | 20.2 | 0.211 |
| m08_discontinued_med | baseline | yes | 4/4 (100%) | 4/4 (100%) | — | 2/0/0 | 2/2 | — | 5.8 | 0.030 |
| m08_discontinued_med | team | yes | 4/4 (100%) | 4/5 (80%) | — | 2/0/0 | 2/2 | — | 19.3 | 0.196 |
| m09_resolved_allergy_rx | baseline | yes | 5/5 (100%) | 5/6 (83%) | 2/2 (100%) | 1/0/0 | 1/1 | — | 10.4 | 0.041 |
| m09_resolved_allergy_rx | team | yes | 5/5 (100%) | 5/6 (83%) | 2/3 (67%) | 1/0/0 | 1/1 | — | 22.9 | 0.228 |
| m10_conflicting_qn_bp | baseline | yes | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 1/0/0 | 2/2 | — | 7.8 | 0.033 |
| m10_conflicting_qn_bp | team | yes | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 1/0/0 | 2/2 | — | 14.6 | 0.148 |
| m11_wait_and_see | baseline | yes | 7/7 (100%) | 7/9 (78%) | 4/5 (80%) | 0/0/0 | 3/3 | — | 18.4 | 0.072 |
| m11_wait_and_see | team | yes | 7/7 (100%) | 7/9 (78%) | 4/5 (80%) | 0/0/3 | 3/3 | — | 32.9 | 0.331 |
| m12_no_xray_needed | baseline | yes | 5/6 (83%) | 5/5 (100%) | 3/3 (100%) | 0/0/0 | 2/2 | — | 6.5 | 0.030 |
| m12_no_xray_needed | team | yes | 6/6 (100%) | 6/7 (86%) | 3/3 (100%) | 0/0/0 | 2/2 | — | 22.5 | 0.225 |
| m13_monitor_no_option | baseline | yes | 5/5 (100%) | 5/5 (100%) | 2/3 (67%) | 1/0/0 | 3/3 | — | 10.2 | 0.050 |
| m13_monitor_no_option | team | yes | 5/5 (100%) | 5/5 (100%) | 2/3 (67%) | 1/0/0 | 3/3 | — | 21.2 | 0.197 |
| m14_patient_belief | baseline | yes | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 1/0/0 | 2/3 | — | 6.7 | 0.031 |
| m14_patient_belief | team | yes | 5/5 (100%) | 5/5 (100%) | 2/2 (100%) | 1/0/0 | 2/3 | — | 21.6 | 0.216 |
| m15_two_dentist_ids | baseline | yes | 4/5 (80%) | 4/4 (100%) | 2/3 (67%) | 0/0/0 | 2/2 | — | 8.8 | 0.036 |
| m15_two_dentist_ids | team | yes | 5/5 (100%) | 5/5 (100%) | 3/3 (100%) | 0/0/0 | 2/2 | — | 14.1 | 0.161 |
| m16_no_bp | baseline | yes | 5/5 (100%) | 5/5 (100%) | 3/4 (75%) | 2/0/0 | 1/1 | — | 16.9 | 0.078 |
| m16_no_bp | team | yes | 5/5 (100%) | 5/6 (83%) | 3/4 (75%) | 2/0/1 | 1/1 | — | 31.1 | 0.305 |
| m17_injection | baseline | yes | 4/4 (100%) | 4/6 (67%) | 2/2 (100%) | 0/1/2 | 4/4 | — | 8.1 | 0.033 |
| m17_injection | team | yes | 4/4 (100%) | 4/6 (67%) | 2/2 (100%) | 1/0/2 | 4/4 | — | 26.6 | 0.281 |
| m18_two_problems | baseline | yes | 8/10 (80%) | 8/10 (80%) | 5/5 (100%) | 1/0/0 | 1/1 | — | 10.2 | 0.040 |
| m18_two_problems | team | yes | 10/10 (100%) | 10/12 (83%) | 7/7 (100%) | 1/0/5 | 1/1 | — | 30.8 | 0.303 |

## Relationship correctness vs flag policy

Team relationships can suppress low target flags only when Cs passes; baseline relationships need a dentist confirmation. Relationship rows per run: m01_control_tooth/baseline: [{'tooth': 3, 'kind': 'control', 'semantic': 'not_applicable'}]; m01_control_tooth/team: [{'tooth': 3, 'kind': 'control', 'semantic': 'fail'}]; m02_treatment_on_control/baseline: [{'tooth': 3, 'kind': 'control', 'semantic': 'not_applicable'}]; m02_treatment_on_control/team: [{'tooth': 3, 'kind': 'control', 'semantic': 'fail'}]; m03_referred_pain/baseline: [{'tooth': 3, 'kind': 'referred_from', 'semantic': 'not_applicable'}]; m03_referred_pain/team: [{'tooth': 3, 'kind': 'referred_from', 'semantic': 'pass'}, {'tooth': 3, 'kind': 'control', 'semantic': 'pass'}]; m06_negation_scope/baseline: [{'tooth': 14, 'kind': 'adjacent_examined', 'semantic': 'not_applicable'}]; m06_negation_scope/team: [{'tooth': 14, 'kind': 'adjacent_examined', 'semantic': 'pass'}]

## What this does and doesn't show

- It compares one single-extractor baseline with one team configuration on the same frozen sources and overlays. It measures split extraction + registry staging + Cs/Ce/Co checks together, not agent teams in general. No ablations yet, so causal claims stay modest.
- 21 small synthetic cases, one run each: counts have wide uncertainty.
- The gold and the Grader are not independent of the system's designer (both drafted by Claude); a person must check the gold, every critical-field grade, and every baseline/team disagreement (see grader_review.csv).
- Audio/ASR quality and human review time are not measured yet.

