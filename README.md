# Dental Scribe Agent Team (prototype)

> **Prototype — test data only. Do not use with real patient information.** Every case here is synthetic and role-played. Using this with real patients requires a separate deployment, security, and compliance review.

An AI scribe for a dental **limited exam**. It transcribes the visit, extracts typed clinical entities tied to exact evidence, checks them, reconciles conflicts, renders a note from the checked graph, raises flags and questions for the dentist, and supports structured correction and revision-bound dentist approval before export. It documents what was said and asks questions. It never decides or changes a diagnosis, treatment, or premedication.

Scope: adult permanent dentition only (Universal numbering 1–32; anything else is free text and "not assessable" for tooth rules), limited exams only.

## Setup

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # add ANTHROPIC_API_KEY and DEEPGRAM_API_KEY (never committed)
.venv/bin/python -m pytest -q   # offline tests (fake model client)
.venv/bin/streamlit run app.py  # UI
```

Run one case from the command line: `python -m eval.run_case eval/cases/case1 --mode team`.
Run the evaluation: `python -m eval.run_eval --cases eval/cases eval/matrix --pipeline both`.
Fault injection: `python -m eval.fault_injection --cases case1 case2 case3`.
Purge old sessions: `python manage.py purge --older-than 7d`.

Models are set in `config/agents.yaml`: `claude-sonnet-5-5` for every producer and checker, and `claude-opus-5-5` for the eval-only Grader.

## How it works

```
STAGE A  sources (frozen, hashed)      text transcript  |  Deepgram nova-3-medical → provider_response.json → utterances.json
         role overlay (human-confirmed for audio), quick notes, visit metadata
STAGE B  extraction → staging.json
         baseline: B0 (one extractor)          team: Br registry → B1 history | B2 symptoms | B3 findings | B4 plan
         L  Linker (Python): ids, versions, hashes, references, structural validation, batch commit
STAGE C  checks on every source-backed entity, one repair round per agent, then re-check
         Cv evidence & normalization (Python)   Cs blind re-extraction + Ce free-text equivalence (team)
         Co omissions (team)                    R2 contradiction detection (both)
STAGE D  reconciliation (Python, derived records only): quick-note conflicts, target relations, R2 links → freeze vN
STAGE E  E0 note renderer · E1 highlights · E2 rule engine · E3 clinical review questions · flag merger
STAGE F  status (processing finished, checks finished, ready for review)
HUMAN    item editor / dispositions / conflict resolution → structural validation → vN+1 → re-run D, E, F
         role or correction overlay change → re-run from Stage B; approval is revoked by any change
```

Key properties, each covered by a test in `tests/test_invariants.py` and `tests/test_failure_paths.py`:
- **One snapshot per graph version.** Execution history (stage runs, check runs, traces) sits outside the snapshot and its hash.
- **Source support.** Source-backed entities come only from Stage B, and in a frozen graph every one has a terminal result for each applicable check. Check results are append-only and bound to the entity's hashes, so an old pass never applies to changed inputs.
- **Structural validation on every version,** human edits included. A failing edit is rejected and nothing commits.
- **Nothing is silently dropped.** Invalid agent output stays in staging unchanged, with a human-review task. Every stage failure creates a task.
- **Critical-change policy.** An Assistant's add, edit, removal or conflict resolution affecting critical content (teeth, allergies, medications, prescriptions, vitals, diagnoses, decisions, consent elements, relationships) becomes a pending change until the Dentist accepts it.
- **Revision-bound approval.** Approval stores the snapshot, note, render-config, overlay, source and rule-file hashes. Any change returns the session to draft, and export re-checks the hashes and refuses on a mismatch.

## Verification levels

Every note line shows its entity's actual check results (`span✓ norm✓ meaning✓`, `✗` failed, `?` not confirmed from evidence, `⏸` not assessed because a checker failed, `–` not applicable).
- **Baseline mode:** "span-checked (meaning not checked)". Cv checks exact quotes and deterministic values (tooth numbers, BP, doses, frequencies, durations, surfaces, drug names). Its relationships suppress target flags only with a dentist confirmation.
- **Team mode:** "span-checked and meaning-checked" describes what was attempted. A line whose meaning check failed or wasn't assessed is shown that way, never as meaning-checked. Cs re-extracts each entity from a ±2-utterance window without seeing the producer's values, and Python compares the two field by field (free text through Ce).

The checkers are **checking passes, not independent reviewers**: they share the sources and the same model. Their error rates are measured, not assumed (see Evaluation).

Clinical-content rules (`bp_reading`, `allergy_rx`, `refusal_discussion`, the E3 review rules) are all `pending`, and run only in `RULE_MODE=synthetic_demo`, where their output is labeled "Rule pending dentist confirmation." Technical safeguards always run.

## Evaluation

`eval/` holds the development cases (`cases/`, split from `scripts_cases_1-3_tuning.md`), the edge-case matrix (`matrix/`, 18 short synthetic cases), draft gold (`gold/`), the runner, the scoring code and fault injection. Results are in `eval/results/` (see the summary below).

**Gold status:** all development and matrix gold is `annotated_by: claude`, with `checked_by` empty. A person must check it before any number is treated as more than provisional. `grader_review.csv` in each results folder lists what to check by hand: every critical-field grade, every baseline/team disagreement, and a 20% sample of the rest.

What the evaluation does and doesn't show:
- It compares one single-extractor baseline with one team configuration on the same frozen sources. This measures split extraction, registry staging and the Cs/Ce/Co checks together, not "agent teams" in general. There are no ablations yet.
- The sample is small and synthetic, with one run per case, so the counts have wide uncertainty. Every quality number comes with its candidate-production denominator.
- The baseline can raise more target flags because its relationships can't suppress them without a dentist confirmation, not because its extraction is worse. Relationship correctness is reported separately.
- Not measured yet: audio and ASR accuracy, speaker attribution (this needs your recordings and `verified_transcript.json`), human review time, and quality after human review.

Held-out cases (4–6 and the two Cohen writes) go in `eval/heldout/` and are run once, after the evaluation configuration is frozen and hashed (stage 9).

## Next steps

- A dentist reviews and approves the clinical rules (`rules/config.json`, `rules/clinical_review_rules.yaml`) and the drug/allergen tables.
- Dentist-reviewed gold annotations, and hand checks of the Grader.
- Audio runs with verified transcripts, plus the Should tier: A1 role suggestions, A2 term corrections, per-agent ablations, latency repeats.
- A deployment, security and compliance review before any real patient use, with real logins in place of the role dropdown.
- Later tier: a narrative writing agent, more highlights, a flag annotation agent, an AssemblyAI adapter, free-text addenda, charting integration, other note types, pediatric/primary teeth.

See `DECISIONS.md` for every choice made where the build spec was open.
