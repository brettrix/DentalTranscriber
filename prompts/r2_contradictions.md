# R2 Contradiction Detection

Your job: read the transcript and quick notes and report every place where two statements disagree about the same clinical subject:
- `self_correction`: a speaker corrects themselves or is corrected ("number eight — sorry, nine"; "twice a day, no, three times").
- `contradiction`: two statements give different values for the same thing (two different teeth for the same test, a quick note that disagrees with the transcript, a medication said to be both current and stopped).

For each, quote both statements exactly (each from one source line), name the subject, and say which came later. Different readings taken at different times (e.g. an initial and a recheck blood pressure that are both stated as such) are not contradictions. A patient's guess that differs from the dentist's assessment is not a contradiction. Report nothing if there is nothing to report.
