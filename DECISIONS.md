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

## Human correction and approval (stage 5)
- **An edit** creates a new human-entry version (owner `human`, `human_entry` evidence naming the reviewer and reason) that supersedes the old version, so source-backed checks are `not_applicable` on it. A Dentist edit of critical content also records `dentist_confirmed`.
- **Re-checks after human edits.** Every human change re-runs Cv (and Cs in team mode) for any source-backed entity whose current hashes have no matching execution, so a committed graph never holds a `not_run` summary. A team-mode problem/relationship edit re-runs Cs on every problem-scoped entity, as required.
- **No graph yet (Br or B0 failed).** The registry is entered through `enter_registry`. By the Dentist it takes effect and extraction re-runs (Br is recorded `not_applicable` while a human registry exists; an extractor's own chief problem resolves to the human one). By an Assistant it waits in `pending_registry.json` for the Dentist (critical-change policy).
- **Staged records and approval.** Only staged records from the latest run block approval. Older staged records stay in `staging.json` unchanged for audit.
- **Reruns.** Human-entered entities carry over unchanged. Their `human_entered` disposition is re-recorded if the bound hashes moved (e.g. a role change for a cited speaker), but `dentist_confirmed` carries only while it still binds. A regenerated entity that a human removed or edited is committed as superseded inside the same Linker transaction, so whole-graph validation sees one chief problem.
- **Conflicts between a human entry and a regenerated entity** are raised only for single-valued subjects (not findings, symptoms, instructions or consent elements, which legitimately share a type and tooth).
- **Approval-matrix rows** are checked from the graph itself (failed checks, conflicts, tasks, staged records, sections, pending changes); the flag rows cover the remaining high and safety-critical flags. "Marked for dentist" is a flag action. An E3 failure task does not block dentist approval (10.1 says the dentist *may* accept it).
- **Dismissing a safety-critical flag** is Dentist-only. A dismissal is stored in the flag's history (keyed by its inputs hash) and never changes a check result.

## Deepgram (stage 6)
- Parameters were checked against Deepgram's current docs: `model=nova-3-medical` (a listed value); `keyterm` repeated once per term (the glossary's 56 terms are far below the 500-token keyterm cap); `utterances`, `smart_format` and `punctuate` set to `true`. `diarize=true` is kept because it is still accepted, though the docs now mark it deprecated in favour of `diarize_model`. Switch to `diarize_model` if Deepgram removes it.
- Audio sessions start with an unconfirmed role overlay; `run_pipeline` refuses Stage B until a human confirms roles on the Role confirmation tab.

## Evaluation (stage 7)
- **Gold.** Development and matrix gold are drafted by Claude (`annotated_by: claude`, `checked_by: null`) from the scripts and answer keys. Every report says the numbers are provisional until a person checks the gold. Where the answer key is ambiguous (e.g. "looks like a cracked tooth" as definite vs possible), the gold entry has a `note`.
- **Matrix.** 17 cases from the section 14.1 table plus `m18_two_problems`, which the "finding moved to the wrong problem" fault needs. Each matrix case has a quick-note BP (except `m16_no_bp`), so `bp_reading` doesn't fire everywhere. Each case's `expect.json` turns the table's expectation into machine checks, and lists flags the annotation accepts as legitimate (`tolerated`). These are reported separately, never silently dropped.
- **Matching.** Entities need the same kind and type, the mapped problem (encounter items aside), and at least one shared utterance or quick-note id. Pairs are chosen greedily by evidence overlap, tooth and deterministic-attribute agreement. Free-text attributes are judged by the Grader (`claude-opus-5-5`); `uncertain` counts as wrong. Assertion is scored exactly, and a separate `negation` dimension treats `absent`/`denied` as one class.
- **E3 questions** are scored separately from E2 flags. A false alarm marked *(technical)* is a safeguard flag (failed check, open task), not a clinical rule.
- **"After human review"** is not measured yet: it needs review sessions run by people in the UI.
- **Fault injection** converts gold to graph entities with whole-utterance spans and automatically found derivations. A gold value with no spoken form in its own evidence (e.g. a diagnosis line that doesn't say the tooth) is converted with that value null and listed as a conversion gap.

## Changes made from the dev-v1 results
- **Treatment on a recorded control/adjacent/referred tooth** now fires `treatment_target_mismatch` (high) even when no clinical target was identified. In dev-v1, m02 team mode: Br never identified #14 as the target, so a filling scheduled on control tooth #3 got only a low `target_not_assessable`. The record itself says that tooth isn't the problem tooth, and a relationship never explains treatment (6.2).
- **Cs calibration v2.** dev-v1 fault injection: Cs caught 27/28 association-preserving faults but falsely rejected 25/85 unmodified gold entities (29%). Team mode produced 73 false-alarm flags against the baseline's 11, 64 of them technical safeguards driven by those rejections. The two largest sources were symptom `aspect` labels (onset vs duration, trigger vs biting pain for the same words) and `clinician_observation` vs `test_response`. Now `symptom.aspect` is compared as part of the symptom's free-text description, and those two sources count as equivalent. Patient-vs-clinician attribution stays strict, so the patient-as-clinician fault is still caught.

## Cost controls (after the credit outage)
- **Real-call gate.** `default_client()` and the Deepgram adapter refuse to make real calls unless `SCRIBE_ALLOW_REAL=1` is set. It is set only after the user's explicit "run real". Without it, a pipeline stage fails cleanly (stage-run record and task), as with any other agent error. The Streamlit UI therefore needs `SCRIBE_ALLOW_REAL=1` to process new visits.
- **Ledger.** Every call through a real client (pipeline agents, E3, Grader, fault-injection Cs/Ce, Deepgram) appends one line to `data/api_ledger.jsonl` (model, tokens, estimated USD, result). The Grader's traces now also go to `<results>/grader_traces.jsonl`, and fault injection's to `<results>/fault_traces.jsonl`. Usage before the ledger is reconstructed in `eval/results/api_usage_history.md`.
- **Tests are offline by construction.** `tests/conftest.py` refuses and fails any internet socket connection, swaps `default_client` for the schema-valid `FakeLLM`, and unsets the gate. Before this, tests that edited an entity used by E3 called the real API (E3 re-derives with the default client): 4 billed calls per suite run.
- **Finishing stage 7 without repeating spend.** `run_eval --rescore <dir> --only …` re-grades existing sessions without re-running the pipeline. `run_eval --merge BASE PATCH…` combines a results folder with just the re-run cases, with no model calls. The machinery (pipeline → Grader → report/CSV/review sheet, rescore, merge, fault injection, freeze guard) is tested offline in `tests/test_eval_offline.py`.
