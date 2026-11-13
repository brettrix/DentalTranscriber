"""Deterministic normalization rules (section 7.2). Each returns the normalized value or raises NormalizationError."""
from __future__ import annotations

import re

from glossary import DRUG_NAMES, SPOKEN_TOOTH_NUMBERS


class NormalizationError(ValueError):
    pass


_UNITS = {"zero": 0, "oh": 0, "o": 0, "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5,
          "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
          "seventeen": 17, "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
         "ninety": 90}
_NUMBER_WORDS = set(_UNITS) | set(_TEENS) | set(_TENS) | {"hundred", "thousand", "and", "half", "point"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[\s\-,]+", text.lower().strip()) if t]


def spoken_number(text: str) -> float | int:
    """'fourteen' -> 14; 'one sixty-eight' -> 168; 'a hundred and twenty' -> 120; '7' -> 7; 'half' -> 0.5."""
    s = text.strip().lower()
    m = re.fullmatch(r"\d+(\.\d+)?", s)
    if m:
        return float(s) if "." in s else int(s)
    toks = [t for t in _tokens(s) if t != "and"]
    if not toks or any(t not in _NUMBER_WORDS for t in toks):
        raise NormalizationError(f"not a spoken number: {text!r}")
    if len(toks) > 1 and toks[0] in ("a", "an") and toks[1] not in ("hundred", "thousand", "half"):
        toks = toks[1:]
    if toks in (["half"], ["a", "half"], ["one", "half"]):
        return 0.5
    if "point" in toks:
        i = toks.index("point")
        whole = spoken_number(" ".join(toks[:i])) if toks[:i] else 0
        frac = "".join(str(_UNITS[t]) for t in toks[i + 1:] if t in _UNITS)
        if not frac:
            raise NormalizationError(f"bad decimal: {text!r}")
        return float(f"{whole}.{frac}")
    if "hundred" in toks or "thousand" in toks:
        total, current = 0, 0
        for t in toks:
            if t in _UNITS:
                current += _UNITS[t]
            elif t in _TEENS:
                current += _TEENS[t]
            elif t in _TENS:
                current += _TENS[t]
            elif t == "hundred":
                current = (current or 1) * 100
            elif t == "thousand":
                total += (current or 1) * 1000
                current = 0
            else:
                raise NormalizationError(f"not a spoken number: {text!r}")
        return total + current
    # Groups of up to two digits; several groups are read digit-wise ("one sixty-eight" = 1|68).
    groups: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in _TENS:
            value = _TENS[t]
            if i + 1 < len(toks) and toks[i + 1] in _UNITS and _UNITS[toks[i + 1]] > 0 and toks[i + 1] not in ("a", "an"):
                value += _UNITS[toks[i + 1]]
                i += 1
            groups.append(str(value))
        elif t in _TEENS:
            groups.append(str(_TEENS[t]))
        elif t in _UNITS:
            if t in ("a", "an") and len(toks) > 1:
                raise NormalizationError(f"not a spoken number: {text!r}")
            groups.append(str(_UNITS[t]))
        else:
            raise NormalizationError(f"not a spoken number: {text!r}")
        i += 1
    if len(groups) == 1:
        return int(groups[0])
    # Digit-wise reading needs every group after the first to be a full two-digit group or an "oh"-led pair.
    return int("".join(g if (k == 0 or len(g) == 2 or g == "0") else g for k, g in enumerate(groups)))


def _find_number_phrase(text: str) -> str:
    """The longest run of number words or digits in the text."""
    s = text.lower()
    m = re.search(r"\d+(\.\d+)?", s)
    if m:
        return m.group(0)
    toks = re.split(r"(\s+|-)", s)
    best, run = "", []
    for tok in toks:
        word = re.sub(r"[^a-z]", "", tok)
        if not word and tok.strip() in ("", "-"):
            if run:
                run.append(tok)
            continue
        if word in _NUMBER_WORDS or (word in ("a", "an") and not run):
            run.append(word)
        else:
            cand = _trim_run(run)
            if len(cand) > len(best):
                best = cand
            run = []
    cand = _trim_run(run)
    if len(cand) > len(best):
        best = cand
    if not best:
        raise NormalizationError(f"no number in {text!r}")
    return best


def _trim_run(run: list[str]) -> str:
    words = "".join(run).strip(" -").split()
    while words and words[-1] in ("and", "a", "an"):
        words.pop()
    while words and words[0] == "and":
        words.pop(0)
    if words in (["a"], ["an"]):
        return ""
    return " ".join(words)


def spoken_tooth_number(text: str) -> int:
    """'number fourteen', '#14', 'tooth 14', 'fourteen' -> 14 (1-32 only)."""
    s = text.lower().strip()
    s = re.sub(r"^(number|tooth|#)\s*", "", s).strip(" .,?!")
    s = re.sub(r"^(number|tooth|#)\s*", "", s).strip(" .,?!")
    if s in SPOKEN_TOOTH_NUMBERS:
        n = SPOKEN_TOOTH_NUMBERS[s]
    else:
        n = spoken_number(_find_number_phrase(s))
    if not isinstance(n, int) or not 1 <= n <= 32:
        raise NormalizationError(f"not an adult tooth number: {text!r}")
    return n


def bp_reading(text: str) -> str:
    """'172 over 104' -> '172/104'; '124/80' -> '124/80'."""
    s = text.lower()
    m = re.search(r"(\d{2,3})\s*(/|over)\s*(\d{2,3})", s)
    if m:
        sys_, dia = int(m.group(1)), int(m.group(3))
    else:
        parts = re.split(r"\bover\b", s)
        if len(parts) != 2:
            raise NormalizationError(f"not a BP reading: {text!r}")
        sys_ = spoken_number(_find_number_phrase(parts[0]))
        dia = spoken_number(_find_number_phrase(parts[1]))
    if not (50 <= sys_ <= 300 and 20 <= dia <= 200):
        raise NormalizationError(f"implausible BP: {text!r}")
    return f"{int(sys_)}/{int(dia)}"


_DOSE_UNITS = {"milligrams": "mg", "milligram": "mg", "mg": "mg", "mgs": "mg", "grams": "g", "gram": "g", "g": "g",
               "micrograms": "mcg", "microgram": "mcg", "mcg": "mcg", "milliliters": "mL", "milliliter": "mL",
               "ml": "mL", "cc": "mL", "units": "units", "unit": "units", "percent": "%", "%": "%"}


def _fmt_num(n: float | int) -> str:
    return str(int(n)) if float(n).is_integer() else str(n)


def dose(text: str) -> str:
    """'five hundred milligrams' -> '500 mg'; 'half a milligram' -> '0.5 mg'; '600mg' -> '600 mg'."""
    s = text.lower().strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*(milligrams?|mgs?|grams?|g|micrograms?|mcg|milliliters?|ml|cc|units?|%|percent)", s)
    if m:
        return f"{_fmt_num(float(m.group(1)))} {_DOSE_UNITS[m.group(2)]}"
    m = re.search(r"\b(milligrams?|mgs?|grams?|micrograms?|mcg|milliliters?|ml|units?|percent)\b", s)
    if not m:
        raise NormalizationError(f"no dose unit in {text!r}")
    before = s[: m.start()].strip()
    if re.search(r"\bhalf\b", before):
        value: float | int = 0.5
    else:
        value = spoken_number(_find_number_phrase(before))
    return f"{_fmt_num(value)} {_DOSE_UNITS[m.group(1)]}"


_FREQ = [
    (r"\b(twice a day|twice daily|two times a day|two times daily|bid)\b", "BID"),
    (r"\b(three times a day|three times daily|tid)\b", "TID"),
    (r"\b(four times a day|four times daily|qid)\b", "QID"),
    (r"\b(at bedtime|before bed|qhs)\b", "QHS"),
    (r"\b(once a day|once daily|one time a day|daily|every day|qd)\b", "QD"),
]


def frequency(text: str) -> str:
    """'three times a day' -> 'TID'; 'every six hours as needed' -> 'q6h PRN'."""
    s = text.lower()
    code = None
    m = re.search(r"every\s+([a-z0-9\- ]+?)\s+hours?", s)
    if m:
        code = f"q{_fmt_num(spoken_number(_find_number_phrase(m.group(1))))}h"
    else:
        m = re.search(r"\bq(\d+)h\b", s)
        if m:
            code = f"q{m.group(1)}h"
        else:
            for pattern, c in _FREQ:
                if re.search(pattern, s):
                    code = c
                    break
    prn = bool(re.search(r"\b(as needed|prn|when needed|if needed)\b", s))
    if code is None:
        if prn:
            return "PRN"
        raise NormalizationError(f"no frequency in {text!r}")
    return f"{code} PRN" if prn else code


def duration(text: str) -> int:
    """'for seven days' -> 7; 'for a week' -> 7. Returns days."""
    s = text.lower()
    m = re.search(r"([a-z0-9\- ]*?)\s*(days?|weeks?)\b", s)
    if not m:
        raise NormalizationError(f"no duration in {text!r}")
    qty_text = re.sub(r"^(for|about|over)\s+", "", m.group(1).strip())
    if qty_text in ("a", "an", "one", ""):
        qty = 1
    else:
        qty = spoken_number(_find_number_phrase(qty_text))
    days = qty * 7 if m.group(2).startswith("week") else qty
    return int(days)


_SURFACES = {"mesial": "M", "occlusal": "O", "distal": "D", "buccal": "B", "lingual": "L", "facial": "F",
             "incisal": "I"}


def surface_code(text: str) -> str:
    """'M O D' -> 'MOD'; 'mesial occlusal' -> 'MO'; 'DO' -> 'DO'."""
    s = text.strip()
    letters = re.sub(r"[\s\-,.]+", "", s).upper()
    if letters and re.fullmatch(r"[MODBLFI]{1,5}", letters):
        return letters
    words = re.findall(r"[a-z]+", s.lower())
    code = "".join(_SURFACES[w] for w in words if w in _SURFACES)
    if not code:
        raise NormalizationError(f"no surface in {text!r}")
    return code


def drug_name(text: str) -> str:
    """Brand or generic -> generic, via the glossary table only."""
    s = re.sub(r"[^a-z0-9/\- ]", "", text.lower()).strip()
    if s in DRUG_NAMES:
        return DRUG_NAMES[s]
    for name in sorted(DRUG_NAMES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", s):
            return DRUG_NAMES[name]
    raise NormalizationError(f"drug not in table: {text!r}")


def mm_measure(text: str) -> float | int:
    """Perio measurement in mm: '4', 'four millimeters' -> 4."""
    s = re.sub(r"\b(millimeters?|mm)\b", "", text.lower())
    return spoken_number(_find_number_phrase(s))


RULES = {
    "spoken_number": lambda t: spoken_number(_find_number_phrase(t)),
    "spoken_tooth_number": spoken_tooth_number,
    "bp_reading": bp_reading,
    "dose": dose,
    "frequency": frequency,
    "duration": duration,
    "surface_code": surface_code,
    "drug_name": drug_name,
    "mm_measure": mm_measure,
}

DETERMINISTIC_RULES = set(RULES)


def apply(rule: str, text: str):
    if rule not in RULES:
        raise NormalizationError(f"unknown deterministic rule {rule!r}")
    return RULES[rule](text)


def values_equal(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return float(a) == float(b)
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    return a == b


def normalize_value(rule: str, value):
    """Normalize an already-extracted value with the rule (used by Cs comparison and gold matching)."""
    if value is None:
        return None
    if rule == "spoken_tooth_number":
        return value if isinstance(value, int) else spoken_tooth_number(str(value))
    if rule in ("spoken_number", "mm_measure", "duration"):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return float(apply(rule, str(value)))
    try:
        return apply(rule, str(value))
    except NormalizationError:
        return str(value).strip().lower()
