# Decisions

Choices made where BUILD_PROMPT v4.3 was unclear. Each keeps the invariants in section 1.1.

## Sources and transcription
- **Text-mode format.** Lines start with a role prefix in any case (`DENTIST:`, `Dentist:`). One speaker id per role, in order of first appearance (S0, S1, …). An optional explicit id (`DENTIST [S2]:`) allows two ids for one role. Unprefixed lines continue the previous utterance. Utterance ids are `u1…un`; timestamps are null.
- **Text-mode provider response** is stored byte for byte as `sources/provider_response.txt` (the typed transcript is the provider response). Deepgram responses are stored as `sources/provider_response.json`.
- **Audio roles** start as an unconfirmed overlay (`Other`, `set_by: unconfirmed`); Stage B refuses to run until a human confirms them.

## Entities and hashes
- **Relationship kind field** is named `relation_kind`, because `kind` is the entity discriminator (`problem | relationship | item`).
- **Symptom severity** is stored as `symptom.score` (a number with a required `spoken_number` derivation), with the patient's words in `value`, because 7.2 requires a deterministic derivation for severity scores.
- **Finding** has an extra `observation` attribute (the "test or observation" in 6.3) alongside `test`.
- **Allergy** has an `original_wording` attribute, so a substance that isn't in the drug table (e.g. latex) keeps its wording with a null normalized `substance` (7.2).
- **BP derivations.** A `bp_reading` derivation is written per attribute (`attributes.systolic` and `attributes.diastolic`, same `from` text); Cv recomputes the reading and compares the matching component.
- **`speaker_ids` and `roles`** are filled by the Linker from the cited utterances and the role overlay. Agents never set them.
- **`content_hash`** covers the clinical content fields, including `problem_id` and `assertion_source`. Derivations are in `support_hash` with the evidence.
- **Versions.** A matched entity gets a new version when either hash changes (not only `content_hash`), so every check execution and disposition binds to a distinct version.
- **Critical types.** All problems and relationships are treated as critical (a relationship can suppress a target rule, so it is treated conservatively), as is any item that names a tooth.
- **Tooth-target items in the 6.4 example.** The example's `test: "cold"` has no derivation; `test` is a semantic attribute and needs none. The example passes as written.

## Checks
- **Negation scope.** An `absent`/`denied` entity needs a derivation with `rule: "negation"` naming the cue (`from`) and the `concept`. Cue and concept must be in the same span, with one exception: a clinician's question and the patient's direct answer ("Any pain when you bite down?" / "Not really."), when both utterances are cited, adjacent, and the first ends with "?". Without this, ordinary Q&A negatives could never pass Cv.
- **`unconfirmed` is terminal** for `checks_finished` (section 12), but an unconfirmed entity is never accepted (9.0).
- **Agent quotes, not offsets.** Agents return quotes; the Linker finds offsets by exact search, falling back to rapidfuzz only to point Cv at the nearest text. Span text keeps the agent's quote, so a non-exact quote fails Cv and goes to repair.

## Models
- Producers and checkers use `claude-sonnet-5-5` (spec). Forced `tool_choice` is rejected on Sonnet 5.5, so calls use `tool_choice: auto` with a prompt instruction, and a missing or invalid tool call gets the one schema re-ask (10). Thinking is adaptive (default on Sonnet 5.5); per-agent effort is set in `config/agents.yaml`.
- Server-side refusal fallback (`fallbacks: "default"`) is enabled on every call; the trace records the model that actually answered.
- The eval-only Grader uses `claude-opus-5-5` with a 180 s timeout, so grading isn't done by the same model as the producers.

## Pipeline mechanics (stages 2–3)
- **Graph versions per run.** A run commits a version after the Linker, after Stage C, and at freeze (Stage D). Human actions each add one version. A stage-E failure task is a graph change, so it adds a version too.
- **Staging before graph.** When nothing can commit (no chief problem), stage-failure tasks are kept in `staging.json` until a graph exists.
- **Registry text for B1–B4** comes from Br's output, keyed `P1`, `P2`, …; the Linker resolves those keys and the agents' own local keys within one batch, in any order.
- **Repair** gets the entity in agent form (quotes instead of offsets) and returns revised items with the same `id`; a revision that changes nothing is ignored. Registry (problem/relationship) issues are never sent to repair: they become high-severity `registry_issue` tasks. This also applies to B0's problems.
- **R2 omission routing.** R2 suggests the item type its subject belongs to, so an uncovered contradiction goes to the right team extractor's repair call.
- **Unknown option links** create a low-severity task (6.8) as well as the `unknown_option_link` flag.

## Cs comparison calibration (stage 3, from case 1)
- **Inputs.** Cs is told the entity type it is checking and sees the producer's evidence quotes as "focus quotes" inside a ±2-utterance window. It never sees the producer's values. Without the type and focus it can't tell which assertion in a window to extract.
- **`absent` vs `denied`** count as the same negated assertion. The guide says when to use each, but which one is right depends on who speaks, and that is already compared through `assertion_source`.
- **Non-critical free text** (e.g. a finding's `observation`, `result_description`, `intensity`, the item's `target.free_text`) is compared as one combined description through Ce. Critical free text (diagnosis, option, procedure, referral destination) is compared attribute by attribute. On case 1, field-by-field comparison failed entities only because the same words were filed under a neighbouring field.
- **The checker adding a non-critical detail** the producer left null is not a mismatch. Any difference on a critical attribute is.
- **Ce** is asked whether the checker's reading supports the recorded value: wording and hedges ("about" vs "maybe") are equivalent; a changed or dropped clinical qualifier is not.
- **Cs extra assertions** count as omissions only if no entity cites that utterance at all. Co does the fine-grained, entity-aware omission check.
- Case 1 team run, before → after calibration: semantic pass 12/23 → 22/23 (same transcript); the remaining failure was a real ambiguity (a negative percussion test recorded as `absent`), now addressed in the extraction guide.

## E2 / E3
- **Quadrants for coarse locations.** Complaint locations such as "upper left" are compared with a tooth by Universal quadrant (glossary `QUADRANT_PHRASES`); a location with neither a tooth nor a recognizable quadrant gives `target_not_assessable` (low).
- **Allergen classes** (e.g. penicillin → amoxicillin, ampicillin) live in `rules/drug_allergy.json`, together with the glossary's brand/generic and combination-ingredient tables.
- **E3 questions are flags** with `origin: E3`, `question: true`, low severity, scored separately from E2 flags in the evaluation. Python finds the runnable rule instances (mode plus preconditions); the agent only words the question and cites entity ids from the instance's list.
- **E3 results are cached** by an inputs hash over the cited entities' hashes and the rule file, so human edits that don't touch those entities don't re-call the model. A failed E3 is not re-run while its inputs are unchanged unless the dentist presses Retry. An E3 failure task does not block approval (10.1: the dentist *may* accept it).
