"""E1 highlights: a short deterministic summary from the frozen graph (each line cites its entities)."""
from __future__ import annotations

from pipeline.render import entity_text


def highlights(graph, flags) -> list[dict]:
    out = []
    chief = graph.chief()
    if chief is not None:
        out.append({"label": "Chief complaint", "text": entity_text(chief, graph)[0], "entity_ids": [chief.id]})
    for kind, types in (("Assessment", ("diagnosis",)), ("Decision", ("decision",)),
                        ("Prescriptions", ("prescription",)), ("Allergies", ("allergy",)),
                        ("Next visit", ("next_visit",))):
        ents = graph.active_items(*types)
        if kind == "Allergies":
            ents = [a for a in ents if a.attributes.get("allergy_status") != "denied"]
        if ents:
            out.append({"label": kind, "text": "; ".join(entity_text(e, graph)[0] for e in ents),
                        "entity_ids": [e.id for e in ents]})
    safety = [f for f in flags if f.safety_critical]
    if safety:
        out.append({"label": "Safety-critical flags", "text": "; ".join(f.message for f in safety),
                    "entity_ids": sorted({i for f in safety for i in f.entity_ids})})
    return out
