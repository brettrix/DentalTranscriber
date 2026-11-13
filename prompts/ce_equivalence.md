# Ce Equivalence Check

Your job: for each pair of short clinical free-text values for the named attribute, decide whether B (an independent reading of the source) supports A (the recorded value) — that is, whether they say the same clinical thing.
- `equivalent`: the same clinical meaning. Different wording, word order, articles, hedges with the same meaning ("about", "maybe", "around"), or B adding a little non-contradicting context are all fine.
- `different`: A states something clinically meaningful that B contradicts or does not contain — a different tooth, side, surface, test, result, negation, severity, certainty, time, drug or dose — or A drops a qualifier that B has and that changes the meaning (e.g. "possible", "not", "mild").
- `uncertain`: you can't tell.
You see no sources; judge only the two values.
