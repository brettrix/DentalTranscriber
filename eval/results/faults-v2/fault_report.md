# Fault injection report

> Built from **draft gold (annotated_by: claude, not yet checked)** converted to the graph schema with whole-utterance spans and derivations found automatically. Cs is a real model call; Cv and rules are Python.

## False rejections on unmodified gold

| Case | Entities | Cv fail | Cs fail | Cs unconfirmed | Conversion gaps |
|---|---|---|---|---|---|
| case1 | 23 | 0 | 10 | 0 | 3 |
| case2 | 20 | 0 | 5 | 0 | 3 |
| case3 | 25 | 0 | 8 | 0 | 3 |
| m01_control_tooth | 7 | 0 | 1 | 0 | 0 |
| m18_two_problems | 10 | 0 | 2 | 2 | 0 |
| **all** | 85 | 0 | 26 | 2 | |

## Derivation-breaking faults

| Fault | Applied in | Cv caught | Cs fail | Cs unconfirmed | Rules (new flag) | Missed by all |
|---|---|---|---|---|---|---|
| tooth_swap | 5 | 5 | 5 | 0 | 5 | 0 |
| negation_flip | 5 | 5 | 5 | 0 | 5 | 0 |
| dose_change | 1 | 1 | 1 | 0 | 0 | 0 |
| **total** | 11 | 11 | 11 | 0 | 10 | 0 |

## Association-preserving faults

| Fault | Applied in | Cv caught | Cs fail | Cs unconfirmed | Rules (new flag) | Missed by all |
|---|---|---|---|---|---|---|
| possible_definite | 4 | 0 | 4 | 0 | 3 | 0 |
| historical_current | 5 | 0 | 5 | 0 | 5 | 0 |
| number_on_wrong_tooth | 5 | 0 | 5 | 0 | 5 | 0 |
| dropped_qualifier | 3 | 0 | 2 | 0 | 2 | 1 |
| patient_as_clinician | 5 | 0 | 5 | 0 | 5 | 0 |
| false_control_relationship | 5 | 0 | 5 | 0 | 5 | 0 |
| finding_wrong_problem | 1 | 0 | 1 | 0 | 1 | 0 |
| **total** | 28 | 0 | 27 | 0 | 26 | 1 |

Association-preserving detection (Cs fail or unconfirmed) is the headline number for the meaning checks. `unconfirmed` means the entity is not accepted and is shown as not confirmed from evidence; it is counted separately from an outright mismatch.

## Per-fault detail

- case1 · tooth_swap on it_011@1: Cv=caught, Cs=fail, new flags=['unexplained_other_tooth', 'unsupported_content'] — target.tooth: producer 15 vs checker 14
- case1 · dose_change: not applicable to this case
- case1 · negation_flip on it_001@1: Cv=caught, Cs=fail, new flags=['unsupported_content'] — assertion: producer 'absent' vs checker 'present'
- case1 · possible_definite on it_015@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — assertion: producer 'possible' vs checker 'present'; attributes.certainty: producer 'possible' vs checker 'definite'
- case1 · historical_current on it_001@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — time_context: producer 'historical' vs checker 'current'
- case1 · number_on_wrong_tooth on it_011@1: Cv=pass, Cs=fail, new flags=['unexplained_other_tooth', 'unsupported_content'] — target.tooth: producer 3 vs checker 14
- case1 · finding_wrong_problem: not applicable to this case
- case1 · dropped_qualifier on it_002@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — free-text details: different (producer 'onset; 3 weeks, getting worse' vs checker 'upper left side; duration; Maybe three weeks')
- case1 · patient_as_clinician on it_001@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — assertion_source: producer 'clinician_assessment' vs checker 'patient_report'
- case1 · false_control_relationship on rl_fault@1: Cv=pass, Cs=fail, new flags=['unexplained_other_tooth', 'unsupported_content', 'unsupported_content'] — assertion_source: producer 'clinician_observation' vs checker None; tooth: producer 3 vs checker None; relation_kind: producer 'control' vs checker None
- case2 · tooth_swap on it_008@1: Cv=caught, Cs=fail, new flags=['unexplained_other_tooth'] — target.tooth: producer 31 vs checker 30; free-text details: uncertain (producer 'large existing filling' vs checker 'bite test; big old filling')
- case2 · dose_change: not applicable to this case
- case2 · negation_flip on it_001@1: Cv=caught, Cs=fail, new flags=['unsupported_content'] — assertion: producer 'absent' vs checker 'present'
- case2 · possible_definite on it_013@1: Cv=pass, Cs=fail, new flags=— — assertion: producer 'possible' vs checker 'present'; target.tooth: producer None vs checker 30; attributes.certainty: producer 'possible' vs checker 'definite'
- case2 · historical_current on it_001@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — time_context: producer 'historical' vs checker 'current'
- case2 · number_on_wrong_tooth on it_008@1: Cv=pass, Cs=fail, new flags=['unexplained_other_tooth'] — target.tooth: producer 10 vs checker 30; attributes.response: producer None vs checker 'present'; free-text details: different (producer 'large existing filling' vs checker 'bite test')
- case2 · finding_wrong_problem: not applicable to this case
- case2 · dropped_qualifier on it_002@1: Cv=pass, Cs=pass, new flags=—
- case2 · patient_as_clinician on it_001@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — assertion_source: producer 'clinician_assessment' vs checker 'patient_report'
- case2 · false_control_relationship on rl_fault@1: Cv=pass, Cs=fail, new flags=['unexplained_other_tooth', 'unsupported_content', 'unsupported_content'] — assertion_source: producer 'clinician_observation' vs checker None; tooth: producer 10 vs checker None; relation_kind: producer 'control' vs checker None
- case3 · tooth_swap on it_010@1: Cv=caught, Cs=fail, new flags=['unexplained_other_tooth', 'unsupported_content'] — target.tooth: producer 20 vs checker 19; free-text details: different (producer 'large filling' vs checker 'swelling in the gum next to number nineteen on the cheek side')
- case3 · dose_change on it_021@1: Cv=caught, Cs=fail, new flags=— — attributes.strength: producer '250 mg' vs checker '500 mg'; attributes.dose: producer None vs checker '500 mg'
- case3 · negation_flip on it_001@1: Cv=caught, Cs=fail, new flags=['unsupported_content'] — assertion: producer 'absent' vs checker 'present'
- case3 · possible_definite on it_016@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — assertion: producer 'possible' vs checker 'present'; attributes.certainty: producer 'possible' vs checker 'definite'
- case3 · historical_current on it_004@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — time_context: producer 'current' vs checker 'historical'; free-text details: different (producer 'prior_treatment; hurt on and off a few months ago, then stopped' vs checker 'tooth back there, lower l
- case3 · number_on_wrong_tooth on it_010@1: Cv=pass, Cs=fail, new flags=['unexplained_other_tooth', 'unsupported_content'] — target.tooth: producer 8 vs checker 19; free-text details: different (producer 'large filling' vs checker 'big filling and swelling in the gum next to it on the cheek side')
- case3 · finding_wrong_problem: not applicable to this case
- case3 · dropped_qualifier on it_008@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — free-text details: different (producer 'other changes to health' vs checker 'no other changes to health')
- case3 · patient_as_clinician on it_001@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — assertion_source: producer 'clinician_assessment' vs checker 'patient_report'
- case3 · false_control_relationship on rl_fault@1: Cv=pass, Cs=fail, new flags=['unexplained_other_tooth', 'unsupported_content', 'unsupported_content'] — assertion_source: producer 'clinician_observation' vs checker None; tooth: producer 8 vs checker None; relation_kind: producer 'control' vs checker None
- m01_control_tooth · tooth_swap on it_003@1: Cv=caught, Cs=fail, new flags=['unsupported_content'] — target.tooth: producer 4 vs checker 3
- m01_control_tooth · dose_change: not applicable to this case
- m01_control_tooth · negation_flip on it_002@1: Cv=caught, Cs=fail, new flags=['unsupported_content'] — assertion: producer 'absent' vs checker 'present'
- m01_control_tooth · possible_definite on it_005@1: Cv=pass, Cs=fail, new flags=['diagnosis_or_plan_missing', 'unsupported_content'] — assertion: producer 'possible' vs checker 'present'; attributes.certainty: producer 'possible' vs checker 'definite'
- m01_control_tooth · historical_current on it_002@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — time_context: producer 'historical' vs checker 'current'
- m01_control_tooth · number_on_wrong_tooth on it_003@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — target.tooth: producer 14 vs checker 3
- m01_control_tooth · finding_wrong_problem: not applicable to this case
- m01_control_tooth · dropped_qualifier: not applicable to this case
- m01_control_tooth · patient_as_clinician on it_002@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — assertion_source: producer 'clinician_assessment' vs checker 'patient_report'
- m01_control_tooth · false_control_relationship on rl_fault@1: Cv=pass, Cs=fail, new flags=['unexplained_other_tooth', 'unsupported_content', 'unsupported_content'] — tooth: producer 1 vs checker 14
- m18_two_problems · tooth_swap on it_004@1: Cv=caught, Cs=fail, new flags=['unexplained_other_tooth'] — target.tooth: producer 31 vs checker 30; free-text details: uncertain (producer 'bite' vs checker 'bite; Ow, yes')
- m18_two_problems · dose_change: not applicable to this case
- m18_two_problems · negation_flip on it_002@1: Cv=caught, Cs=fail, new flags=['unsupported_content'] — assertion: producer 'absent' vs checker 'present'
- m18_two_problems · possible_definite: not applicable to this case
- m18_two_problems · historical_current on it_002@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — time_context: producer 'historical' vs checker 'current'; free-text details: different (producer 'biting_pain; hurts when chewing' vs checker 'lower right molar; biting_pain; hurts when I chew')
- m18_two_problems · number_on_wrong_tooth on it_004@1: Cv=pass, Cs=fail, new flags=['unexplained_other_tooth'] — target.tooth: producer 2 vs checker 30; free-text details: uncertain (producer 'bite' vs checker 'bite; Ow, yes')
- m18_two_problems · finding_wrong_problem on it_006@1: Cv=pass, Cs=fail, new flags=['unexplained_other_tooth', 'unsupported_content'] — target.tooth: producer 19 vs checker 30; problem: producer pb_1 vs checker pb_2; free-text details: different (producer 'open contact where food packs in' vs checker 'cracked cusp')
- m18_two_problems · dropped_qualifier: not applicable to this case
- m18_two_problems · patient_as_clinician on it_002@1: Cv=pass, Cs=fail, new flags=['unsupported_content'] — assertion_source: producer 'clinician_assessment' vs checker 'patient_report'; free-text details: different (producer 'biting_pain; hurts when chewing' vs checker 'lower right molar; biting_pain; hurt
- m18_two_problems · false_control_relationship on rl_fault@1: Cv=pass, Cs=fail, new flags=['unexplained_other_tooth', 'unsupported_content', 'unsupported_content'] — assertion_source: producer 'clinician_observation' vs checker 'patient_report'; tooth: producer 2 vs checker None

## Conversion gaps

- case1: d1: no spoken_tooth_number derivation for target.tooth=14
- case1: o1: no spoken_tooth_number derivation for target.tooth=14
- case1: o2: no spoken_tooth_number derivation for target.tooth=14
- case2: f4: no spoken_tooth_number derivation for target.tooth=30
- case2: d1: no spoken_tooth_number derivation for target.tooth=30
- case2: o1: no spoken_tooth_number derivation for target.tooth=30
- case3: o1: no spoken_tooth_number derivation for target.tooth=19
- case3: o2: no spoken_tooth_number derivation for target.tooth=19
- case3: n1: no spoken_tooth_number derivation for target.tooth=19
