# Development evaluation v2 (after Cs calibration): baseline vs team

> **Incomplete run — read this first.** The Anthropic account ran out of credit during this run. Three runs (m17_injection/team, m18_two_problems/baseline, m18_two_problems/team) failed with `400: credit balance is too low`. They appear below as candidate-production failures, but they are billing failures, not pipeline failures. Two more runs (m16_no_bp/team, m17_injection/baseline) have no Grader scores for the same reason. All other runs completed normally. Re-run the affected cases once credit is added: `python -m eval.run_eval --cases eval/matrix --only m16_no_bp m17_injection m18_two_problems --pipeline both`.

> Prototype — test data only. Synthetic role-played cases. Gold annotations are **drafts by Claude, not yet checked by a person** (`checked_by` empty), so every number below is provisional until the gold is checked.

Provenance: git `9b5af031dddb5fb197844641b8bb1774b64a6998` (dirty), eval config hash `a3eb2fb63280957b`, schema `9dbe1baa5d0fbe62`, models claude-sonnet-5-5 (grader claude-opus-5-5), rule mode synthetic_demo, text mode.

## Candidate production and workflow

| | baseline | team |
|---|---|---|
| Runs producing a candidate | 20/21 (95%) | 19/21 (90%) |
| Reached ready_for_review | 20/21 (95%) | 19/21 (90%) |
| Dentist approval blocked before human review | 13/20 (65%) | 16/19 (84%) |

Every quality number below is computed over the runs that produced a candidate and is reported with that denominator.

## Extraction quality (final, after automated repair)

| Metric | baseline | team |
|---|---|---|
| Entity precision | 151/162 (93%) across 20 of 21 runs | 152/173 (88%) across 19 of 21 runs |
| Entity recall | 151/161 (94%) across 20 of 21 runs | 152/157 (97%) across 19 of 21 runs |
| Clinical-target accuracy | 20/20 (100%) | 18/19 (95%) |
| Matrix expectations met | 36/37 (97%) | 32/34 (94%) |

### Critical-field accuracy (matched entities)

| Field | baseline | team |
|---|---|---|
| tooth | 75/81 (93%) | 74/87 (85%) |
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
| assertion | 126/128 (98%) | 125/130 (96%) |
| assertion_source | 124/127 (98%) | 122/129 (95%) |
| attr:aspect | 25/31 (81%) | 28/33 (85%) |
| attr:certainty | 9/9 (100%) | 9/9 (100%) |
| attr:complaint_location | 20/20 (100%) | 18/18 (100%) |
| attr:complaint_text | 16/20 (80%) | 15/18 (83%) |
| attr:content | 2/2 (100%) | 2/2 (100%) |
| attr:decision | 7/7 (100%) | 7/7 (100%) |
| attr:description | 2/2 (100%) | 2/2 (100%) |
| attr:diagnosis | 9/9 (100%) | 9/9 (100%) |
| attr:diastolic | 20/20 (100%) | 19/19 (100%) |
| attr:drug | 5/5 (100%) | 5/5 (100%) |
| attr:duration_days | 2/2 (100%) | 2/2 (100%) |
| attr:duration_s | 1/1 (100%) | 1/1 (100%) |
| attr:element | 2/2 (100%) | 2/2 (100%) |
| attr:finding | 3/3 (100%) | 3/3 (100%) |
| attr:frequency_code | 3/3 (100%) | 3/3 (100%) |
| attr:lingering | 7/7 (100%) | 6/6 (100%) |
| attr:observation | 7/8 (88%) | 8/9 (89%) |
| attr:option | 9/9 (100%) | 8/9 (89%) |
| attr:procedure | 7/7 (100%) | 7/7 (100%) |
| attr:reaction | 1/1 (100%) | 1/1 (100%) |
| attr:reason | 1/1 (100%) | 1/1 (100%) |
| attr:recommended_by_clinician | 3/3 (100%) | 2/3 (67%) |
| attr:relation_kind | 3/3 (100%) | 3/3 (100%) |
| attr:response | 18/22 (82%) | 19/22 (86%) |
| attr:result_description | 4/5 (80%) | 2/4 (50%) |
| attr:score | 3/3 (100%) | 3/3 (100%) |
| attr:strength | 3/3 (100%) | 3/3 (100%) |
| attr:substance | 3/3 (100%) | 3/3 (100%) |
| attr:surface | 1/1 (100%) | 1/1 (100%) |
| attr:systolic | 20/20 (100%) | 19/19 (100%) |
| attr:test | 21/21 (100%) | 21/21 (100%) |
| attr:text | 3/3 (100%) | 3/3 (100%) |
| attr:timing | 7/7 (100%) | 7/7 (100%) |
| attr:type | 3/3 (100%) | 3/3 (100%) |
| attr:value | 24/25 (96%) | 27/27 (100%) |
| negation | 7/8 (88%) | 7/7 (100%) |
| role | 20/20 (100%) | 19/19 (100%) |
| status | 8/8 (100%) | 7/8 (88%) |
| target_relation | 50/53 (94%) | 50/54 (93%) |
| time_context | 127/128 (99%) | 128/130 (98%) |
| tooth | 75/81 (93%) | 74/87 (85%) |

### Recall by type (matched / gold; produced)

| Type | baseline | team |
|---|---|---|
| allergy | 3/3; 3 | 3/3; 3 |
| consent_element | 2/3; 3 | 2/3; 4 |
| decision | 7/7; 8 | 7/7; 7 |
| diagnosis | 9/9; 10 | 9/9; 14 |
| finding | 29/31; 31 | 30/30; 31 |
| history_change | 2/2; 3 | 2/2; 4 |
| instruction | 3/6; 4 | 3/6; 4 |
| medication | 2/2; 3 | 2/2; 5 |
| next_visit | 7/7; 7 | 7/7; 7 |
| option_discussed | 6/6; 7 | 6/6; 7 |
| prescription | 3/3; 3 | 3/3; 3 |
| problem | 20/20; 20 | 19/19; 19 |
| radiograph | 4/4; 4 | 4/4; 4 |
| relationship | 3/3; 4 | 3/3; 5 |
| symptom | 31/35; 31 | 33/34; 36 |
| treatment_today | 0/0; 1 | 0/0; 0 |
| vital_reading | 20/20; 20 | 19/19; 20 |

## Stages: raw extraction vs after automated repair

| | baseline raw | baseline repaired | team raw | team repaired |
|---|---|---|---|---|
| Recall | 151/161 (94%) | 151/161 (94%) | 151/157 (96%) | 152/157 (97%) |
| Precision | 151/162 (93%) | 151/162 (93%) | 151/167 (90%) | 152/173 (88%) |
| Tooth accuracy | 75/81 (93%) | 75/81 (93%) | 73/88 (83%) | 74/87 (85%) |

After human review: not yet measured. It needs the review sessions you run yourselves in the UI (at least two cases); `score_session` scores an approved session the same way.

## Flags (E2; E3 review questions counted separately)

| | baseline | team |
|---|---|---|
| caught | 13 | 13 |
| missed | 1 | 0 |
| duplicates | 1 | 0 |
| false alarms | 9 | 47 |
| false alarms clinical | 0 | 3 |
| false alarms technical | 9 | 44 |
| tolerated | 11 | 8 |
| questions | 8 | 6 |

Missed expected flags: m17_injection/baseline: diagnosis_or_plan_missing


`tolerated` = produced flags the draft matrix annotation lists as acceptable (not counted as false alarms); `false alarms` marked *(technical)* are safeguard flags (failed checks, open tasks), not clinical rules.

## Claim support (Grader, rendered attributes)

| Label | baseline | team |
|---|---|---|
| changed_meaning | 13 | 6 |
| supported_by_quick_notes | 38 | 41 |
| supported_by_transcript | 388 | 422 |
| unsupported | 3 | 6 |

## Cost and latency

| | baseline | team |
|---|---|---|
| Model calls | 54 | 408 |
| Extraction + checking cost (USD) | 0.872 | 5.003 |
| Shared stages R2 + E3 (USD) | 0.144 | 0.134 |
| Wall time per run, s (every run) | 30.4, 24.3, 38.4, 10.6, 10.0, 7.3, 15.2, 7.7, 7.4, 13.1, 5.2, 10.4, 8.2, 17.8, 6.5, 6.7, 7.3, 9.4, 12.8, 11.2, 0.2 | 45.2, 56.4, 60.8, 27.2, 24.7, 17.5, 29.0, 24.6, 22.8, 20.6, 24.1, 20.6, 14.2, 33.1, 23.5, 20.5, 21.3, 14.1, 19.9, 0.3, 0.3 |

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
| m17_injection | team | no: B/Br | | | | | | | 0.3 | 0.000 |
| m18_two_problems | baseline | no: B/B0 | | | | | | | 0.2 | 0.000 |
| m18_two_problems | team | no: B/Br | | | | | | | 0.3 | 0.000 |

## Relationship correctness vs flag policy

Team relationships can suppress low target flags only when Cs passes; baseline relationships need a dentist confirmation. Relationship rows per run: m01_control_tooth/baseline: [{'tooth': 3, 'kind': 'control', 'semantic': 'not_applicable'}]; m01_control_tooth/team: [{'tooth': 3, 'kind': 'control', 'semantic': 'fail'}]; m02_treatment_on_control/baseline: [{'tooth': 3, 'kind': 'control', 'semantic': 'not_applicable'}]; m02_treatment_on_control/team: [{'tooth': 3, 'kind': 'control', 'semantic': 'pass'}]; m03_referred_pain/baseline: [{'tooth': 3, 'kind': 'referred_from', 'semantic': 'not_applicable'}]; m03_referred_pain/team: [{'tooth': 3, 'kind': 'referred_from', 'semantic': 'pass'}, {'tooth': 3, 'kind': 'control', 'semantic': 'pass'}]; m06_negation_scope/baseline: [{'tooth': 14, 'kind': 'adjacent_examined', 'semantic': 'not_applicable'}]; m06_negation_scope/team: [{'tooth': 14, 'kind': 'adjacent_examined', 'semantic': 'pass'}]

## What this does and doesn't show

- It compares one single-extractor baseline with one team configuration on the same frozen sources and overlays. It measures split extraction + registry staging + Cs/Ce/Co checks together, not agent teams in general. No ablations yet, so causal claims stay modest.
- 21 small synthetic cases, one run each: counts have wide uncertainty.
- The gold and the Grader are not independent of the system's designer (both drafted by Claude); a person must check the gold, every critical-field grade, and every baseline/team disagreement (see grader_review.csv).
- Audio/ASR quality and human review time are not measured yet.

