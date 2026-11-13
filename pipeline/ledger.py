"""Real-call gate and ledger.

No real Anthropic or Deepgram call happens unless SCRIBE_ALLOW_REAL=1 (set only after the user says "run real").
Every real call, Grader and fault injection included, is appended to data/api_ledger.jsonl with model, tokens
and estimated cost.
"""
from __future__ import annotations

import os
from functools import lru_cache

import yaml

from pipeline.storage import ROOT, append_jsonl, now, read_jsonl

LEDGER = ROOT / "data" / "api_ledger.jsonl"
ALLOW_ENV = "SCRIBE_ALLOW_REAL"


class RealCallsDisabled(RuntimeError):
    pass


def real_calls_allowed() -> bool:
    return os.environ.get(ALLOW_ENV) == "1"


def require_real(service: str) -> None:
    if not real_calls_allowed():
        raise RealCallsDisabled(f"real {service} calls are disabled; set {ALLOW_ENV}=1 only after approval ('run real')")


@lru_cache(maxsize=1)
def prices() -> dict:
    return yaml.safe_load((ROOT / "config" / "eval.yaml").read_text())["pricing_per_mtok"]


def cost_usd(model: str | None, input_tokens: int | None, output_tokens: int | None) -> float:
    p = prices().get(model or "")
    if p is None:
        return 0.0
    return ((input_tokens or 0) * p["input"] + (output_tokens or 0) * p["output"]) / 1e6


def record(service: str, *, agent: str, model: str | None, input_tokens=None, output_tokens=None, result: str,
           label: str = "", error: str | None = None, extra: dict | None = None) -> dict:
    rec = {"timestamp": now(), "service": service, "agent": agent, "label": label, "model": model, "result": result,
           "input_tokens": input_tokens, "output_tokens": output_tokens,
           "usd": round(cost_usd(model, input_tokens, output_tokens), 6), "error": error, **(extra or {})}
    append_jsonl(LEDGER, rec)
    return rec


def totals() -> dict:
    rows = read_jsonl(LEDGER)
    return {"calls": len(rows), "input_tokens": sum(r.get("input_tokens") or 0 for r in rows),
            "output_tokens": sum(r.get("output_tokens") or 0 for r in rows),
            "usd": round(sum(r.get("usd") or 0 for r in rows), 4)}
