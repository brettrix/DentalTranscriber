"""Freeze the evaluation configuration before held-out runs (section 14.5).

python -m eval.freeze          # writes eval/FROZEN.json with per-file hashes and the eval config hash
python -m eval.freeze --check  # exits non-zero if anything frozen has changed since
"""
from __future__ import annotations

import argparse
import json
import sys

from eval.run_eval import FROZEN_PATHS, _files, provenance, tree_hash
from pipeline.storage import ROOT, sha256_text

FROZEN = ROOT / "eval" / "FROZEN.json"


def file_hashes() -> dict[str, str]:
    return {str(f.relative_to(ROOT)): sha256_text(f.read_bytes()) for rel in FROZEN_PATHS for f in _files(ROOT / rel)}


def freeze() -> dict:
    record = {"eval_config_hash": tree_hash(FROZEN_PATHS), "files": file_hashes(), "provenance": provenance()}
    FROZEN.write_text(json.dumps(record, indent=1) + "\n")
    return record


def check() -> list[str]:
    if not FROZEN.exists():
        return ["not frozen yet"]
    frozen = json.loads(FROZEN.read_text())["files"]
    now = file_hashes()
    return sorted({k for k in frozen.keys() | now.keys() if frozen.get(k) != now.get(k)})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        changed = check()
        print("frozen configuration unchanged" if not changed else f"changed since freeze: {changed}")
        sys.exit(1 if changed else 0)
    print(f"frozen: {freeze()['eval_config_hash']}")
