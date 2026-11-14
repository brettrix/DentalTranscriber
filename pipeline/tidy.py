"""Deterministic corrections to extractor output, applied by the Linker before an item is built.

These cover mistakes the model makes that plain rules can catch from the cited words alone:
- a hedged "no" ("I don't think so") recorded as a possible or present finding;
- a strength spoken without its unit ("ibuprofen six hundred") left empty.

Nothing here invents content: every value comes from the cited utterance, and each change adds the derivation
that the evidence check (Cv) verifies.
"""
from __future__ import annotations

import re

import glossary
from pipeline.normalize import NormalizationError, spoken_number

# ---------------------------------------------------------------- hedged denials

HEDGED_NO = re.compile(
    r"\b(?:i\s+)?(?:don'?t|do\s+not)\s+(?:think|believe)\s+(?:so|i\s+(?:do|did|have|am))\b"
    r"|\bnot\s+that\s+i(?:'m|\s+am)?\s+(?:know|aware)(?:\s+of)?\b"
    r"|\bnot\s+really\b|\bprobably\s+not\b|\bi\s+doubt\s+it\b|\bnot\s+as\s+far\s+as\s+i\s+know\b", re.I)
_FILLER = re.compile(r"\b(?:no|nope|nah|um+|uh+|er+|well|hmm+|oh|so|i\s+mean|honestly|to\s+be\s+honest)\b", re.I)
DENIABLE = ("symptom", "history_change", "allergy", "medication", "finding")


def hedged_no(text: str | None) -> re.Match | None:
    """The hedge inside a short answer that is only a hedged "no" ("I don't think so.", "No, not that I know of").
    A longer answer that goes on to describe something is left alone."""
    m = HEDGED_NO.search(text or "")
    if not m:
        return None
    rest = _FILLER.sub(" ", (text[:m.start()] + " " + text[m.end():]))
    return m if len(re.findall(r"[A-Za-z']+", rest)) <= 2 else None


def is_hedged_denial(entity) -> bool:
    """True when an item's cited words are a hedged "no" (used when wording the note, including for notes written
    before this correction existed)."""
    return any(s.source_type == "transcript" and hedged_no(s.text) for s in entity.evidence)


def _concepts(out) -> list[str]:
    a = out.attributes
    words = [a.get(k) for k in ("value", "substance", "drug", "description", "observation", "test", "original_wording")]
    if out.type == "symptom" and a.get("aspect") not in (None, "other"):
        words.append(a["aspect"].replace("_", " "))
    return [w for w in words if isinstance(w, str) and w.strip()]


def fix_hedged_denial(out, sources) -> bool:
    """A hedged "no" is a denial, never a possible or present finding. Cites the clinician's question when the
    answer follows it directly, so the negation can be checked against what was asked."""
    from agents.io import DerivationOut, Quote
    if out.type not in DENIABLE or out.assertion not in ("possible", "present"):
        return False
    hit = next(((i, q, hedged_no(q.quote)) for i, q in enumerate(out.evidence)
                if q.source_type == "transcript" and hedged_no(q.quote)), None)
    if hit is None:
        return False
    i, quote, m = hit
    out.assertion = "denied"
    if out.type == "allergy":
        out.attributes["allergy_status"] = "denied"
    if any(d.rule == "negation" for d in out.derivations):
        return True
    cue = quote.quote[m.start():m.end()]
    concept_index, concept = None, None
    idx = sources.utterance_index(quote.source_id)
    asked = sources.utterances.utterances[idx - 1] if idx > 0 else None
    for word in _concepts(out):
        if word.lower() in quote.quote.lower():
            concept_index, concept = i, word
            break
        if asked is not None and asked.text.rstrip().endswith("?") and word.lower() in asked.text.lower():
            at = asked.text.lower().index(word.lower())
            concept = asked.text[at:at + len(word)]
            concept_index = next((k for k, q in enumerate(out.evidence)
                                  if q.source_type == "transcript" and q.source_id == asked.id
                                  and concept.lower() in q.quote.lower()), None)
            if concept_index is None:
                out.evidence.append(Quote(source_type="transcript", source_id=asked.id, quote=asked.text))
                concept_index = len(out.evidence) - 1
            break
    if concept is not None:
        out.derivations.append(DerivationOut(attribute="assertion", rule="negation", **{"from": cue}, to="denied",
                                             evidence_index=i, concept=concept, concept_evidence_index=concept_index))
    return True


# ---------------------------------------------------------------- strengths spoken without a unit

_NUM = (r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
        r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|a)")
_NUMBER = rf"(?:\d{{2,4}}|{_NUM}(?:[\s-]+(?:and\s+)?{_NUM})*)"
_UNIT_AHEAD = r"(?!\s*(?:milligrams?|mgs?|grams?|g\b|micrograms?|mcg|milliliters?|ml\b|cc\b|units?|%|percent))"
STRENGTH_RULE = "spoken_strength"   # derivation rule: a number said right after the drug's name, unit assumed mg
MG_RANGE = (25, 2000)               # outside this a bare number is not read as milligrams (e.g. "Tylenol 3")


def names_of(generic: str | None) -> list[str]:
    """Every name (brand or generic) the glossary knows for a generic drug, longest first."""
    if not generic:
        return []
    return sorted((k for k, v in glossary.DRUG_NAMES.items() if v == generic), key=len, reverse=True)


def spoken_strength_value(phrase: str) -> str:
    n = spoken_number(phrase.strip())
    if not isinstance(n, int) or not MG_RANGE[0] <= n <= MG_RANGE[1]:
        raise NormalizationError(f"not a plausible milligram strength: {phrase!r}")
    return f"{n} mg"


def _strength_after(names: list[str], text: str):
    pattern = re.compile(rf"\b(?:{'|'.join(re.escape(n) for n in names)})\b[\s,]*(?:is\s+|at\s+|of\s+)?({_NUMBER})"
                         rf"{_UNIT_AHEAD}\b", re.I)
    for m in pattern.finditer(text):
        try:
            return m, spoken_strength_value(m.group(1))
        except NormalizationError:
            continue
    return None, None


def fix_spoken_strength(out, sources) -> bool:
    """"Ibuprofen six hundred and Tylenol five hundred" -> 600 mg and 500 mg. Only a number said right after that
    drug's own name counts, and only when no strength was extracted."""
    from agents.io import DerivationOut, Quote
    if out.type not in ("medication", "prescription") or out.attributes.get("strength"):
        return False
    names = names_of(out.attributes.get("drug"))
    if not names:
        return False
    for i, q in enumerate(list(out.evidence)):
        if q.source_type != "transcript":
            continue
        m, value = _strength_after(names, q.quote)
        index = i
        if m is None:  # the model may have quoted only the drug's name: look at the whole line it cited
            line = sources.source_text("transcript", q.source_id) or ""
            m, value = _strength_after(names, line)
            if m is None:
                continue
            out.evidence.append(Quote(source_type="transcript", source_id=q.source_id, quote=line[m.start():m.end()]))
            index = len(out.evidence) - 1
        out.attributes["strength"] = value
        out.derivations.append(DerivationOut(attribute="attributes.strength", rule=STRENGTH_RULE,
                                             **{"from": m.group(1)}, to=value, evidence_index=index))
        return True
    return False


def tidy_item(out, sources) -> list[str]:
    """Apply every correction to one extracted item (in place). Returns what was changed, for the staging record."""
    changed = []
    if fix_hedged_denial(out, sources):
        changed.append("hedged denial recorded as denied")
    if fix_spoken_strength(out, sources):
        changed.append("spoken strength filled in")
    return changed
