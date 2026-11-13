"""Run one case folder through the pipeline and print the result. Usage: python -m eval.run_case eval/cases/case1 --mode baseline"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.orchestrator import run_pipeline
from pipeline.render import note_markdown
from pipeline.storage import Session
from pipeline.transcribe import transcribe_text, write_quick_notes, write_visit_meta


def new_case_session(case_dir: Path, mode: str, rule_mode: str = "synthetic_demo", root=None) -> Session:
    s = Session.create(root=root, case=case_dir.name, pipeline_mode=mode, rule_mode=rule_mode)
    transcribe_text(s, (case_dir / "transcript.txt").read_text("utf-8"))
    write_quick_notes(s, (case_dir / "quick_notes.txt").read_text("utf-8") if (case_dir / "quick_notes.txt").exists() else "")
    meta = json.loads((case_dir / "visit_meta.json").read_text("utf-8")) if (case_dir / "visit_meta.json").exists() else {}
    meta.pop("title", None)
    write_visit_meta(s, **meta)
    return s


def summarize(result: dict) -> str:
    run = result["run"]
    out = [f"run {run['run_id']} mode={run['mode']} graph v{run['graph_version']}", "stages:"]
    out += [f"  {l}" for l in run["log"]]
    out.append(f"trace: {run['trace_totals']}")
    out.append(f"issues before repair: {len(run['issues'])}")
    for i in run["issues"]:
        out.append(f"  - [{i['kind']}/{i['owner']}] {i.get('entity_id') or ''} {i['details'][:160]}")
    if result.get("note"):
        out.append(note_markdown(result["note"]))
    out.append("flags:")
    for f in result["flags"]:
        out.append(f"  [{f.severity}{' SAFETY' if f.safety_critical else ''}] {f.rule_id}: {f.message}")
    out.append(f"notices: {result['notices']}")
    out.append(f"status: {json.dumps(result['status'], default=str)}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("--mode", default="baseline", choices=["baseline", "team"])
    ap.add_argument("--rule-mode", default="synthetic_demo")
    args = ap.parse_args()
    s = new_case_session(Path(args.case_dir), args.mode, args.rule_mode)
    print(f"session {s.id}")
    print(summarize(run_pipeline(s, mode=args.mode, rule_mode=args.rule_mode)))


if __name__ == "__main__":
    main()
