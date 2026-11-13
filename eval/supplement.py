"""Supplementary analysis for an existing results folder, offline (no model calls, report.md untouched):
tooth accuracy on tooth-bearing items only, and every raised flag that wasn't matched to gold.

python -m eval.supplement eval/results/heldout-v1-graded
Matching is deterministic (the Grader only judges free text), so these recomputations use the same matches
as the frozen report.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from eval import scoring
from eval.run_eval import EVAL_DIR, frac, load_gold, load_rows
from pipeline.graph import load_graph
from pipeline.orchestrator import load_latest
from pipeline.overlays import load_sources
from pipeline.storage import ROOT, Session
from schemas.flags import Flag


def rows_for(results_dir: Path) -> list[dict]:
    """A merged results folder keeps no runs/; rebuild its rows from the merge sources in its provenance."""
    if (results_dir / "runs").exists():
        return load_rows(results_dir)
    from eval.run_eval import merge
    srcs = json.loads((results_dir / "provenance.json").read_text())["merged"]
    return merge(ROOT / srcs[0], [ROOT / d for d in srcs[1:]])


def supplement(results_dir: Path) -> str:
    rows = rows_for(results_dir)
    tooth = {p: defaultdict(lambda: [0, 0]) for p in ("baseline", "team")}
    tooth_all_dims = {p: [0, 0] for p in ("baseline", "team")}
    unmatched = []
    for r in sorted(rows, key=lambda r: (r["case"], r["pipeline"])):
        if not r.get("scored"):
            continue
        s = Session(r["session"])
        gold, graph, latest = load_gold(r["case"]), load_graph(s), load_latest(s)
        flags = [Flag.model_validate(f) for f in latest.get("flags", [])]
        exp_path = EVAL_DIR / "matrix" / r["case"] / "expect.json"
        expect = json.loads(exp_path.read_text()) if exp_path.exists() else {}
        sc = scoring.score_case(gold, graph, flags, latest.get("markdown"), load_sources(s), r["pipeline"],
                                expect.get("expect"), expect.get("tolerated_flags", []))
        for t, (a, b) in scoring.tooth_by_type(sc).items():
            tooth[r["pipeline"]][t][0] += a
            tooth[r["pipeline"]][t][1] += b
        for m in sc.matches:
            if m.produced is not None and "tooth" in m.dims:
                tooth_all_dims[r["pipeline"]][0] += bool(m.dims["tooth"])
                tooth_all_dims[r["pipeline"]][1] += 1
        for f in sc.flags["unmatched_detail"]:
            unmatched.append((r["case"], r["pipeline"], f))
    L = [f"# Supplement to {results_dir.name}/report.md\n",
         "Recomputed offline from the stored sessions (no model calls); the frozen report is unchanged. "
         "Check: the 'all matched items' row should equal the report's tooth figure.\n",
         "## Tooth accuracy on tooth-bearing items (gold names a tooth)\n",
         "| Type | baseline | team |\n|---|---|---|"]
    from eval.scoring import TOOTH_BEARING
    for t in TOOTH_BEARING:
        L.append(f"| {t} | {frac(*tooth['baseline'][t])} | {frac(*tooth['team'][t])} |")
    tb = {p: [sum(v[0] for v in tooth[p].values()), sum(v[1] for v in tooth[p].values())] for p in tooth}
    L.append(f"| **all tooth-bearing** | {frac(*tb['baseline'])} | {frac(*tb['team'])} |")
    L.append(f"| all matched items (report's tooth figure) | {frac(*tooth_all_dims['baseline'])} | "
             f"{frac(*tooth_all_dims['team'])} |\n")
    L.append("The report's tooth figure also counts items whose gold has no tooth but the produced item names one "
             "(or the reverse): symptoms, medications, instructions, consent elements and the like.\n")
    L.append("## Raised flags not matched to gold\n")
    L.append("| Case | Pipeline | Rule | Severity | Kind | Evidence | Message |\n|---|---|---|---|---|---|---|")
    for case, pipe, f in unmatched:
        L.append(f"| {case} | {pipe} | {f['rule_id']} | {f['severity']} | "
                 f"{'technical' if f['technical'] else 'clinical/target'} | {', '.join(f['evidence'][:4])} | "
                 f"{f['message'][:140].replace('|', '/')} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    d = ROOT / sys.argv[1]
    (d / "supplement.md").write_text(supplement(d), "utf-8")
    print(f"wrote {d / 'supplement.md'}")
