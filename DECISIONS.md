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
