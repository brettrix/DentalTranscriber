# dev-v2 patch

> Prototype — test data only. Synthetic role-played cases. Gold annotations are **drafts by Claude, not yet checked by a person** (`checked_by` empty), so every number below is provisional until the gold is checked.

Provenance: git `a7493f5fa8eed2d5ccafc265a38bf9d420458c30` (dirty), eval config hash `0e83966b3288c14e`, schema `9dbe1baa5d0fbe62`, models claude-sonnet-5-5 (grader claude-opus-5-5), rule mode synthetic_demo, text mode.

## Candidate production and workflow

| | team |
|---|---|
| Runs producing a candidate | 1/1 (100%) |
| Reached ready_for_review | 1/1 (100%) |
| Dentist approval blocked before human review | 1/1 (100%) |

Every quality number below is computed over the runs that produced a candidate and is reported with that denominator.

## Extraction quality (final, after automated repair)

| Metric | team |
|---|---|
| Entity precision | 4/6 (67%) across 1 of 1 runs |
| Entity recall | 4/4 (100%) across 1 of 1 runs |
| Clinical-target accuracy | 1/1 (100%) |
| Matrix expectations met | 4/4 (100%) |

### Critical-field accuracy (matched entities)

| Field | team |
|---|---|
| tooth | 2/2 (100%) |
| relationship | — |
| drug | — |
| dose | — |
| negation | — |
| certainty | — |
| decision | — |
| allergy_status | — |
| medication_status | — |

### Per-dimension accuracy (matched entities)

| Dimension | team |
|---|---|
| assertion | 3/3 (100%) |
| assertion_source | 3/3 (100%) |
| attr:aspect | 0/1 (0%) |
| attr:complaint_location | 1/1 (100%) |
| attr:complaint_text | 1/1 (100%) |
| attr:diastolic | 1/1 (100%) |
| attr:lingering | 1/1 (100%) |
| attr:response | 1/1 (100%) |
| attr:result_description | 1/1 (100%) |
| attr:systolic | 1/1 (100%) |
| attr:test | 1/1 (100%) |
| attr:value | 1/1 (100%) |
| role | 1/1 (100%) |
| target_relation | 1/1 (100%) |
| time_context | 3/3 (100%) |
| tooth | 2/2 (100%) |

### Recall by type (matched / gold; produced)

| Type | team |
|---|---|
| decision | 0/0; 1 |
| finding | 1/1; 1 |
| problem | 1/1; 1 |
| symptom | 1/1; 2 |
| vital_reading | 1/1; 1 |

## Stages: raw extraction vs after automated repair

| | team raw | team repaired |
|---|---|---|
| Recall | 4/4 (100%) | 4/4 (100%) |
| Precision | 4/6 (67%) | 4/6 (67%) |
| Tooth accuracy | 2/2 (100%) | 2/2 (100%) |

After human review: not yet measured. It needs the review sessions you run yourselves in the UI (at least two cases); `score_session` scores an approved session the same way.

## Flags (E2; E3 review questions counted separately)

| | team |
|---|---|
| caught | 1 |
| missed | 0 |
| duplicates | 0 |
| false alarms | 2 |
| false alarms clinical | 0 |
| false alarms technical | 2 |
| tolerated | 2 |
| questions | 0 |

Missed expected flags: none


`tolerated` = produced flags the draft matrix annotation lists as acceptable (not counted as false alarms); `false alarms` marked *(technical)* are safeguard flags (failed checks, open tasks), not clinical rules.

## Claim support (Grader, rendered attributes)

| Label | team |
|---|---|
| changed_meaning | 1 |
| supported_by_quick_notes | 2 |
| supported_by_transcript | 14 |

## Cost and latency

| | team |
|---|---|
| Model calls | 25 |
| Extraction + checking cost (USD) | 0.281 |
| Shared stages R2 + E3 (USD) | 0.005 |
| Wall time per run, s (every run) | 24.8 |

Latencies are single runs at one session at a time; percentiles would be exploratory and are not given.

## Per-run rows

| Case | Pipeline | Candidate | Recall | Precision | Tooth | Flags caught/missed/false | Expectations | Forbidden | Wall s | USD |
|---|---|---|---|---|---|---|---|---|---|---|
| m17_injection | team | yes | 4/4 (100%) | 4/6 (67%) | 2/2 (100%) | 1/0/2 | 4/4 | — | 24.8 | 0.286 |

## Relationship correctness vs flag policy

Team relationships can suppress low target flags only when Cs passes; baseline relationships need a dentist confirmation. Relationship rows per run: 

## What this does and doesn't show

- It compares one single-extractor baseline with one team configuration on the same frozen sources and overlays. It measures split extraction + registry staging + Cs/Ce/Co checks together, not agent teams in general. No ablations yet, so causal claims stay modest.
- 21 small synthetic cases, one run each: counts have wide uncertainty.
- The gold and the Grader are not independent of the system's designer (both drafted by Claude); a person must check the gold, every critical-field grade, and every baseline/team disagreement (see grader_review.csv).
- Audio/ASR quality and human review time are not measured yet.

