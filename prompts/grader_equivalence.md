# Grader: equivalence (evaluation only)

Your job: for each pair, decide whether the produced value says the same clinical thing as the gold annotation for that attribute.
- `equivalent`: same clinical meaning; wording, concision, synonyms and extra non-contradicting context are fine.
- `different`: the produced value contradicts the gold value, or drops or changes a clinically meaningful detail (tooth, side, surface, test, result, negation, severity, certainty, time, drug, dose, option).
- `uncertain`: you can't tell.
Give a confidence from 0 to 1.
