"""The replaceable note template and section ownership."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pipeline.storage import ROOT, sha256_text

TEMPLATE_PATH = ROOT / "templates" / "limited_exam.json"


@lru_cache(maxsize=4)
def _load(path: str) -> tuple[dict, str]:
    raw = Path(path).read_text("utf-8")
    return json.loads(raw), sha256_text(raw)


def template(path: Path = TEMPLATE_PATH) -> dict:
    return _load(str(path))[0]


def template_hash(path: Path = TEMPLATE_PATH) -> str:
    return _load(str(path))[1]


def extraction_sections() -> list[dict]:
    return [s for s in template()["sections"] if s.get("team_owner")]


def sections_owned(agent: str) -> list[str]:
    """B0 owns every extraction section; team agents own theirs."""
    if agent == "B0":
        return [s["id"] for s in extraction_sections()]
    return [s["id"] for s in extraction_sections() if s["team_owner"] == agent]


def owner_of_section(section: str, mode: str) -> str:
    if mode == "baseline":
        return "B0"
    return next(s["team_owner"] for s in extraction_sections() if s["id"] == section)


def types_of_agent(agent: str) -> list[str]:
    out: list[str] = []
    for s in extraction_sections():
        if agent == "B0" or s["team_owner"] == agent:
            out += s["item_types"]
    return out
