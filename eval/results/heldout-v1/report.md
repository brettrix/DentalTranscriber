# Held-out evaluation (cases 4-8, run once on frozen config 0e83966b3288c14e)

> Prototype — test data only. Synthetic role-played cases. Gold annotations are **drafts by Claude, not yet checked by a person** (`checked_by` empty), so every number below is provisional until the gold is checked.

Provenance: git `832a171cccda1226a840079ee4f9d7abffdaa382`, eval config hash `0e83966b3288c14e`, schema `9dbe1baa5d0fbe62`, models claude-sonnet-5-5 (grader claude-opus-5-5), rule mode synthetic_demo, text mode.

## Candidate production and workflow

| | baseline | team |
|---|---|---|
| Runs producing a candidate | 5/5 (100%) | 5/5 (100%) |
| Reached ready_for_review | 5/5 (100%) | 5/5 (100%) |
| Dentist approval blocked before human review | — | — |

Every quality number below is computed over the runs that produced a candidate and is reported with that denominator.

## Extraction quality (final, after automated repair)

| Metric | baseline | team |
|---|---|---|
| Entity precision | — across 0 of 5 runs | — across 0 of 5 runs |
| Entity recall | — across 0 of 5 runs | — across 0 of 5 runs |
| Clinical-target accuracy | — | — |
| Matrix expectations met | — | — |

### Critical-field accuracy (matched entities)

| Field | baseline | team |
|---|---|---|
| tooth | — | — |
| relationship | — | — |
| drug | — | — |
| dose | — | — |
| negation | — | — |
| certainty | — | — |
| decision | — | — |
| allergy_status | — | — |
| medication_status | — | — |

### Per-dimension accuracy (matched entities)

| Dimension | baseline | team |
|---|---|---|

### Recall by type (matched / gold; produced)

| Type | baseline | team |
|---|---|---|

## Stages: raw extraction vs after automated repair

| | baseline raw | baseline repaired | team raw | team repaired |
|---|---|---|---|---|
| Recall | — | — | — | — |
| Precision | — | — | — | — |
| Tooth accuracy | — | — | — | — |

After human review: not yet measured. It needs the review sessions you run yourselves in the UI (at least two cases); `score_session` scores an approved session the same way.

## Flags (E2; E3 review questions counted separately)

| | baseline | team |
|---|---|---|
| caught | 0 | 0 |
| missed | 0 | 0 |
| duplicates | 0 | 0 |
| false alarms | 0 | 0 |
| false alarms clinical | 0 | 0 |
| false alarms technical | 0 | 0 |
| tolerated | 0 | 0 |
| questions | 0 | 0 |

Missed expected flags: none


`tolerated` = produced flags the draft matrix annotation lists as acceptable (not counted as false alarms); `false alarms` marked *(technical)* are safeguard flags (failed checks, open tasks), not clinical rules.

## Claim support (Grader, rendered attributes)

| Label | baseline | team |
|---|---|---|

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
| case4 | baseline | yes | | | | | | | 25.2 | 0.091 |
| case4 | team | yes | | | | | | | 53.6 | 0.592 |
| case5 | baseline | yes | | | | | | | 26.3 | 0.091 |
| case5 | team | yes | | | | | | | 50.4 | 0.519 |
| case6 | baseline | yes | | | | | | | 20.9 | 0.080 |
| case6 | team | yes | | | | | | | 45.2 | 0.564 |
| case7 | baseline | yes | | | | | | | 26.3 | 0.098 |
| case7 | team | yes | | | | | | | 63.6 | 0.681 |
| case8 | baseline | yes | | | | | | | 28.8 | 0.098 |
| case8 | team | yes | | | | | | | 38.4 | 0.513 |

## Relationship correctness vs flag policy

Team relationships can suppress low target flags only when Cs passes; baseline relationships need a dentist confirmation. Relationship rows per run: 

## What this does and doesn't show

- It compares one single-extractor baseline with one team configuration on the same frozen sources and overlays. It measures split extraction + registry staging + Cs/Ce/Co checks together, not agent teams in general. No ablations yet, so causal claims stay modest.
- 21 small synthetic cases, one run each: counts have wide uncertainty.
- The gold and the Grader are not independent of the system's designer (both drafted by Claude); a person must check the gold, every critical-field grade, and every baseline/team disagreement (see grader_review.csv).
- Audio/ASR quality and human review time are not measured yet.


## Informal flag read-out against the answer keys (not a score)

Held-out gold doesn't exist yet: the spec has the Grader draft gold from the answer keys and a person check it before scoring, and drafting was deferred. The table only compares each answer key's "Expected flags" line with what each mode raised. Cases 7–8 were written by Claude (the assistant that wrote the build prompt) in place of a teammate's cases.

| Case | Expected (answer key) | Baseline | Team |
|---|---|---|---|
| 4 | none; no `perio_rationale` | none ✓ | no clinical flags ✓; 6 high + 2 medium technical flags (Cs rejections) |
| 5 | `treatment_target_disagreement` (high); `quick_note_tooth_unclear` (medium) | both ✓ (+ `treatment_target_mismatch`, 2 R2 tooth-number conflicts) | both ✓ (+ mismatch, 1 conflict, `radiograph_finding_missing`, technical) |
| 6 | `bp_reading` (medium) | ✓, nothing else | ✓ + technical flags |
| 7 | self-correction conflict, later = left; `quick_note_complaint_mismatch` (low); `quick_note_tooth_unclear` (medium); no `refusal_discussion`, no `allergy_rx` | all ✓; the side correction appears as an *unmatched* contradiction (no entity covers it); extra `radiograph_finding_missing` | same as baseline + technical flags |
| 8 | quick-note vs transcript BP conflict (medium); `bp_reading` (medium, precautionary); `refusal_discussion` (low); no `radiograph_finding_missing`, no `allergy_rx` | all ✓ (conflict is high: vital readings are a critical type, 9.2) | all ✓ + technical flags |

Caveat: this is a read-out by the system's own designer against flag *names*, not the one-to-one, evidence-matched, Grader-judged flag scoring in section 14.3.
