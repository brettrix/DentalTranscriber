"""Shared vocabulary: Deepgram keyterms, abbreviations, tooth numbers, drug tables, quick-note labels."""

KEYTERMS = [
    "periapical", "bitewing", "panoramic", "pano", "percussion", "palpation", "Endo Ice", "Tooth Slooth",
    "radiolucency", "caries", "recurrent decay", "reversible pulpitis", "irreversible pulpitis", "pulp necrosis",
    "apical periodontitis", "abscess", "pericoronitis", "periodontitis", "scaling and root planing", "root canal",
    "buildup", "composite", "amalgam", "bonding", "calculus", "prophy", "probing depth", "bleeding on probing",
    "recession", "attachment loss", "bone loss", "mobility", "mesial", "distal", "occlusal", "buccal", "lingual",
    "facial", "incisal", "MOD", "DO", "MO", "amoxicillin", "Augmentin", "clindamycin", "azithromycin", "cephalexin",
    "ibuprofen", "acetaminophen", "chlorhexidine", "lisinopril", "warfarin", "apixaban", "clopidogrel", "alendronate",
]
assert len(KEYTERMS) <= 100

ABBREVIATIONS = {
    "PA": "periapical radiograph",
    "BWX": "bitewing radiographs",
    "FMX": "full-mouth series",
    "RCT": "root canal treatment",
    "SRP": "scaling and root planing",
    "BOP": "bleeding on probing",
    "Rx": "prescription",
    "PCP": "primary care provider",
    "BP": "blood pressure",
    "CC": "chief complaint",
}

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = {20: "twenty", 30: "thirty"}


def _tooth_word(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    word = _TENS[tens * 10]
    return word if ones == 0 else f"{word}-{_ONES[ones]}"


# Spoken tooth number table for the Universal system (adult permanent dentition only).
SPOKEN_TOOTH_NUMBERS = {_tooth_word(n): n for n in range(1, 33)}
SPOKEN_TOOTH_NUMBERS.update({w.replace("-", " "): n for w, n in list(SPOKEN_TOOTH_NUMBERS.items()) if "-" in w})
SPOKEN_TOOTH_NUMBERS.update({w.replace("-", ""): n for w, n in list(SPOKEN_TOOTH_NUMBERS.items()) if "-" in w})

# Quadrants by Universal number, used only to compare coarse complaint locations.
def tooth_quadrant(tooth: int) -> str:
    if 1 <= tooth <= 8:
        return "UR"
    if 9 <= tooth <= 16:
        return "UL"
    if 17 <= tooth <= 24:
        return "LL"
    if 25 <= tooth <= 32:
        return "LR"
    raise ValueError(f"not an adult tooth: {tooth}")


QUADRANT_PHRASES = {
    "upper right": "UR", "upper left": "UL", "lower left": "LL", "lower right": "LR",
    "top right": "UR", "top left": "UL", "bottom left": "LL", "bottom right": "LR",
    "right upper": "UR", "left upper": "UL", "left lower": "LL", "right lower": "LR",
}

# Brand -> generic. Generic names map to themselves. Combination products map to their ingredients.
DRUG_NAMES = {
    "amoxicillin": "amoxicillin", "amoxil": "amoxicillin",
    "augmentin": "amoxicillin/clavulanate", "amoxicillin/clavulanate": "amoxicillin/clavulanate",
    "amoxicillin-clavulanate": "amoxicillin/clavulanate",
    "penicillin": "penicillin", "penicillin vk": "penicillin", "pen vk": "penicillin",
    "ampicillin": "ampicillin", "dicloxacillin": "dicloxacillin",
    "clindamycin": "clindamycin", "cleocin": "clindamycin",
    "azithromycin": "azithromycin", "zithromax": "azithromycin", "z-pak": "azithromycin", "zpak": "azithromycin",
    "cephalexin": "cephalexin", "keflex": "cephalexin",
    "ibuprofen": "ibuprofen", "advil": "ibuprofen", "motrin": "ibuprofen",
    "naproxen": "naproxen", "aleve": "naproxen", "aspirin": "aspirin",
    "acetaminophen": "acetaminophen", "tylenol": "acetaminophen", "paracetamol": "acetaminophen",
    "hydrocodone/acetaminophen": "hydrocodone/acetaminophen", "vicodin": "hydrocodone/acetaminophen",
    "norco": "hydrocodone/acetaminophen", "codeine": "codeine",
    "tylenol with codeine": "acetaminophen/codeine", "tylenol 3": "acetaminophen/codeine",
    "chlorhexidine": "chlorhexidine", "peridex": "chlorhexidine",
    "lisinopril": "lisinopril", "zestril": "lisinopril", "prinivil": "lisinopril",
    "warfarin": "warfarin", "coumadin": "warfarin", "jantoven": "warfarin",
    "apixaban": "apixaban", "eliquis": "apixaban",
    "clopidogrel": "clopidogrel", "plavix": "clopidogrel",
    "alendronate": "alendronate", "fosamax": "alendronate",
    "metformin": "metformin", "atorvastatin": "atorvastatin", "lipitor": "atorvastatin",
    "sulfamethoxazole/trimethoprim": "sulfamethoxazole/trimethoprim", "bactrim": "sulfamethoxazole/trimethoprim",
}


def ingredients(generic: str) -> list[str]:
    """Combination products list each ingredient; single drugs list themselves."""
    return [part.strip() for part in generic.split("/") if part.strip()]


# Allergen class -> member generics, used by the allergy/prescription rule together with ingredients().
ALLERGEN_GROUPS = {
    "penicillin": ["penicillin", "amoxicillin", "ampicillin", "dicloxacillin"],
    "cephalosporin": ["cephalexin"],
    "nsaid": ["ibuprofen", "naproxen", "aspirin"],
    "sulfa": ["sulfamethoxazole"],
    "codeine": ["codeine"],
    "macrolide": ["azithromycin"],
}
ALLERGEN_ALIASES = {"penicillins": "penicillin", "pcn": "penicillin", "nsaids": "nsaid", "sulfa drugs": "sulfa",
                    "cephalosporins": "cephalosporin"}

# Quick-note labels: what kind of tooth reference each label gives.
QUICK_NOTE_LABELS = {
    "CC:": "complaint_location",
    "Tx:": "clinical_target",
    "Tooth:": "clinical_target",
    "Dx:": "clinical_target",
    "BP": "vital",
    "Allergy:": "allergy",
    "Meds:": "medication",
}
