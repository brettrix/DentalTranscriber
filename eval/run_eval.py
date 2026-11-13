"""Evaluation runner (section 14.4).

python -m eval.run_eval --cases eval/cases eval/matrix --mode text --pipeline both [--repeats N] [--workers 3]
Writes eval/results/<stamp>/{report.md, results.csv, runs/*.json, grader_review.csv}.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

from pipeline.storage import ROOT, hash_obj, sha256_text

EVAL_DIR = ROOT / "eval"
GRADER_TRACE: list = [None]   # set by main(): grader calls are traced to <out>/grader_traces.jsonl


def grader_tracer():
    from pipeline.trace import Tracer
    return Tracer(path=GRADER_TRACE[0])
FROZEN_PATHS = ["prompts", "schemas", "rules", "glossary.py", "pipeline/normalize.py", "pipeline/compare.py",
                "eval/scoring.py", "eval/run_eval.py", "eval/fault_injection.py", "agents/grader.py",
                "config/eval.yaml", "config/agents.yaml", "templates"]


# ---------------------------------------------------------------- provenance (14.5)

def _files(path: Path):
    return sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts) if path.is_dir() else [path]


def tree_hash(paths) -> str:
    parts = {}
    for rel in paths:
        for f in _files(ROOT / rel):
            parts[str(f.relative_to(ROOT))] = sha256_text(f.read_bytes())
    return hash_obj(parts)[:16]


def provenance() -> dict:
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        except Exception:  # noqa: BLE001
            return None
    from agents.base import agent_config
    from pipeline.rules import rule_file_hashes
    cfg = agent_config()
    models = {"defaults": cfg["defaults"]["model"], **{k: v.get("model", cfg["defaults"]["model"])
                                                       for k, v in cfg.get("agents", {}).items()}}
    return {"git_hash": git("rev-parse", "HEAD"), "git_dirty": bool(git("status", "--porcelain")),
            "models": models, "prompt_hashes": {f.name: sha256_text(f.read_bytes())[:12] for f in _files(ROOT / "prompts")},
            "schema_version": tree_hash(["schemas"]), "rule_file_hashes": rule_file_hashes(),
            "eval_config_hash": tree_hash(FROZEN_PATHS), "transcriber": "text mode",
            "timestamp": datetime.now().isoformat(timespec="seconds")}


# ---------------------------------------------------------------- one run

def load_gold(case_id: str):
    from schemas.gold import GoldCase
    p = EVAL_DIR / "gold" / f"{case_id}.json"
    return GoldCase.model_validate(json.loads(p.read_text())) if p.exists() else None


def run_one(case_dir: Path, pipeline: str, repeat: int, out_dir: Path, grade: bool, rule_mode: str,
            client=None) -> dict:
    from eval.run_case import new_case_session
    from pipeline.orchestrator import run_pipeline
    row = {"case": case_dir.name, "pipeline": pipeline, "repeat": repeat}
    session = new_case_session(case_dir, pipeline, rule_mode)
    row["session"] = session.id
    t0 = time.monotonic()
    try:
        result = run_pipeline(session, mode=pipeline, rule_mode=rule_mode, client=client)
        row["error"] = None
    except Exception as exc:  # noqa: BLE001 - a crash is a candidate-production failure, reported as such
        result = None
        row["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    row["wall_s"] = round(time.monotonic() - t0, 1)
    row.update(score_session(session, pipeline, grade=grade, result=result, client=client))
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)
    (out_dir / "runs" / f"{case_dir.name}__{pipeline}__{repeat}.json").write_text(json.dumps(row, indent=1, default=str))
    print(f"done {case_dir.name} {pipeline} r{repeat}: candidate={row['candidate']} wall={row['wall_s']}s", flush=True)
    return row


def score_session(session, pipeline: str, *, grade: bool = True, result=None, client=None) -> dict:
    from eval import scoring
    from pipeline.graph import load_graph
    from pipeline.orchestrator import load_latest
    from pipeline.overlays import load_sources
    from pipeline.stage_runs import session_stage_log
    from pipeline.storage import read_json
    from pipeline.trace import read_traces
    from schemas.flags import Flag
    meta = session.meta()
    case_id = meta.get("case")
    gold = load_gold(case_id)
    latest = load_latest(session) or {}
    graph = load_graph(session)
    sources = load_sources(session)
    run_state = read_json(session.path("runs", f"{meta.get('last_run')}.json"), {}) or {}
    stage_runs = session_stage_log(session).for_run(meta.get("last_run") or "")
    status = latest.get("status") or {}
    candidate = graph is not None and bool(latest.get("note"))
    out = {"candidate": candidate, "ready_for_review": bool(status.get("ready_for_review")),
           "failed_stages": status.get("failed_stages", []),
           "production_failure_stage": None if candidate else next(
               (f"{r['stage']}/{r['agent']}" for r in stage_runs if r["status"] == "failed"), "unknown")}
    out.update(cost_row(read_traces(session)))
    if not candidate or gold is None:
        out["scored"] = False
        return out
    flags = [Flag.model_validate(f) for f in latest.get("flags", [])]
    expect = json.loads((EVAL_DIR / ("matrix" if case_id.startswith("m") else "cases") / case_id / "expect.json")
                        .read_text()) if (EVAL_DIR / "matrix" / case_id / "expect.json").exists() else {}
    final = scoring.score_case(gold, graph, flags, latest.get("markdown"), sources, pipeline,
                               expect.get("expect"), expect.get("tolerated_flags", []))
    raw_graph = load_graph(session, run_state.get("linker_graph_version")) if run_state.get("linker_graph_version") else None
    raw = scoring.score_case(gold, raw_graph, [], None, sources, pipeline) if raw_graph else None
    grades, claim_counts, claims_detail, grader_err = {}, Counter(), [], None
    if grade:
        try:
            grades = grade_pairs([final] + ([raw] if raw else []), client=client)
            claim_counts, claims_detail = grade_claims(session, sources, latest.get("note"), graph, client=client)
        except Exception as exc:  # noqa: BLE001
            grader_err = f"{type(exc).__name__}: {exc}"
    scoring.apply_grades(final, grades)
    if raw:
        scoring.apply_grades(raw, grades)
    from pipeline.approval import blockers
    dentist_blockers = blockers(session, "dentist")
    out.update({
        "scored": True, "grader_error": grader_err,
        "final": summarize_score(final, graph), "raw": summarize_score(raw, raw_graph) if raw else None,
        "claims": dict(claim_counts), "claims_detail": claims_detail,
        "dentist_blockers": len(dentist_blockers),
        "blocker_kinds": dict(Counter(b.split(":")[0].split(" ")[0] for b in dentist_blockers)),
        "check_counts": status.get("check_counts"),
        "relationships": [{"tooth": r.tooth, "kind": r.relation_kind, "semantic": r.checks.semantic_support}
                          for r in graph.active("relationship")],
    })
    return out


def summarize_score(score, graph) -> dict:
    from eval import scoring
    matched = [m for m in score.matches if m.produced is not None]
    by_type = defaultdict(lambda: {"gold": 0, "matched": 0, "produced": 0})
    for m in score.matches:
        t = m.gold["type"] or m.gold["kind"]
        by_type[t]["gold"] += 1
        by_type[t]["matched"] += m.produced is not None
    for e in [e for e in graph.active() if e.owner != "human"]:
        by_type[getattr(e, "type", None) or e.kind]["produced"] += 1
    dims, crit = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    detail = []
    for m in matched:
        for dim, ok in m.dims.items():
            if ok is None:
                continue
            base = dim.split(":")[0] if dim.startswith("status:") else dim
            dims[base][0] += ok
            dims[base][1] += 1
            b = scoring.critical_bucket(dim)
            if b:
                crit[b][0] += ok
                crit[b][1] += 1
            if not ok:
                detail.append(f"{m.gold['gid']}:{dim}")
    produced_n = sum(v["produced"] for v in by_type.values())
    return {"gold": len(score.matches), "matched": len(matched), "produced": produced_n,
            "precision": [len(matched), produced_n], "recall": [len(matched), len(score.matches)],
            "by_type": dict(by_type), "dims": dict(dims), "critical": dict(crit), "errors": detail,
            "omissions": [m.gold["gid"] for m in score.matches if m.produced is None],
            "extras": [f"{getattr(e, 'type', e.kind)}:{e.id}" for e in score.unmatched_produced],
            "problem_map": score.problem_map, "merged": score.merged, "split": score.split,
            "target_accuracy": list(score.target_accuracy), "flags": score.flags,
            "forbidden_hits": score.forbidden_hits, "expectations": score.expectations}


def grade_pairs(scores, client=None) -> dict[str, str]:
    from agents.grader import GraderEquivalence
    pairs, seen = [], set()
    for sc in scores:
        for m in sc.matches:
            for dim, g, p in m.pending:
                pid = f"{m.gold['gid']}|{dim}"
                key = (pid, str(p))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append({"pair_id": pid, "attribute": dim, "gold": g, "produced": p})
    if not pairs:
        return {}
    out = GraderEquivalence(client=client, tracer=grader_tracer()).grade(pairs)
    return {g.pair_id: g.verdict for g in out.grades}


def grade_claims(session, sources, note, graph, client=None):
    from agents.grader import GraderClaims
    claims = []
    for sec in (note or {}).get("sections", []):
        for line in sec["lines"]:
            if not line.get("entity_id"):
                continue
            for attr, val in line["attributes"].items():
                if attr in ("assertion",) and val == "present":
                    continue
                claims.append({"claim_id": f"{line['entity_id']}|{attr}", "attribute": attr, "value": val,
                               "line": line["text"]})
    if not claims:
        return Counter(), []
    humans = "\n".join(f"{e.id}: {e.evidence[0].text}" for e in graph.active() if e.owner == "human")
    out = GraderClaims(client=client, tracer=grader_tracer()).grade(sources, claims, humans)
    return Counter(g.label for g in out.grades), [g.model_dump() for g in out.grades]


def cost_row(traces) -> dict:
    cfg = yaml.safe_load((ROOT / "config" / "eval.yaml").read_text())
    price = cfg["pricing_per_mtok"]
    shared = set(cfg["shared_stage_agents"])
    calls = [r for r in traces if r.get("kind") == "model_call" and r.get("result") in ("ok", "invalid")]
    per_agent = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0, "seconds": 0.0, "usd": 0.0})
    for r in calls:
        a = per_agent[r["agent"]]
        a["calls"] += 1
        a["in"] += r.get("input_tokens") or 0
        a["out"] += r.get("output_tokens") or 0
        a["seconds"] += r.get("seconds") or 0
        p = price.get(r.get("model") or "", price["claude-sonnet-5-5"])
        a["usd"] += ((r.get("input_tokens") or 0) * p["input"] + (r.get("output_tokens") or 0) * p["output"]) / 1e6
    tot = lambda keys: round(sum(per_agent[k]["usd"] for k in keys), 4)  # noqa: E731
    return {"calls": sum(a["calls"] for a in per_agent.values()),
            "usd_pipeline": tot([k for k in per_agent if k not in shared]), "usd_shared": tot([k for k in per_agent if k in shared]),
            "per_agent": {k: {**v, "seconds": round(v["seconds"], 1), "usd": round(v["usd"], 4)} for k, v in per_agent.items()},
            "timings": [round(r.get("seconds") or 0, 1) for r in calls]}


# ---------------------------------------------------------------- report

def frac(n, d):
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "—"


def aggregate(rows, pipeline, key="final"):
    rs = [r for r in rows if r["pipeline"] == pipeline]
    cands = [r for r in rs if r.get("scored") and r.get(key)]
    agg = {"runs": len(rs), "candidates": sum(r["candidate"] for r in rs), "scored": len(cands)}
    s = lambda f: [sum(f(r[key])[0] for r in cands), sum(f(r[key])[1] for r in cands)]  # noqa: E731
    agg["precision"] = s(lambda x: x["precision"])
    agg["recall"] = s(lambda x: x["recall"])
    agg["target"] = s(lambda x: x["target_accuracy"])
    dims, crit, by_type = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0, 0])
    flags = Counter()
    for r in cands:
        for d, (a, b) in r[key]["dims"].items():
            dims[d][0] += a
            dims[d][1] += b
        for d, (a, b) in r[key]["critical"].items():
            crit[d][0] += a
            crit[d][1] += b
        for t, v in r[key]["by_type"].items():
            by_type[t][0] += v["matched"]
            by_type[t][1] += v["gold"]
            by_type[t][2] += v["produced"]
        for k in ("caught", "missed", "duplicates", "false_alarms", "tolerated", "questions"):
            flags[k] += len(r[key]["flags"][k])
        flags["false_alarms_technical"] += sum("(technical)" in x for x in r[key]["flags"]["false_alarms"])
        flags["false_alarms_clinical"] += sum("(technical)" not in x for x in r[key]["flags"]["false_alarms"])
    agg.update(dims=dict(dims), critical=dict(crit), by_type=dict(by_type), flags=dict(flags))
    agg["expectations"] = [sum(sum(e["pass"] for e in r[key]["expectations"]) for r in cands),
                           sum(len(r[key]["expectations"]) for r in cands)]
    claims = Counter()
    for r in cands:
        claims.update(r.get("claims") or {})
    agg["claims"] = dict(claims)
    agg["usd_pipeline"] = round(sum(r.get("usd_pipeline", 0) for r in rs), 3)
    agg["usd_shared"] = round(sum(r.get("usd_shared", 0) for r in rs), 3)
    agg["calls"] = sum(r.get("calls", 0) for r in rs)
    agg["wall"] = [r["wall_s"] for r in rs]
    agg["ready"] = sum(r.get("ready_for_review", False) for r in rs)
    agg["blocked"] = sum(1 for r in cands if r.get("dentist_blockers"))
    return agg


def write_report(rows, out_dir: Path, prov: dict, title: str):
    pipelines = sorted({r["pipeline"] for r in rows})
    A = {p: aggregate(rows, p) for p in pipelines}
    R = {p: aggregate(rows, p, "raw") for p in pipelines}
    L = []
    w = L.append
    w(f"# {title}\n")
    w("> Prototype — test data only. Synthetic role-played cases. Gold annotations are **drafts by Claude, not yet "
      "checked by a person** (`checked_by` empty), so every number below is provisional until the gold is checked.\n")
    w(f"Provenance: git `{prov['git_hash']}`{' (dirty)' if prov['git_dirty'] else ''}, eval config hash "
      f"`{prov['eval_config_hash']}`, schema `{prov['schema_version']}`, models {prov['models']['defaults']} "
      f"(grader {prov['models'].get('Grader')}), rule mode synthetic_demo, {prov['transcriber']}.\n")
    w("## Candidate production and workflow\n")
    w("| | " + " | ".join(pipelines) + " |\n|---|" + "---|" * len(pipelines))
    rowfmt = lambda label, f: w(f"| {label} | " + " | ".join(f(A[p]) for p in pipelines) + " |")  # noqa: E731
    rowfmt("Runs producing a candidate", lambda a: frac(a["candidates"], a["runs"]))
    rowfmt("Reached ready_for_review", lambda a: frac(a["ready"], a["runs"]))
    rowfmt("Dentist approval blocked before human review", lambda a: frac(a["blocked"], a["scored"]))
    w("\nEvery quality number below is computed over the runs that produced a candidate and is reported with that "
      "denominator.\n")
    w("## Extraction quality (final, after automated repair)\n")
    w("| Metric | " + " | ".join(pipelines) + " |\n|---|" + "---|" * len(pipelines))
    rowfmt("Entity precision", lambda a: f"{frac(*a['precision'])} across {a['scored']} of {a['runs']} runs")
    rowfmt("Entity recall", lambda a: f"{frac(*a['recall'])} across {a['scored']} of {a['runs']} runs")
    rowfmt("Clinical-target accuracy", lambda a: frac(*a["target"]))
    rowfmt("Matrix expectations met", lambda a: frac(*a["expectations"]))
    w("\n### Critical-field accuracy (matched entities)\n")
    crit_keys = ["tooth", "relationship", "drug", "dose", "negation", "certainty", "decision", "allergy_status",
                 "medication_status"]
    w("| Field | " + " | ".join(pipelines) + " |\n|---|" + "---|" * len(pipelines))
    for k in crit_keys:
        rowfmt(k, lambda a, k=k: frac(*a["critical"].get(k, [0, 0])))
    w("\n### Per-dimension accuracy (matched entities)\n")
    keys = sorted({k for p in pipelines for k in A[p]["dims"]})
    w("| Dimension | " + " | ".join(pipelines) + " |\n|---|" + "---|" * len(pipelines))
    for k in keys:
        rowfmt(k, lambda a, k=k: frac(*a["dims"].get(k, [0, 0])))
    w("\n### Recall by type (matched / gold; produced)\n")
    types = sorted({t for p in pipelines for t in A[p]["by_type"]})
    w("| Type | " + " | ".join(pipelines) + " |\n|---|" + "---|" * len(pipelines))
    for t in types:
        rowfmt(t, lambda a, t=t: (lambda v: f"{v[0]}/{v[1]}; {v[2]}")(a["by_type"].get(t, [0, 0, 0])))
    w("\n## Stages: raw extraction vs after automated repair\n")
    w("| | " + " | ".join(f"{p} raw | {p} repaired" for p in pipelines) + " |\n|---|" + "---|---|" * len(pipelines))
    for label, f in (("Recall", lambda a: frac(*a["recall"])), ("Precision", lambda a: frac(*a["precision"])),
                     ("Tooth accuracy", lambda a: frac(*a["critical"].get("tooth", [0, 0])))):
        w(f"| {label} | " + " | ".join(f"{f(R[p])} | {f(A[p])}" for p in pipelines) + " |")
    w("\nAfter human review: not yet measured. It needs the review sessions you run yourselves in the UI "
      "(at least two cases); `score_session` scores an approved session the same way.\n")
    w("## Flags (E2; E3 review questions counted separately)\n")
    w("| | " + " | ".join(pipelines) + " |\n|---|" + "---|" * len(pipelines))
    for k in ("caught", "missed", "duplicates", "false_alarms", "false_alarms_clinical", "false_alarms_technical",
              "tolerated", "questions"):
        rowfmt(k.replace("_", " "), lambda a, k=k: str(a["flags"].get(k, 0)))
    missed = [f"{r['case']}/{r['pipeline']}: {', '.join(r['final']['flags']['missed'])}" for r in rows
              if r.get("scored") and r["final"]["flags"]["missed"]]
    w("\nMissed expected flags: " + ("; ".join(missed) or "none") + "\n")
    w("\n`tolerated` = produced flags the draft matrix annotation lists as acceptable (not counted as false alarms); "
      "`false alarms` marked *(technical)* are safeguard flags (failed checks, open tasks), not clinical rules.\n")
    w("## Claim support (Grader, rendered attributes)\n")
    labels = sorted({k for p in pipelines for k in A[p]["claims"]})
    w("| Label | " + " | ".join(pipelines) + " |\n|---|" + "---|" * len(pipelines))
    for k in labels:
        rowfmt(k, lambda a, k=k: str(a["claims"].get(k, 0)))
    w("\n## Cost and latency\n")
    w("| | " + " | ".join(pipelines) + " |\n|---|" + "---|" * len(pipelines))
    rowfmt("Model calls", lambda a: str(a["calls"]))
    rowfmt("Extraction + checking cost (USD)", lambda a: f"{a['usd_pipeline']:.3f}")
    rowfmt("Shared stages R2 + E3 (USD)", lambda a: f"{a['usd_shared']:.3f}")
    rowfmt("Wall time per run, s (every run)", lambda a: ", ".join(str(x) for x in a["wall"]))
    w("\nLatencies are single runs at one session at a time; percentiles would be exploratory and are not given.\n")
    w("## Per-run rows\n")
    w("| Case | Pipeline | Candidate | Recall | Precision | Tooth | Flags caught/missed/false | Expectations | "
      "Forbidden | Wall s | USD |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: (r["case"], r["pipeline"], r["repeat"])):
        if not r.get("scored"):
            w(f"| {r['case']} | {r['pipeline']} | {'yes' if r['candidate'] else 'no: ' + str(r.get('production_failure_stage'))} "
              f"| | | | | | | {r['wall_s']} | {r.get('usd_pipeline', 0) + r.get('usd_shared', 0):.3f} |")
            continue
        f = r["final"]
        fl = f["flags"]
        ex = f["expectations"]
        w(f"| {r['case']} | {r['pipeline']} | yes | {frac(*f['recall'])} | {frac(*f['precision'])} | "
          f"{frac(*f['critical'].get('tooth', [0, 0]))} | {len(fl['caught'])}/{len(fl['missed'])}/{len(fl['false_alarms'])} | "
          f"{sum(e['pass'] for e in ex)}/{len(ex)} | {', '.join(f['forbidden_hits']) or '—'} | {r['wall_s']} | "
          f"{r.get('usd_pipeline', 0) + r.get('usd_shared', 0):.3f} |")
    w("\n## Relationship correctness vs flag policy\n")
    w("Team relationships can suppress low target flags only when Cs passes; baseline relationships need a dentist "
      "confirmation. Relationship rows per run: " + "; ".join(
          f"{r['case']}/{r['pipeline']}: {r['relationships']}" for r in rows if r.get("relationships")) + "\n")
    w("## What this does and doesn't show\n")
    w("- It compares one single-extractor baseline with one team configuration on the same frozen sources and "
      "overlays. It measures split extraction + registry staging + Cs/Ce/Co checks together, not agent teams in "
      "general. No ablations yet, so causal claims stay modest.\n- 21 small synthetic cases, one run each: counts "
      "have wide uncertainty.\n- The gold and the Grader are not independent of the system's designer (both drafted "
      "by Claude); a person must check the gold, every critical-field grade, and every baseline/team disagreement "
      "(see grader_review.csv).\n- Audio/ASR quality and human review time are not measured yet.\n")
    (out_dir / "report.md").write_text("\n".join(L) + "\n", "utf-8")


def write_csv(rows, out_dir: Path):
    fields = ["case", "pipeline", "repeat", "session", "candidate", "production_failure_stage", "ready_for_review",
              "recall_n", "recall_d", "precision_n", "precision_d", "tooth_n", "tooth_d", "flags_caught", "flags_missed",
              "flags_false_alarms", "expectations_pass", "expectations_total", "calls", "usd_pipeline", "usd_shared",
              "wall_s", "error"]
    with open(out_dir / "results.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fields)
        wr.writeheader()
        for r in rows:
            f = r.get("final") or {}
            fl = f.get("flags") or {}
            ex = f.get("expectations") or []
            wr.writerow({**{k: r.get(k) for k in fields if k in r},
                         "recall_n": (f.get("recall") or [None, None])[0], "recall_d": (f.get("recall") or [None, None])[1],
                         "precision_n": (f.get("precision") or [None, None])[0], "precision_d": (f.get("precision") or [None, None])[1],
                         "tooth_n": (f.get("critical", {}).get("tooth") or [None, None])[0],
                         "tooth_d": (f.get("critical", {}).get("tooth") or [None, None])[1],
                         "flags_caught": len(fl.get("caught", [])) if fl else None,
                         "flags_missed": len(fl.get("missed", [])) if fl else None,
                         "flags_false_alarms": len(fl.get("false_alarms", [])) if fl else None,
                         "expectations_pass": sum(e["pass"] for e in ex) if f else None,
                         "expectations_total": len(ex) if f else None})


def write_grader_review(rows, out_dir: Path, fraction: float):
    """Every critical-field grade and every baseline/team disagreement, plus a 20% random sample of the rest."""
    from eval import scoring
    rnd = random.Random(7)
    out = []
    by_case = defaultdict(dict)
    for r in rows:
        if r.get("scored"):
            by_case[r["case"]][r["pipeline"]] = set(r["final"]["errors"])
    for r in rows:
        if not r.get("scored"):
            continue
        other = by_case[r["case"]].get("team" if r["pipeline"] == "baseline" else "baseline", set())
        for err in r["final"]["errors"]:
            dim = err.split(":", 1)[1]
            reason = "critical" if scoring.critical_bucket(dim) else ("disagreement" if err not in other else None)
            if reason or rnd.random() < fraction:
                out.append({"case": r["case"], "pipeline": r["pipeline"], "item": err, "why": reason or "sample",
                            "checked_by": "", "agrees": ""})
        for c in r.get("claims_detail") or []:
            if c["label"] in ("unsupported", "changed_meaning") or rnd.random() < fraction:
                out.append({"case": r["case"], "pipeline": r["pipeline"], "item": f"claim {c['claim_id']}: {c['label']}",
                            "why": "claim", "checked_by": "", "agrees": ""})
    with open(out_dir / "grader_review.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=["case", "pipeline", "item", "why", "checked_by", "agrees"])
        wr.writeheader()
        wr.writerows(out)


def load_rows(results_dir: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((results_dir / "runs").glob("*.json"))]


def rescore(results_dir: Path, out_dir: Path, only=None, client=None) -> list[dict]:
    """Re-score existing sessions (no pipeline re-run): e.g. to add Grader scores a run is missing."""
    from pipeline.storage import Session
    rows = []
    for row in load_rows(results_dir):
        if only and row["case"] not in only:
            continue
        s = Session(row["session"])
        new = {**row, **score_session(s, row["pipeline"], grade=True, client=client)}
        (out_dir / "runs").mkdir(parents=True, exist_ok=True)
        (out_dir / "runs" / f"{row['case']}__{row['pipeline']}__{row['repeat']}.json").write_text(
            json.dumps(new, indent=1, default=str))
        rows.append(new)
    return rows


def merge(base_dir: Path, patch_dirs: list[Path]) -> list[dict]:
    """Rows from base_dir, each replaced by the latest patch row for the same case/pipeline/repeat."""
    key = lambda r: (r["case"], r["pipeline"], r["repeat"])  # noqa: E731
    rows = {key(r): r for r in load_rows(base_dir)}
    for d in patch_dirs:
        for r in load_rows(d):
            rows[key(r)] = {**r, "merged_from": str(d.name)}
    return list(rows.values())


def finish(rows, out_dir: Path, prov: dict, title: str):
    write_csv(rows, out_dir)
    write_grader_review(rows, out_dir, yaml.safe_load((ROOT / "config" / "eval.yaml").read_text())["grader_sample_fraction"])
    write_report(rows, out_dir, prov, title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", default=["eval/cases"])
    ap.add_argument("--mode", default="text", choices=["text", "audio"])
    ap.add_argument("--pipeline", default="both", choices=["baseline", "team", "both"])
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--rule-mode", default="synthetic_demo")
    ap.add_argument("--no-grader", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--title", default="Evaluation report: baseline vs team")
    ap.add_argument("--only", nargs="*", default=None, help="case folder names to include")
    ap.add_argument("--rescore", default=None, help="re-score the sessions of an existing results dir (no pipeline run)")
    ap.add_argument("--merge", nargs="+", default=None, help="BASE PATCH...: combine results dirs, no model calls")
    args = ap.parse_args()
    if args.merge:
        out_dir = ROOT / (args.out or f"eval/results/merged-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = merge(ROOT / args.merge[0], [ROOT / d for d in args.merge[1:]])
        prov = {**json.loads((ROOT / args.merge[0] / "provenance.json").read_text()), "merged": args.merge}
        (out_dir / "provenance.json").write_text(json.dumps(prov, indent=1))
        finish(rows, out_dir, prov, args.title)
        print(f"report: {out_dir / 'report.md'}")
        return
    if args.mode == "audio":
        raise SystemExit("audio mode needs recordings and verified transcripts (stage 6 follow-up)")
    if any("heldout" in c for c in args.cases):
        from eval.freeze import check
        changed = check()
        if changed:
            raise SystemExit(f"held-out runs need the frozen evaluation configuration; changed: {changed[:5]}")
    case_dirs = []
    for c in args.cases:
        p = ROOT / c
        case_dirs += sorted(d for d in p.iterdir() if d.is_dir()) if p.is_dir() else []
    if args.only:
        case_dirs = [d for d in case_dirs if d.name in args.only]
    pipelines = ["baseline", "team"] if args.pipeline == "both" else [args.pipeline]
    out_dir = ROOT / (args.out or f"eval/results/{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    out_dir.mkdir(parents=True, exist_ok=True)
    GRADER_TRACE[0] = out_dir / "grader_traces.jsonl"
    prov = provenance()
    (out_dir / "provenance.json").write_text(json.dumps(prov, indent=1))
    if args.rescore:
        rows = rescore(ROOT / args.rescore, out_dir, args.only)
        finish(rows, out_dir, prov, args.title)
        print(f"report: {out_dir / 'report.md'}")
        return
    jobs = [(d, p, r) for d in case_dirs for p in pipelines for r in range(args.repeats)]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda j: run_one(j[0], j[1], j[2], out_dir, not args.no_grader, args.rule_mode), jobs))
    finish(rows, out_dir, prov, args.title)
    print(f"report: {out_dir / 'report.md'}")


if __name__ == "__main__":
    main()
