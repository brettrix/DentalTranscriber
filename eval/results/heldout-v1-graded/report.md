# Held-out evaluation (cases 4-8), graded: run once on frozen config 0e83966b3288c14e

> **Read first.** Held-out pipeline run once (`heldout-v1`) on frozen config `0e83966b3288c14e`, then graded here with the frozen Opus Grader, with no pipeline re-run. Gold was drafted by Sonnet (`eval/tools/draft_gold.py`) and reviewed and corrected by a Claude chat assistant that wrote the answer keys, **not by an independent person** (see `checked_by`; drafts are in `eval/gold/_drafts_before_review/`). The review added two expected flags to case 5 (`open_conflict`, `treatment_target_mismatch`) that the answer key doesn't list; both match flags the system raised in the earlier informal read-out. Cases 7–8 were written by Claude in place of a teammate's cases. The system, the answer keys, the gold review and the Grader are all Claude, so treat every number as provisional.

> Prototype — test data only. Synthetic role-played cases. Gold annotations are **drafts by Claude, not yet checked by a person** (`checked_by` empty), so every number below is provisional until the gold is checked.

Provenance: git `d844e5ca6ab8efac9a7a7bfd3623d79edba2e6db`, eval config hash `0e83966b3288c14e`, schema `9dbe1baa5d0fbe62`, models claude-sonnet-5-5 (grader claude-opus-5-5), rule mode synthetic_demo, text mode.

## Candidate production and workflow

| | baseline | team |
|---|---|---|
| Runs producing a candidate | 5/5 (100%) | 5/5 (100%) |
| Reached ready_for_review | 5/5 (100%) | 5/5 (100%) |
| Dentist approval blocked before human review | 5/5 (100%) | 5/5 (100%) |

Every quality number below is computed over the runs that produced a candidate and is reported with that denominator.

## Extraction quality (final, after automated repair)

| Metric | baseline | team |
|---|---|---|
| Entity precision | 85/88 (97%) across 5 of 5 runs | 88/111 (79%) across 5 of 5 runs |
| Entity recall | 85/96 (89%) across 5 of 5 runs | 88/96 (92%) across 5 of 5 runs |
| Clinical-target accuracy | 5/5 (100%) | 5/5 (100%) |
| Matrix expectations met | — | — |

### Critical-field accuracy (matched entities)

| Field | baseline | team |
|---|---|---|
| tooth | 35/61 (57%) | 37/62 (60%) |
| relationship | — | — |
| drug | 5/5 (100%) | 5/5 (100%) |
| dose | 2/2 (100%) | 2/2 (100%) |
| negation | 5/7 (71%) | 7/8 (88%) |
| certainty | 4/4 (100%) | 4/4 (100%) |
| decision | 4/4 (100%) | 3/3 (100%) |
| allergy_status | 0/1 (0%) | 0/1 (0%) |
| medication_status | 3/3 (100%) | 2/3 (67%) |

### Per-dimension accuracy (matched entities)

| Dimension | baseline | team |
|---|---|---|
| action | 5/5 (100%) | 5/5 (100%) |
| assertion | 75/80 (94%) | 79/83 (95%) |
| assertion_source | 76/82 (93%) | 80/85 (94%) |
| attr:action | 1/1 (100%) | 1/1 (100%) |
| attr:as_needed | 2/2 (100%) | 2/2 (100%) |
| attr:aspect | 7/16 (44%) | 7/15 (47%) |
| attr:benefits | 1/4 (25%) | 3/4 (75%) |
| attr:bleeding | 1/3 (33%) | 6/6 (100%) |
| attr:bone_loss | 1/2 (50%) | 1/2 (50%) |
| attr:certainty | 4/4 (100%) | 4/4 (100%) |
| attr:complaint_location | 5/5 (100%) | 5/5 (100%) |
| attr:complaint_text | 4/5 (80%) | 3/5 (60%) |
| attr:content | 3/4 (75%) | 3/4 (75%) |
| attr:decision | 4/4 (100%) | 3/3 (100%) |
| attr:description | 3/3 (100%) | 4/4 (100%) |
| attr:diagnosis | 4/4 (100%) | 4/4 (100%) |
| attr:diastolic | 7/7 (100%) | 7/7 (100%) |
| attr:drug | 5/5 (100%) | 5/5 (100%) |
| attr:duration_days | 1/1 (100%) | 1/1 (100%) |
| attr:element | 4/4 (100%) | 4/4 (100%) |
| attr:finding | 4/5 (80%) | 5/5 (100%) |
| attr:frequency_code | 3/3 (100%) | 3/3 (100%) |
| attr:label | 2/4 (50%) | 2/4 (50%) |
| attr:lingering | 2/2 (100%) | 2/2 (100%) |
| attr:medication_status | 1/1 (100%) | 1/1 (100%) |
| attr:observation | 5/9 (56%) | 7/11 (64%) |
| attr:option | 9/11 (82%) | 7/9 (78%) |
| attr:original_wording | 5/6 (83%) | 4/6 (67%) |
| attr:probing_depth_mm | 3/3 (100%) | 6/6 (100%) |
| attr:procedure | 3/4 (75%) | 2/4 (50%) |
| attr:purpose | 1/1 (100%) | 1/1 (100%) |
| attr:reaction | 1/1 (100%) | 1/1 (100%) |
| attr:reason | 1/1 (100%) | 1/1 (100%) |
| attr:recommended_by_clinician | 5/7 (71%) | 4/6 (67%) |
| attr:response | 4/4 (100%) | 4/4 (100%) |
| attr:result_description | 3/6 (50%) | 3/6 (50%) |
| attr:risks | 3/4 (75%) | 3/4 (75%) |
| attr:route | 0/1 (0%) | 0/1 (0%) |
| attr:score | 3/3 (100%) | 3/3 (100%) |
| attr:sequence | 5/5 (100%) | 5/5 (100%) |
| attr:site | 3/3 (100%) | 6/6 (100%) |
| attr:strength | 2/2 (100%) | 2/2 (100%) |
| attr:substance | 1/1 (100%) | 1/1 (100%) |
| attr:surface | 0/1 (0%) | 0/1 (0%) |
| attr:systolic | 7/7 (100%) | 7/7 (100%) |
| attr:target | 0/5 (0%) | 0/5 (0%) |
| attr:test | 4/11 (36%) | 4/13 (31%) |
| attr:text | 5/5 (100%) | 5/5 (100%) |
| attr:timing | 3/4 (75%) | 4/4 (100%) |
| attr:to | 1/1 (100%) | 1/1 (100%) |
| attr:type | 3/5 (60%) | 3/5 (60%) |
| attr:unit | 7/7 (100%) | 7/7 (100%) |
| attr:value | 11/16 (69%) | 12/15 (80%) |
| negation | 5/7 (71%) | 7/8 (88%) |
| role | 5/5 (100%) | 5/5 (100%) |
| status | 5/6 (83%) | 4/6 (67%) |
| target_relation | 30/66 (45%) | 31/68 (46%) |
| time_context | 69/80 (86%) | 72/83 (87%) |
| tooth | 35/61 (57%) | 37/62 (60%) |

### Recall by type (matched / gold; produced)

| Type | baseline | team |
|---|---|---|
| allergy | 1/1; 1 | 1/1; 1 |
| consent_element | 4/4; 4 | 4/4; 5 |
| decision | 4/5; 4 | 3/5; 3 |
| diagnosis | 4/4; 4 | 4/4; 5 |
| finding | 11/14; 12 | 13/14; 14 |
| history_change | 3/7; 3 | 4/7; 5 |
| instruction | 5/5; 5 | 5/5; 8 |
| medication | 2/2; 2 | 2/2; 4 |
| next_visit | 4/4; 4 | 4/4; 4 |
| option_discussed | 7/7; 7 | 6/7; 7 |
| perio_measurement | 3/6; 3 | 6/6; 6 |
| prescription | 3/3; 3 | 3/3; 3 |
| problem | 5/5; 5 | 5/5; 5 |
| radiograph | 5/5; 5 | 5/5; 5 |
| referral | 1/1; 1 | 1/1; 1 |
| relationship | 0/0; 0 | 0/0; 2 |
| symptom | 16/16; 18 | 15/16; 26 |
| vital_reading | 7/7; 7 | 7/7; 7 |

## Stages: raw extraction vs after automated repair

| | baseline raw | baseline repaired | team raw | team repaired |
|---|---|---|---|---|
| Recall | 85/96 (89%) | 85/96 (89%) | 86/96 (90%) | 88/96 (92%) |
| Precision | 85/88 (97%) | 85/88 (97%) | 86/105 (82%) | 88/111 (79%) |
| Tooth accuracy | 35/61 (57%) | 35/61 (57%) | 41/63 (65%) | 37/62 (60%) |

After human review: not yet measured. It needs the review sessions you run yourselves in the UI (at least two cases); `score_session` scores an approved session the same way.

## Flags (E2; E3 review questions counted separately)

| | baseline | team |
|---|---|---|
| caught | 9 | 9 |
| missed | 2 | 2 |
| duplicates | 2 | 1 |
| false alarms | 11 | 69 |
| false alarms clinical | 3 | 4 |
| false alarms technical | 8 | 65 |
| tolerated | 0 | 0 |
| questions | 2 | 1 |

Missed expected flags: case5/baseline: quick_note_tooth_unclear, treatment_target_mismatch; case5/team: quick_note_tooth_unclear, treatment_target_mismatch


`tolerated` = produced flags the draft matrix annotation lists as acceptable (not counted as false alarms); `false alarms` marked *(technical)* are safeguard flags (failed checks, open tasks), not clinical rules.

## Claim support (Grader, rendered attributes)

| Label | baseline | team |
|---|---|---|
| changed_meaning | 2 | 1 |
| supported_by_quick_notes | 9 | 9 |
| supported_by_transcript | 219 | 293 |

## Cost and latency

| | baseline | team |
|---|---|---|
| Model calls | 17 | 199 |
| Extraction + checking cost (USD) | 0.405 | 2.821 |
| Shared stages R2 + E3 (USD) | 0.052 | 0.049 |
| Wall time per run, s (every run) | 25.2, 26.3, 20.9, 26.3, 28.8 | 53.6, 50.4, 45.2, 63.6, 38.4 |

Latencies are single runs at one session at a time; percentiles would be exploratory and are not given.

## Per-run rows

| Case | Pipeline | Candidate | Recall | Precision | Tooth | Flags caught/missed/false | Expectations | Forbidden | Wall s | USD |
|---|---|---|---|---|---|---|---|---|---|---|
| case4 | baseline | yes | 20/24 (83%) | 20/20 (100%) | 6/14 (43%) | 0/0/0 | 0/0 | — | 25.2 | 0.091 |
| case4 | team | yes | 23/24 (96%) | 23/25 (92%) | 9/17 (53%) | 0/0/24 | 0/0 | — | 53.6 | 0.592 |
| case5 | baseline | yes | 15/18 (83%) | 15/16 (94%) | 7/11 (64%) | 2/2/3 | 0/0 | — | 26.3 | 0.091 |
| case5 | team | yes | 15/18 (83%) | 15/19 (79%) | 7/9 (78%) | 2/2/13 | 0/0 | — | 50.4 | 0.519 |
| case6 | baseline | yes | 15/18 (83%) | 15/17 (88%) | 6/9 (67%) | 1/0/0 | 0/0 | — | 20.9 | 0.080 |
| case6 | team | yes | 16/18 (89%) | 16/23 (70%) | 7/10 (70%) | 1/0/10 | 0/0 | — | 45.2 | 0.564 |
| case7 | baseline | yes | 21/21 (100%) | 21/21 (100%) | 6/17 (35%) | 3/0/6 | 0/0 | — | 26.3 | 0.098 |
| case7 | team | yes | 21/21 (100%) | 21/26 (81%) | 9/17 (53%) | 3/0/16 | 0/0 | — | 63.6 | 0.681 |
| case8 | baseline | yes | 14/15 (93%) | 14/14 (100%) | 10/10 (100%) | 3/0/2 | 0/0 | — | 28.8 | 0.098 |
| case8 | team | yes | 13/15 (87%) | 13/18 (72%) | 5/9 (56%) | 3/0/6 | 0/0 | — | 38.4 | 0.513 |

## Relationship correctness vs flag policy

Team relationships can suppress low target flags only when Cs passes; baseline relationships need a dentist confirmation. Relationship rows per run: case5/team: [{'tooth': 9, 'kind': 'adjacent_examined', 'semantic': 'pass'}]; case6/team: [{'tooth': 18, 'kind': 'adjacent_examined', 'semantic': 'pass'}]

## What this does and doesn't show

- It compares one single-extractor baseline with one team configuration on the same frozen sources and overlays. It measures split extraction + registry staging + Cs/Ce/Co checks together, not agent teams in general. No ablations yet, so causal claims stay modest.
- 21 small synthetic cases, one run each: counts have wide uncertainty.
- The gold and the Grader are not independent of the system's designer (both drafted by Claude); a person must check the gold, every critical-field grade, and every baseline/team disagreement (see grader_review.csv).
- Audio/ASR quality and human review time are not measured yet.

