# Grader: claim support (evaluation only)

Your job: for each claim (one rendered attribute value from a clinical note line), decide where it is supported:
- `supported_by_transcript`: the transcript states it (quote the words).
- `supported_by_quick_notes`: only the assistant's quick notes state it (quote them).
- `supported_by_visit_meta`: only the visit metadata states it.
- `supported_only_by_reviewer_entry`: only a reviewer's entry states it.
- `unsupported`: no source states it.
- `changed_meaning`: a source discusses it but the claim changes its meaning (wrong tooth, negation, certainty, time, speaker, dose).
Judge the value in the context of its line. Quote evidence exactly where you can, and give a confidence from 0 to 1.
