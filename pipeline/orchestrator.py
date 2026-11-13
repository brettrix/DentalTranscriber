"""Pipeline orchestration: Stages A-F for PIPELINE_MODE=baseline|team (section 4)."""
from __future__ import annotations

import json
import os
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from agents.base import AgentError
from pipeline import rules as rules_mod
from pipeline.flags import merge_flags, session_flag_actions
from pipeline.graph import load_graph, overwrite_graph, save_graph, snapshot_hash
from pipeline.highlights import highlights
from pipeline.linker import Staging, apply_revisions, commit_batch, convert_outputs, session_staging
from pipeline.overlays import load_sources
from pipeline.reconcile import add_conflicts, link_r2, link_tasks, r1_conflicts, r2_uncovered
from pipeline.relations import compute_target_relations
from pipeline.render import RenderError, note_markdown, render_note
from pipeline.repair import Issue, covered_by, cv_issues, dedupe, owner_for_entity, owner_for_type
from pipeline.stage_runs import StageRunLog, session_stage_log
from pipeline.status import compute_status
from pipeline.storage import Session, atomic_write_json, hash_obj, now, read_json
from pipeline.tasks import add_task, make_task
from pipeline.template import sections_owned
from pipeline.trace import Tracer, session_tracer
from pipeline.validate import validate_graph
from pipeline.verify import CheckLog, run_cv, session_check_log, summarize_all
from schemas.dispositions import SectionRecord
from schemas.entities import entity_section
from schemas.graph import Graph

MAX_CONCURRENT_CALLS = 4
TEAM_EXTRACTORS = ["B1", "B2", "B3", "B4"]


class RolesNotConfirmed(RuntimeError):
    pass


def default_agents():
    from agents.b0_extract import B0ExtractionAgent
    from agents.b1_history import B1MedicalHistoryAgent
    from agents.b2_complaint import B2ComplaintAgent
    from agents.b3_findings import B3FindingsAgent
    from agents.b4_plan import B4PlanAgent
    from agents.br_registry import BrRegistryAgent
    from agents.r2_contradictions import R2ContradictionAgent
    out = {"B0": B0ExtractionAgent, "Br": BrRegistryAgent, "B1": B1MedicalHistoryAgent, "B2": B2ComplaintAgent,
           "B3": B3FindingsAgent, "B4": B4PlanAgent, "R2": R2ContradictionAgent}
    try:
        from agents.cs_support import CsSupportAgent
        from agents.ce_equivalence import CeEquivalenceAgent
        from agents.co_omission import CoOmissionAgent
        out.update(Cs=CsSupportAgent, Ce=CeEquivalenceAgent, Co=CoOmissionAgent)
    except ImportError:
        pass
    try:
        from agents.e3_clinical_review import E3ClinicalReviewAgent
        out.update(E3=E3ClinicalReviewAgent)
    except ImportError:
        pass
    return out


@dataclass
class Run:
    session: Session
    mode: str
    rule_mode: str
    run_id: str
    sources: object
    tracer: Tracer
    stage_log: StageRunLog
    check_log: CheckLog
    staging: Staging
    previous: Graph | None
    agents: dict
    client: object = None
    graph: Graph | None = None
    r2_findings: list[dict] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    stage_tasks: list = field(default_factory=list)
    linker_version: int | None = None

    def agent(self, name):
        return self.agents[name](client=self.client, tracer=self.tracer)

    def note(self, msg):
        self.log.append(msg)
        if os.environ.get("SCRIBE_VERBOSE"):
            print(f"[{self.mode}] {msg}", flush=True)

    def record(self, stage, agent, status, *, error=None, blocked_by=None, inputs=None, started=None, extra=None):
        rec = self.stage_log.record(stage, agent, status, error=error, blocked_by=blocked_by,
                                    inputs_hash=hash_obj(inputs if inputs is not None else self.sources.hashes)[:16],
                                    started=started, run_id=self.run_id, extra=extra)
        if status == "failed":
            task = make_task("stage_failure", f"{stage} {agent} failed: {error}", created_by_stage=stage,
                             severity="high", stage_run_id=rec["id"], key=f"{stage}/{agent}/{rec['inputs_hash']}")
            self.stage_tasks.append(task)
        self.note(f"{stage}/{agent}: {status}" + (f" ({error})" if error else ""))
        return rec


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:300]}"


# ---------------------------------------------------------------- entry point

def run_pipeline(session: Session, *, mode: str | None = None, rule_mode: str | None = None, client=None,
                 agents: dict | None = None) -> dict:
    mode = mode or session.meta().get("pipeline_mode") or os.environ.get("PIPELINE_MODE", "team")
    rule_mode = rule_mode or session.meta().get("rule_mode") or os.environ.get("RULE_MODE", "synthetic_demo")
    assert mode in ("baseline", "team") and rule_mode in ("synthetic_demo", "office")
    with session.lock():
        sources = load_sources(session)
        if not sources.roles.confirmed:
            raise RolesNotConfirmed("speaker roles must be confirmed before extraction")
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        previous = load_graph(session)
        run = Run(session=session, mode=mode, rule_mode=rule_mode, run_id=run_id, sources=sources,
                  tracer=session_tracer(session, run_id=run_id), stage_log=session_stage_log(session),
                  check_log=session_check_log(session), staging=session_staging(session), previous=previous,
                  agents=agents or default_agents(), client=client)
        session.update_meta(pipeline_mode=mode, rule_mode=rule_mode, last_run=run_id)
        started = now()
        run.record("A", "T0", "succeeded", inputs=sources.hashes)
        if previous is not None and not previous.stale:
            previous.stale = True
            for e in previous.entities:
                if e.status == "active":
                    e.status = "stale"
            overwrite_graph(session, previous)
        stage_b(run)
        if run.graph is not None:
            stage_c(run)
            stage_d(run)
            run.graph.frozen = True
            errs = validate_graph(run.graph)
            if errs:
                run.record("D", "freeze", "failed", error="; ".join(errs[:3]))
                run.graph = None
            else:
                run.graph = save_graph(session, run.graph)
                run.tracer.graph_version = run.graph.version
                run.record("D", "freeze", "succeeded", inputs={"graph": snapshot_hash(run.graph)})
        else:
            for agent in ("Cv", "R2") + (("Cs", "Ce", "Co") if mode == "team" else ()):
                run.record("C", agent, "blocked", blocked_by="L/Linker")
            run.record("C", "repair", "blocked", blocked_by="L/Linker")
            run.record("D", "reconcile", "blocked", blocked_by="L/Linker")
        run.staging.tasks = [t.model_dump(mode="json") for t in run.stage_tasks] if run.graph is None else []
        run.staging.save()
        result = derive(session, run.graph, sources, mode, rule_mode, run_id=run_id, run=run)
        state = {"run_id": run_id, "mode": mode, "rule_mode": rule_mode, "started": started, "finished": now(),
                 "graph_version": run.graph.version if run.graph else None,
                 "linker_graph_version": run.linker_version,
                 "r2_findings": run.r2_findings, "issues": [i.to_dict() for i in run.issues], "log": run.log,
                 "trace_totals": run.tracer.totals()}
        atomic_write_json(session.path("runs", f"{run_id}.json"), state)
        if run.graph is not None:
            from pipeline.approval import revoke_if_changed
            revoke_if_changed(session, reason=f"pipeline rerun {run_id}")
        return {**result, "run": state}


# ---------------------------------------------------------------- Stage B

def stage_b(run: Run) -> None:
    from pipeline import human
    outputs: list[tuple[str, object]] = []
    status: dict[str, str] = {}
    graph = Graph(pipeline_mode=run.mode, overlay_versions=run.sources.overlay_versions,
                  source_hashes=run.sources.hashes)
    # 6.11: human-entered entities carry over unchanged (a human-entered registry included).
    human.carry_into(run.session, graph, run.previous, run.sources)
    human_chief = graph.chief()
    if run.mode == "baseline":
        agent = run.agent("B0")
        st = now()
        try:
            outputs.append(("B0", agent.extract(run.sources)))
            status["B0"] = "succeeded"
            run.record("B", "B0", "succeeded", started=st)
        except (AgentError, Exception) as exc:  # noqa: BLE001 - every failure gets a record and a task
            status["B0"] = "failed"
            run.record("B", "B0", "failed", error=_err(exc), started=st)
        registry_owner = "B0"
    else:
        registry_owner = "Br"
        st = now()
        br_out, br_rec, registry = None, None, None
        if human_chief is not None:
            # A human-entered registry replaces Br (10.1: once it is saved, B2-B4 run and the batch commits).
            run.record("B", "Br", "not_applicable", extra={"reason": "human-entered registry"})
            registry = _registry_text_from_graph(graph)
        else:
            try:
                br_out = run.agent("Br").extract(run.sources)
                outputs.append(("Br", br_out))
                status["Br"] = "succeeded"
                br_rec = run.record("B", "Br", "succeeded", started=st)
            except Exception as exc:  # noqa: BLE001
                status["Br"] = "failed"
                br_rec = run.record("B", "Br", "failed", error=_err(exc), started=st)
            from agents.extract_common import registry_text
            if br_out:
                registry = registry_text([p.model_dump(mode="json") for p in br_out.problems],
                                         [r.model_dump(mode="json") for r in br_out.relationships])
        runnable = TEAM_EXTRACTORS if registry is not None else ["B1"]
        for name in TEAM_EXTRACTORS:
            if name not in runnable:
                status[name] = "blocked"
                run.record("B", name, "blocked", blocked_by=br_rec["id"] if br_rec else "B/Br")

        def call(name):
            st_ = now()
            try:
                return name, run.agent(name).extract(run.sources, registry), None, st_
            except Exception as exc:  # noqa: BLE001
                return name, None, exc, st_

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CALLS) as pool:
            for name, out, exc, st_ in pool.map(call, runnable):
                if exc is None:
                    outputs.append((name, out))
                    status[name] = "succeeded"
                    run.record("B", name, "succeeded", started=st_)
                else:
                    status[name] = "failed"
                    run.record("B", name, "failed", error=_err(exc), started=st_)
    # Linker
    entities, staged = convert_outputs(outputs, run.sources, graph, run.previous, registry_owner, run.run_id,
                                       human_chief_id=human_chief.id if human_chief else None)
    committed, uncommitted = commit_batch(graph, entities, staged, run.sources, run.previous,
                                          overrides=human.human_overrides(run.session))
    for rec in staged:
        run.staging.add(rec)
    chief_ok = graph.chief() is not None
    if not chief_ok:
        run.record("L", "Linker", "failed", error="no valid graph: " + "; ".join(
            (uncommitted[0].errors[-1:] if uncommitted and uncommitted[0].errors else ["no chief problem"])))
        run.graph = None
        return
    human.after_commit(run.session, graph, run.previous, committed, run.sources)
    run.record("L", "Linker", "succeeded", extra={"committed": len(committed), "staged": len(uncommitted)})
    # Section records: every section each extractor owns, even with zero entities.
    for agent_name, st_ in status.items():
        owned = sections_owned(agent_name) if agent_name != "Br" else ["chief_complaint"]
        for sec in owned:
            n = sum(1 for e in committed if entity_section(e) == sec)
            sstatus = {"succeeded": "completed", "failed": "failed", "blocked": "not_run"}[st_]
            graph.section_records.append(SectionRecord(section=sec, owner=agent_name, status=sstatus, entities=n,
                                                       version=_section_version(run.previous, sec, sstatus, n)))
    if human_chief is not None and run.mode == "team":
        graph.section_records.append(SectionRecord(section="chief_complaint", owner="human", status="completed",
                                                   entities=len(graph.active("problem"))))
    human.carry_section_dispositions(graph, run.previous)
    for rec in uncommitted:
        task = make_task("staged_record", f"{rec.owner} {rec.kind} not committed: {'; '.join(rec.errors)[:400]}",
                         created_by_stage="L", severity="medium", staging_ids=[rec.id])
        rec.task_id = task.id
        add_task(graph, task, run.previous)
    run.graph = save_graph(run.session, graph)
    run.linker_version = run.graph.version
    run.tracer.graph_version = run.graph.version


def _section_version(previous, section, status, n) -> int:
    if previous is None:
        return 1
    prev = next((s for s in previous.section_records if s.section == section), None)
    if prev is None:
        return 1
    return prev.version if (prev.status, prev.entities) == (status, n) else prev.version + 1


# ---------------------------------------------------------------- Stage C

def stage_c(run: Run) -> None:
    g = run.graph
    sources = run.sources
    owner_of = lambda e: owner_for_entity(e, run.mode)  # noqa: E731
    source_backed = [e for e in g.active() if not e.is_human]
    st = now()
    cv = run_cv(source_backed, sources, run.check_log, attempt=1, run_id=run.run_id)
    run.record("C", "Cv", "succeeded", started=st)
    issues = cv_issues(g, cv, owner_of)
    sem_config = None
    team = None
    if run.mode == "team":
        from pipeline import compare as team
        sem_config, sem_issues = team.run_semantic(run, source_backed, attempt=1)
        issues += sem_issues
        issues += team.run_omission(run, attempt=1)
    # R2 detection
    st = now()
    try:
        out = run.agent("R2").detect(sources)
        run.r2_findings = [f.model_dump(mode="json", by_alias=True) for f in out.findings]
        run.record("C", "R2", "succeeded", started=st)
        for f, missing in r2_uncovered(g, run.r2_findings, sources):
            issues.append(Issue(kind="omission", owner=owner_for_type(f.get("suggested_type"), run.mode),
                                details=f"R2 {f['kind']} about {f.get('subject')}: no entity covers this statement",
                                evidence=[{"source_type": s.source_type, "source_id": s.source_id, "quote": s.text}
                                          for s in missing], origin="R2", suggested_type=f.get("suggested_type")))
    except Exception as exc:  # noqa: BLE001
        run.record("C", "R2", "failed", error=_err(exc), started=st)
    issues = dedupe(issues)
    run.issues = issues
    summarize_all(g, run.check_log, run.mode, sem_config)
    # One repair round, grouped by owning agent.
    st = now()
    repaired = repair_round(run, issues)
    run.record("C", "repair", "succeeded" if repaired is not None else "not_applicable", started=st,
               extra={"issues": len(issues), "changed": len(repaired or [])})
    if repaired:
        run_cv(repaired, sources, run.check_log, attempt=2, run_id=run.run_id)
        if team is not None:
            team.run_semantic(run, repaired, attempt=2)
            team.run_omission(run, attempt=2, sections={entity_section(e) for e in repaired})
    summarize_all(g, run.check_log, run.mode, sem_config)
    _remaining_issue_tasks(run)
    run.graph = save_graph(run.session, g)
    run.tracer.graph_version = run.graph.version


def repair_round(run: Run, issues: list[Issue]):
    g = run.graph
    by_owner: dict[str, list[Issue]] = {}
    for i in issues:
        by_owner.setdefault(i.owner, []).append(i)
    if not issues:
        return None
    changed = []
    registry_text_ = _registry_text_from_graph(g) if run.mode == "team" else None
    jobs = [(o, iss) for o, iss in by_owner.items() if o in run.agents and o not in ("registry", "unassigned")]

    def call(job):
        owner, iss = job
        ids = {i.entity_id for i in iss if i.entity_id}
        ents = [_entity_for_agent(g.get(eid)) for eid in ids if g.get(eid) is not None]
        try:
            return owner, run.agent(owner).repair(run.sources, [i.for_agent() for i in iss], ents,
                                                  registry_text_), None
        except Exception as exc:  # noqa: BLE001
            return owner, None, exc

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CALLS) as pool:
        results = list(pool.map(call, jobs))
    for owner, out, exc in results:
        if exc is not None:
            run.record("C", f"repair/{owner}", "failed", error=_err(exc))
            continue
        revised_out = [x for x in out.items if x.id and g.get(x.id) is not None]
        new_out = [x for x in out.items if not (x.id and g.get(x.id) is not None)]
        registry_owner = "B0" if run.mode == "baseline" else "Br"
        rev_entities, rev_staged = convert_outputs([(owner, _Items(revised_out))], run.sources, g, None,
                                                   registry_owner, run.run_id)
        for rec in rev_staged:
            run.staging.add(rec)
        from pipeline.validate import validate_entity
        ok = [e for e in rev_entities if not validate_entity(e)]
        changed += apply_revisions(g, ok, run.sources)
        new_entities, new_staged = convert_outputs([(owner, _Items(new_out))], run.sources, g, run.previous,
                                                   registry_owner, run.run_id)
        committed, uncommitted = commit_batch(g, new_entities, new_staged, run.sources, run.previous)
        for rec in new_staged:
            run.staging.add(rec)
        for rec in uncommitted:
            task = make_task("staged_record", f"{rec.owner} repair output not committed: {'; '.join(rec.errors)[:400]}",
                             created_by_stage="C", staging_ids=[rec.id])
            rec.task_id = task.id
            add_task(g, task, run.previous)
        changed += committed
        for sec in {entity_section(e) for e in committed}:
            rec = next((s for s in g.section_records if s.section == sec), None)
            if rec is not None:
                rec.entities += sum(1 for e in committed if entity_section(e) == sec)
    return changed


class _Items:
    def __init__(self, items):
        self.items = items


def _entity_for_agent(e) -> dict:
    d = e.model_dump(mode="json", by_alias=True, exclude={"content_hash", "support_hash", "checks", "dispositions",
                                                           "status", "speaker_ids", "roles", "superseded_by",
                                                           "supersede_reason", "target_relation"})
    d["key"] = (e.local_key or e.id).split(":")[-1]
    d["evidence"] = [{"source_type": s["source_type"], "source_id": s["source_id"], "quote": s["text"]}
                     for s in d["evidence"]]
    return d


def _registry_text_from_graph(g) -> str:
    from agents.extract_common import registry_text
    probs = [{"key": p.id, "role": p.role, "complaint_text": p.complaint_text,
              "complaint_location": p.complaint_location.model_dump(), "clinical_target": p.clinical_target.model_dump()}
             for p in g.active("problem")]
    rels = [{"tooth": r.tooth, "relation_kind": r.relation_kind, "problem_key": r.problem_id}
            for r in g.active("relationship")]
    return registry_text(probs, rels)


def _remaining_issue_tasks(run: Run) -> None:
    """After the repair budget, open issues become human-review tasks (failed checks stay failed)."""
    g = run.graph
    for i in run.issues:
        if i.entity_id:
            e = g.get(i.entity_id)
            if e is None or e.status != "active":
                continue
            still = any(v in ("fail", "unconfirmed", "not_assessed_due_to_failure") for v in
                        (e.checks.span_valid, e.checks.normalization_valid, e.checks.semantic_support))
            if not still:
                continue
            kind = "registry_issue" if i.owner == "registry" else "check_failure"
            sev = "high" if i.owner == "registry" else "medium"
            add_task(g, make_task(kind, f"{i.details[:400]}", participants=[e], created_by_stage="C",
                                  severity=sev, key=i.id), run.previous)
        else:
            from schemas.entities import Span
            spans = []
            for ev in i.evidence:
                s = Span(source_type=ev["source_type"], source_id=ev["source_id"], text=ev.get("quote", ""))
                from pipeline.verify import locate_span
                locate_span(s, run.sources)
                spans.append(s)
            if spans and all(covered_by(g, s.source_type, s.source_id, s.start, s.end) for s in spans):
                continue
            kind = "registry_issue" if i.owner == "registry" else "omission"
            add_task(g, make_task(kind, i.details[:400], evidence=spans, created_by_stage="C",
                                  severity="high" if kind == "registry_issue" else "medium", key=i.id), run.previous)


# ---------------------------------------------------------------- Stage D

def stage_d(run: Run) -> None:
    g = run.graph
    st = now()
    reconcile_graph(g, run.sources, run.mode, run.r2_findings, run.previous)
    for t in run.stage_tasks:
        add_task(g, t, run.previous)
    run.stage_tasks = []
    run.record("D", "reconcile", "succeeded", started=st)


def reconcile_graph(g: Graph, sources, mode: str, r2_findings: list[dict], previous: Graph | None) -> None:
    """Python-only, derived records: target relations, R1 and R2 conflicts, link tasks. Also run after edits."""
    compute_target_relations(g, mode)
    add_conflicts(g, r1_conflicts(g), previous)
    add_conflicts(g, link_r2(g, r2_findings, sources, previous), previous)
    link_tasks(g, previous)
    from pipeline.human import apply_carried_resolutions
    apply_carried_resolutions(g)


# ---------------------------------------------------------------- Stages E and F

def derive(session: Session, graph: Graph | None, sources, mode: str, rule_mode: str, *, run_id: str | None = None,
           run: Run | None = None, client=None, agents=None, retry_e3: bool = False) -> dict:
    """E0-E3 and F from one frozen graph version. Also run after every human edit."""
    stage_log = run.stage_log if run else session_stage_log(session)
    run_id = run_id or session.meta().get("last_run")
    failures: list[dict] = []

    def record(stage, agent, status, error=None, blocked_by=None, extra=None):
        inputs = {"graph": snapshot_hash(graph)} if graph is not None else {}
        rec = stage_log.record(stage, agent, status, error=error, blocked_by=blocked_by, run_id=run_id,
                               inputs_hash=hash_obj(inputs)[:16], extra=extra)
        if run is not None:
            run.note(f"{stage}/{agent}: {status}" + (f" ({error})" if error else ""))
        if status == "failed":
            failures.append(rec)
        return rec

    out = {"graph_version": graph.version if graph else None, "note": None, "flags": [], "notices": [],
           "highlights": [], "status": None, "candidate": graph is not None}
    if graph is None:
        for agent in ("E0", "E1", "E2", "E3"):
            record("E", agent, "blocked", blocked_by="L/Linker")
        out["status"] = compute_status(None, stage_log.for_run(run_id), [], mode, rule_mode, [])
        record("F", "status", "succeeded")
        atomic_write_json(session.path("outputs", "latest.json"), {**out, "flags": []})
        return out
    flags, notices = [], []
    from pipeline import clinical_review
    e3_flags, e3_notices = clinical_review.run_e3(session, graph, sources, mode, rule_mode,
                                                  client=client or (run.client if run else None),
                                                  agents=agents or (run.agents if run else None),
                                                  tracer=run.tracer if run else session_tracer(session, graph.version),
                                                  record=record, run_id=run_id, retry=retry_e3)
    graph = _add_failure_tasks(session, graph, failures)
    try:
        note = render_note(graph, sources, mode)
        record("E", "E0", "succeeded")
    except Exception as exc:  # noqa: BLE001 - RenderError or a bug: either way no valid candidate
        note = None
        record("E", "E0", "failed", error=_err(exc))
    out["note"] = note
    staging = session_staging(session)
    try:
        ctx = rules_mod.RuleContext(graph=graph, mode=mode, rule_mode=rule_mode, sources=sources,
                                    stage_runs=stage_log.for_run(run_id), staging_open=staging.open_records())
        flags, notices = rules_mod.run_rules(ctx)
        record("E", "E2", "succeeded")
    except Exception as exc:  # noqa: BLE001
        record("E", "E2", "failed", error=_err(exc))
        traceback.print_exc()
    flags = merge_flags(flags + e3_flags)
    notices += e3_notices
    session_flag_actions(session).apply(flags)
    out.update(graph_version=graph.version, flags=flags, notices=notices, highlights=highlights(graph, flags))
    record("E", "E1", "succeeded")
    out["status"] = compute_status(graph, stage_log.for_run(run_id), flags, mode, rule_mode, _expected_stages(mode))
    out["status"]["candidate"] = note is not None
    record("F", "status", "succeeded")
    payload = {**out, "flags": [f.model_dump(mode="json") for f in flags],
               "snapshot_hash": snapshot_hash(graph), "markdown": note_markdown(note) if note else None,
               "staged_open": len(staging.open_records())}
    atomic_write_json(session.path("outputs", f"derived_v{graph.version}.json"), payload)
    atomic_write_json(session.path("outputs", "latest.json"), payload)
    return out


def _add_failure_tasks(session: Session, graph: Graph, failures: list[dict]) -> Graph:
    """Every failed stage creates a task (invariant 9). Adding it is a graph change: a new version."""
    if not failures:
        return graph
    g = graph.model_copy(deep=True)
    for rec in failures:
        add_task(g, make_task("stage_failure", f"{rec['stage']} {rec['agent']} failed: {rec.get('error')}",
                              created_by_stage=rec["stage"], severity="medium", stage_run_id=rec["id"],
                              key=rec["id"]),
                 graph)
    if validate_graph(g):
        return graph
    return save_graph(session, g)


def _expected_stages(mode: str) -> list[str]:
    base = ["A/T0", "L/Linker", "C/Cv", "C/R2", "C/repair", "D/reconcile", "D/freeze", "E/E3", "E/E0", "E/E2",
            "E/E1"]
    if mode == "baseline":
        return base + ["B/B0"]
    return base + ["B/Br", "B/B1", "B/B2", "B/B3", "B/B4", "C/Cs", "C/Ce", "C/Co"]


def load_latest(session: Session) -> dict | None:
    return read_json(session.path("outputs", "latest.json"))
