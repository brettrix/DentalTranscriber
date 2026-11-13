"""Human correction (section 11): item editor, dispositions, conflict resolution, pending critical changes,
staged-record conversion, and carrying human assertions across reruns (6.11).

Every graph-changing action: apply in memory -> structural validation -> new graph version -> Stages D, E, F.
"""
from __future__ import annotations

import copy
import uuid

from pipeline.dispositions import (add_entity_disposition, entity_hashes, make_disposition)
from pipeline.graph import ENTITY_ADAPTER, load_graph, rehash_all, save_graph
from pipeline.storage import atomic_write_json, hash_obj, now, read_json
from pipeline.validate import StructuralError, validate_graph
from schemas.conflicts import Participant, Resolution
from schemas.dispositions import PendingChange
from schemas.entities import Span, is_critical

ROLES = ("Assistant", "Dentist")


class HumanActionError(ValueError):
    pass


# ---------------------------------------------------------------- human assertions store

def _assertions_path(session):
    return session.path("human_assertions.json")


def load_assertions(session) -> list[dict]:
    return read_json(_assertions_path(session), [])


def _save_assertion(session, assertion: dict) -> dict:
    data = load_assertions(session)
    assertion = {"id": f"ha_{uuid.uuid4().hex[:10]}", "timestamp": now(), **assertion}
    data.append(assertion)
    atomic_write_json(_assertions_path(session), data)
    return assertion


# ---------------------------------------------------------------- helpers

def human_span(role: str, reason: str) -> Span:
    text = f"Entered by {role}: {reason or 'no reason given'}"
    return Span(source_type="human_entry", source_id=f"{role.lower()}_entry", source_version=1, start=None, end=None,
                text=text)


def _new_human_entity(data: dict, role: str, reason: str, assertion_source: str | None = None):
    data = copy.deepcopy(data)
    for k in ("content_hash", "support_hash", "checks", "dispositions", "superseded_by", "supersede_reason",
              "target_relation"):
        data.pop(k, None)
    data["owner"] = "human"
    data["status"] = "active"
    data["evidence"] = [human_span(role, reason).model_dump()]
    data["derivations"] = []
    data["speaker_ids"], data["roles"] = [], []
    if assertion_source:
        data["assertion_source"] = assertion_source
    e = ENTITY_ADAPTER.validate_python(data)
    e.checks.span_valid = e.checks.normalization_valid = e.checks.semantic_support = "not_applicable"
    return e


ENTITY_TASKS = ("check_failure", "registry_issue", "human_override_check")


def _complete_entity_tasks(g, entity_id: str, completion: str, role: str, reason: str, cites=()) -> None:
    """A person settling an entity (confirming, correcting or removing it) also completes the open review tasks
    raised about that entity. Each gets its own task_completed disposition bound to the task's inputs_hash."""
    for t in g.tasks:
        if t.status == "open" and t.kind in ENTITY_TASKS and any(p.entity_id == entity_id for p in t.participants):
            d = make_disposition("task", t.id, {"inputs_hash": t.inputs_hash}, "task_completed", role,
                                 f"settled with the entity: {reason}", completion=completion, cites=list(cites))
            g.dispositions.append(d)
            t.status, t.disposition_id = "completed", d.id


def _critical_content(*entities) -> bool:
    return any(e is not None and is_critical(e) for e in entities)


def _next_item_id(graph, kind: str) -> str:
    from pipeline.graph import new_id, next_ids
    return new_id(next_ids(graph), kind)


# ---------------------------------------------------------------- commit pipeline for human actions

def commit_human_change(session, graph, *, reason: str, client=None, agents=None, rerun_cs_for_problem=False):
    """Validate, save a new version, re-run D, E, F (and Cs on problem-scoped entities after a team-mode
    problem/relationship edit). Raises StructuralError and commits nothing if validation fails."""
    from pipeline.approval import revoke_if_changed
    from pipeline.orchestrator import derive, reconcile_graph
    from pipeline.overlays import load_sources
    from pipeline.verify import session_check_log, summarize_all
    sources = load_sources(session)
    rehash_all(graph, sources.roles)
    errs = validate_graph(graph)
    if errs:
        raise StructuralError(errs)
    mode = graph.pipeline_mode
    log = session_check_log(session)
    from pipeline.verify import CV_CONFIG_HASH, run_cv
    stale_cv = [e for e in graph.active() if not e.is_human and log.latest(e, "span_valid", CV_CONFIG_HASH) is None]
    if stale_cv:
        run_cv(stale_cv, sources, log, attempt=3, run_id=session.meta().get("last_run"))
    sem_config = None
    if mode == "team":
        from pipeline.compare import run_semantic, semantic_config_hash
        run = _MiniRun(session, graph, sources, client, agents)
        run.check_log = log
        sem_config = semantic_config_hash(run)
        targets = [e for e in graph.active() if not e.is_human and
                   log.latest(e, "semantic_support", sem_config) is None]
        if rerun_cs_for_problem:
            targets = [e for e in graph.active() if not e.is_human and
                       (e.kind == "relationship" or (e.kind == "item" and e.scope == "problem"))]
        if targets:
            run_semantic(run, targets, attempt=3)
    summarize_all(graph, log, mode, sem_config)
    latest_run = read_json(session.path("runs", f"{session.meta().get('last_run')}.json"), {}) or {}
    previous = load_graph(session)
    reconcile_graph(graph, sources, mode, latest_run.get("r2_findings", []), previous)
    graph.frozen = True
    errs = validate_graph(graph)
    if errs:
        raise StructuralError(errs)
    graph = save_graph(session, graph)
    result = derive(session, graph, sources, mode, session.meta().get("rule_mode", "synthetic_demo"),
                    client=client, agents=agents)
    revoke_if_changed(session, reason=reason)
    return graph, result


class _MiniRun:
    """Enough of an orchestrator Run for run_semantic outside a pipeline run."""

    def __init__(self, session, graph, sources, client, agents):
        from pipeline.orchestrator import default_agents
        from pipeline.stage_runs import session_stage_log
        from pipeline.trace import session_tracer
        from pipeline.verify import session_check_log
        self.session, self.graph, self.sources, self.client = session, graph, sources, client
        self.agents = agents or default_agents()
        self.mode = graph.pipeline_mode
        self.run_id = session.meta().get("last_run")
        self.tracer = session_tracer(session, graph.version, self.run_id)
        self.stage_log = session_stage_log(session)
        self.check_log = session_check_log(session)
        self.issues = []

    def agent(self, name):
        return self.agents[name](client=self.client, tracer=self.tracer)

    def record(self, stage, agent, status, error=None, started=None, extra=None, **_):
        return self.stage_log.record(stage, agent, status, error=error, started=started, run_id=self.run_id,
                                     extra=extra)


def _working_graph(session):
    g = load_graph(session)
    if g is None:
        raise HumanActionError("no graph yet")
    if g.stale:
        raise HumanActionError("this graph version is stale; reload the latest")
    g = g.model_copy(deep=True)
    g.frozen = False
    return g


def _check_role(role):
    if role not in ROLES:
        raise HumanActionError(f"role must be one of {ROLES}")


# ---------------------------------------------------------------- item editor

def _pending(graph, operation, role, reason, targets=(), content=None, conflict_id=None) -> PendingChange:
    pc = PendingChange(id=f"pc_{uuid.uuid4().hex[:8]}", operation=operation,
                       target_versions=[Participant(entity_id=t.id, version=t.version) for t in targets],
                       proposed_content=content, conflict_id=conflict_id, by_role="Assistant", reason=reason,
                       timestamp=now())
    graph.pending_changes.append(pc)
    return pc


def edit_entity(session, entity_id: str, changes: dict, role: str, reason: str, *, client=None, agents=None):
    """Edit: a new human-entered version supersedes the old one. Critical content by an Assistant is pending."""
    _check_role(role)
    g = _working_graph(session)
    old = g.get(entity_id)
    if old is None or old.status != "active":
        raise HumanActionError(f"{entity_id} is not an active entity")
    data = old.model_dump(mode="json", by_alias=True)
    _deep_update(data, changes)
    new = _new_human_entity(data, role, reason, changes.get("assertion_source"))
    new.id = old.id
    new.version = max(e.version for e in g.entities if e.id == old.id) + 1
    if role == "Assistant" and _critical_content(old, new):
        _pending(g, "edit", role, reason, [old], content=changes)
        return commit_human_change(session, g, reason=f"pending edit of {entity_id}", client=client, agents=agents)
    _apply_edit(g, old, new, role, reason, _roles(session))
    _save_assertion(session, {"operation": "edit", "entity_id": old.id, "replaced_versions": [old.version],
                              "replaced_content_hash": old.content_hash, "entity": new.model_dump(mode="json",
                                                                                                  by_alias=True),
                              "by_role": role, "reason": reason})
    return commit_human_change(session, g, reason=f"edit {entity_id}", client=client, agents=agents,
                               rerun_cs_for_problem=old.kind in ("problem", "relationship"))


def _apply_edit(g, old, new, role, reason, roles):
    old.status = "superseded"
    old.superseded_by = new.ref
    old.supersede_reason = f"edited by {role}: {reason}"
    g.entities.append(new)
    rehash_all(g, roles)
    _complete_entity_tasks(g, old.id, "corrected", role, reason)
    add_entity_disposition(g, new, "dentist_confirmed" if role == "Dentist" and is_critical(new) else
                           "human_entered", role, reason)
    if role == "Dentist" and is_critical(new):
        add_entity_disposition(g, new, "human_entered", role, reason)


def _roles(session):
    from pipeline.overlays import load_roles
    return load_roles(session)


def add_entity(session, data: dict, role: str, reason: str, *, client=None, agents=None):
    """Add a human-entry entity (problem, relationship or item)."""
    _check_role(role)
    g = _working_graph(session)
    data = dict(data)
    data.setdefault("id", _next_item_id(g, data.get("kind", "item")))
    new = _new_human_entity(data, role, reason, data.get("assertion_source"))
    if role == "Assistant" and _critical_content(new):
        _pending(g, "add", role, reason, content=new.model_dump(mode="json", by_alias=True))
        return commit_human_change(session, g, reason="pending add", client=client, agents=agents)
    g.entities.append(new)
    rehash_all(g, _roles(session))
    _dispose_new(g, new, role, reason)
    _save_assertion(session, {"operation": "add", "entity_id": new.id,
                              "entity": new.model_dump(mode="json", by_alias=True), "by_role": role, "reason": reason})
    return commit_human_change(session, g, reason=f"add {new.id}", client=client, agents=agents,
                               rerun_cs_for_problem=new.kind in ("problem", "relationship"))


def _dispose_new(g, new, role, reason):
    add_entity_disposition(g, new, "human_entered", role, reason)
    if role == "Dentist" and is_critical(new):
        add_entity_disposition(g, new, "dentist_confirmed", role, reason)


def remove_entity(session, entity_id: str, role: str, reason: str, *, client=None, agents=None):
    _check_role(role)
    if not reason:
        raise HumanActionError("removal needs a reason")
    g = _working_graph(session)
    old = g.get(entity_id)
    if old is None or old.status != "active":
        raise HumanActionError(f"{entity_id} is not an active entity")
    if role == "Assistant" and _critical_content(old):
        _pending(g, "remove", role, reason, [old])
        return commit_human_change(session, g, reason=f"pending removal of {entity_id}", client=client, agents=agents)
    _apply_remove(g, old, role, reason)
    _save_assertion(session, {"operation": "remove", "entity_id": old.id, "replaced_versions": [old.version],
                              "replaced_content_hash": old.content_hash, "by_role": role, "reason": reason})
    return commit_human_change(session, g, reason=f"remove {entity_id}", client=client, agents=agents,
                               rerun_cs_for_problem=old.kind in ("problem", "relationship"))


def _apply_remove(g, old, role, reason):
    old.status = "superseded"
    old.superseded_by = f"human:{role}"
    old.supersede_reason = f"removed by {role}: {reason}"
    _complete_entity_tasks(g, old.id, "corrected", role, reason)


def _deep_update(data: dict, changes: dict):
    for k, v in changes.items():
        if isinstance(v, dict) and isinstance(data.get(k), dict):
            _deep_update(data[k], v)
        else:
            data[k] = v


# ---------------------------------------------------------------- pending changes

def decide_pending(session, pending_id: str, accept: bool, role: str, reason: str = "", *, client=None, agents=None):
    if role != "Dentist":
        raise HumanActionError("only the Dentist accepts or rejects pending critical changes")
    g = _working_graph(session)
    pc = next((p for p in g.pending_changes if p.id == pending_id and p.status == "pending"), None)
    if pc is None:
        raise HumanActionError("no such pending change")
    if not accept:
        pc.status = "rejected"
        return commit_human_change(session, g, reason=f"reject {pending_id}", client=client, agents=agents)
    pc.status = "accepted"
    why = f"{pc.reason} (assistant proposal, accepted by Dentist{': ' + reason if reason else ''})"
    if pc.operation == "add":
        new = _new_human_entity(pc.proposed_content, "Assistant", pc.reason)
        g.entities.append(new)
        rehash_all(g, _roles(session))
        add_entity_disposition(g, new, "human_entered", "Assistant", pc.reason)
        add_entity_disposition(g, new, "dentist_confirmed", "Dentist", why)
        _save_assertion(session, {"operation": "add", "entity_id": new.id, "by_role": "Dentist", "reason": why,
                                  "entity": new.model_dump(mode="json", by_alias=True)})
    elif pc.operation in ("edit", "remove"):
        tv = pc.target_versions[0]
        old = g.get(tv.entity_id, tv.version)
        if old is None or old.status != "active":
            raise HumanActionError("the target changed since the proposal; it no longer applies")
        if pc.operation == "remove":
            _apply_remove(g, old, "Dentist", why)
            _save_assertion(session, {"operation": "remove", "entity_id": old.id, "replaced_versions": [old.version],
                                      "replaced_content_hash": old.content_hash, "by_role": "Dentist", "reason": why})
        else:
            data = old.model_dump(mode="json", by_alias=True)
            _deep_update(data, pc.proposed_content or {})
            new = _new_human_entity(data, "Assistant", pc.reason)
            new.id, new.version = old.id, max(e.version for e in g.entities if e.id == old.id) + 1
            _apply_edit(g, old, new, "Dentist", why, _roles(session))
            _save_assertion(session, {"operation": "edit", "entity_id": old.id, "replaced_versions": [old.version],
                                      "replaced_content_hash": old.content_hash, "by_role": "Dentist", "reason": why,
                                      "entity": new.model_dump(mode="json", by_alias=True)})
    elif pc.operation == "resolve_conflict":
        c = g.conflict(pc.conflict_id)
        payload = dict(pc.proposed_content or {})
        replacement = payload.pop("replacement", None)
        payload["pending_change_id"] = None
        _apply_resolution(g, c, Resolution.model_validate(payload), session, replacement=replacement)
        _save_assertion(session, {"operation": "resolve_conflict", "conflict_id": c.id, "by_role": "Dentist",
                                  "resolution": c.resolution.model_dump(mode="json"), "reason": why})
    return commit_human_change(session, g, reason=f"accept {pending_id}", client=client, agents=agents)


# ---------------------------------------------------------------- dispositions

def confirm_entity(session, entity_id: str, kind: str, role: str, reason: str = "", *, client=None, agents=None):
    """human_reviewed (Assistant) or dentist_confirmed (Dentist) on the entity's current hashes."""
    if kind == "dentist_confirmed" and role != "Dentist":
        raise HumanActionError("only the Dentist can confirm")
    if kind not in ("human_reviewed", "dentist_confirmed"):
        raise HumanActionError("kind must be human_reviewed or dentist_confirmed")
    g = _working_graph(session)
    e = g.get(entity_id)
    if e is None or e.status != "active":
        raise HumanActionError(f"{entity_id} is not active")
    d = add_entity_disposition(g, e, kind, role, reason)
    _complete_entity_tasks(g, e.id, "accepted", role, reason, cites=[d.id])
    return commit_human_change(session, g, reason=f"{kind} {entity_id}", client=client, agents=agents)


def review_section(session, section: str, outcome: str, role: str, reason: str, *, client=None, agents=None):
    """section_reviewed: the reviewer read the sources for this section. Adding an item alone never clears it."""
    if outcome not in ("completed", "not_discussed"):
        raise HumanActionError("outcome must be completed or not_discussed")
    g = _working_graph(session)
    rec = next((s for s in g.section_records if s.section == section), None)
    if rec is None:
        raise HumanActionError(f"no section record for {section}")
    d = make_disposition("section", section, {"record_version": rec.version}, "section_reviewed", role, reason,
                         outcome=outcome)
    g.dispositions.append(d)
    _auto_complete_extractor_tasks(g)
    return commit_human_change(session, g, reason=f"section {section} reviewed", client=client, agents=agents)


def _auto_complete_extractor_tasks(g):
    """10.1: an extractor failure task completes itself once every section it owns has a section review."""
    from pipeline.dispositions import section_reviewed
    from pipeline.template import sections_owned
    for t in g.tasks:
        if t.kind != "stage_failure" or t.status != "open" or t.created_by_stage != "B":
            continue
        agent = t.reason.split()[1] if len(t.reason.split()) > 1 else ""
        owned = sections_owned(agent) if agent != "Br" else []
        if not owned:
            continue
        disps = [section_reviewed(g, s) for s in owned]
        if all(disps):
            d = make_disposition("task", t.id, {"inputs_hash": t.inputs_hash}, "task_completed", "System",
                                 "all owned sections reviewed", completion="corrected", cites=[x.id for x in disps])
            g.dispositions.append(d)
            t.status, t.disposition_id = "completed", d.id


def complete_task(session, task_id: str, completion: str, role: str, reason: str, *, client=None, agents=None):
    g = _working_graph(session)
    t = g.task(task_id)
    if t is None:
        raise HumanActionError("no such task")
    if completion not in ("corrected", "accepted", "not_applicable"):
        raise HumanActionError("completion must be corrected, accepted or not_applicable")
    if t.kind == "stage_failure" and t.created_by_stage == "C" and ("Co " in t.reason or "R2 " in t.reason) \
            and role != "Dentist":
        raise HumanActionError("a failed Co or R2 stage is accepted by the Dentist after reviewing the transcript")
    d = make_disposition("task", t.id, {"inputs_hash": t.inputs_hash}, "task_completed", role, reason,
                         completion=completion)
    g.dispositions.append(d)
    t.status, t.disposition_id = "completed", d.id
    return commit_human_change(session, g, reason=f"task {task_id} completed", client=client, agents=agents)


# ---------------------------------------------------------------- conflicts

def resolve_conflict(session, conflict_id: str, action: str, role: str, reason: str, *, active_entity_id=None,
                     superseded_entity_id=None, explanation=None, replacement: dict | None = None, client=None,
                     agents=None):
    _check_role(role)
    g = _working_graph(session)
    c = g.conflict(conflict_id)
    if c is None:
        raise HumanActionError("no such conflict")
    res = Resolution(action=action, active_entity_id=active_entity_id, superseded_entity_id=superseded_entity_id,
                     explanation=explanation, resolver_role=role, reason=reason,
                     participant_versions=c.participants, timestamp=now())
    if action == "keep_both" and not (explanation or "").strip():
        raise HumanActionError("keep_both needs an explanation")
    if action == "replace":
        if not replacement:
            raise HumanActionError("replace needs the replacement item")
        rep = dict(replacement)
        rep.setdefault("id", _next_item_id(g, rep.get("kind", "item")))
        res.replacement_entity_id = rep["id"]
        res = res.model_copy(update={"replacement_entity_id": rep["id"]})
        replacement = rep
    participants = [g.get(p.entity_id, p.version) for p in c.participants]
    changes_content = action != "keep_both"
    if role == "Assistant" and changes_content and _critical_content(*participants):
        payload = res.model_dump(mode="json")
        payload["replacement"] = replacement
        pc = _pending(g, "resolve_conflict", role, reason, [p for p in participants if p], content=payload,
                      conflict_id=c.id)
        c.status = "resolved"
        c.resolution = res.model_copy(update={"pending_change_id": pc.id})
        return commit_human_change(session, g, reason=f"pending resolution {conflict_id}", client=client,
                                   agents=agents)
    if replacement:
        res = Resolution.model_validate({**res.model_dump(), "replacement_entity_id": replacement["id"]})
    _apply_resolution(g, c, res, session, replacement=replacement)
    _save_assertion(session, {"operation": "resolve_conflict", "conflict_id": c.id,
                              "resolution": res.model_dump(mode="json"), "by_role": role, "reason": reason})
    return commit_human_change(session, g, reason=f"resolve {conflict_id}", client=client, agents=agents)


def _apply_resolution(g, c, res: Resolution, session=None, replacement: dict | None = None):
    """Conflicts never edit participants' content: they only change which participants are active."""
    parts = [g.get(p.entity_id, p.version) for p in c.participants]
    if res.action == "select":
        for e in parts:
            if e is not None and e.id != res.active_entity_id and e.status == "active":
                e.status, e.superseded_by, e.supersede_reason = "superseded", f"conflict:{c.id}", res.reason
    elif res.action == "supersede":
        e = next((x for x in parts if x is not None and x.id == res.superseded_entity_id), None)
        if e is not None:
            e.status, e.superseded_by, e.supersede_reason = "superseded", f"conflict:{c.id}", res.reason
    elif res.action == "replace":
        for e in parts:
            if e is not None and e.status == "active":
                e.status, e.superseded_by, e.supersede_reason = "superseded", f"conflict:{c.id}", res.reason
        if replacement:
            new = _new_human_entity(replacement, res.resolver_role, res.reason)
            g.entities.append(new)
            rehash_all(g, _roles(session))
            _dispose_new(g, new, res.resolver_role, res.reason)
            if session is not None:
                _save_assertion(session, {"operation": "add", "entity_id": new.id, "by_role": res.resolver_role,
                                          "reason": res.reason, "entity": new.model_dump(mode="json", by_alias=True)})
    c.status = "resolved"
    c.resolution = res
    g.dispositions.append(make_disposition("conflict_resolution", c.id,
                                           {"resolution": res.action,
                                            "participants": [f"{p.entity_id}@{p.version}" for p in c.participants]},
                                           "dentist_confirmed" if res.resolver_role == "Dentist" else "human_entered",
                                           res.resolver_role, res.reason))


def apply_carried_resolutions(g) -> None:
    """A resolution carried over (participants and evidence unchanged) re-applies its effect on activity."""
    for c in g.conflicts:
        if c.status != "resolved" or c.resolution is None or c.resolution.pending_change_id:
            continue
        r = c.resolution
        for p in c.participants:
            e = g.get(p.entity_id, p.version)
            if e is None or e.status != "active":
                continue
            if (r.action == "select" and e.id != r.active_entity_id) or \
                    (r.action == "supersede" and e.id == r.superseded_entity_id) or r.action == "replace":
                e.status, e.superseded_by, e.supersede_reason = "superseded", f"conflict:{c.id}", r.reason


# ---------------------------------------------------------------- staged records

def discard_staged(session, staged_id: str, role: str, reason: str):
    from pipeline.linker import session_staging
    if not reason:
        raise HumanActionError("discarding needs a reason")
    st = session_staging(session)
    rec = st.get(staged_id)
    if rec is None or rec.status != "staged":
        raise HumanActionError("no open staged record")
    rec.status, rec.discard_reason = "discarded", f"{role}: {reason}"
    st.save()
    _complete_staged_task(session, rec, role, reason, "not_applicable")


def convert_staged(session, staged_id: str, data: dict, role: str, reason: str, *, client=None, agents=None):
    """Turn a staged record into a valid human-entry entity. The staged record itself stays unchanged."""
    from pipeline.linker import session_staging
    st = session_staging(session)
    rec = st.get(staged_id)
    if rec is None or rec.status != "staged":
        raise HumanActionError("no open staged record")
    result = add_entity(session, data, role, reason, client=client, agents=agents)
    st = session_staging(session)
    rec = st.get(staged_id)
    rec.status = "converted"
    st.save()
    _complete_staged_task(session, rec, role, reason, "corrected")
    return result


def _complete_staged_task(session, rec, role, reason, completion):
    g = load_graph(session)
    if g is None or not rec.task_id or g.task(rec.task_id) is None or g.task(rec.task_id).status != "open":
        from pipeline.orchestrator import derive
        from pipeline.overlays import load_sources
        if g is not None:
            derive(session, g, load_sources(session), g.pipeline_mode, session.meta().get("rule_mode"))
        return
    complete_task(session, rec.task_id, completion, role, f"staged record {rec.id}: {reason}")


# ---------------------------------------------------------------- reruns (6.11)

def human_overrides(session) -> dict[str, dict]:
    """Entity ids a human removed, edited or replaced -> the latest such assertion."""
    out = {}
    for a in load_assertions(session):
        if a["operation"] in ("remove", "edit"):
            out[a["entity_id"]] = a
    return out


def carry_into(session, graph, previous, sources) -> None:
    """Before the Linker commit: human-entered entities carry over unchanged (problems first)."""
    entities = {}
    for a in load_assertions(session):
        if a["operation"] in ("add", "edit") and a.get("entity"):
            entities[a["entity_id"]] = a["entity"]
        if a["operation"] == "remove":
            entities.pop(a["entity_id"], None)
    order = {"problem": 0, "relationship": 1, "item": 2}
    by_entity = {a["entity_id"]: a for a in load_assertions(session) if a.get("entity")}
    for data in sorted(entities.values(), key=lambda d: order[d["kind"]]):
        e = ENTITY_ADAPTER.validate_python(copy.deepcopy(data))
        e.status = "active"
        e.dispositions = []
        graph.entities.append(e)
        if previous is None or previous.get(e.id) is None:
            # Entered while no graph existed (e.g. a registry after a Br failure): record its entry now.
            a = by_entity.get(e.id, {})
            from pipeline.graph import rehash
            rehash(e, sources.roles, graph)
            add_entity_disposition(graph, e, "human_entered", a.get("by_role", "Dentist"), a.get("reason", ""))
            if a.get("by_role") == "Dentist" and is_critical(e):
                add_entity_disposition(graph, e, "dentist_confirmed", "Dentist", a.get("reason", ""))


def after_commit(session, graph, previous, committed, sources) -> list:
    """After the Linker commit: regenerated entities a human removed or replaced are committed as superseded;
    if their content differs from what was removed, a task asks whether the removal still applies. A
    regenerated entity disagreeing with a human-entered one on the same subject becomes a conflict.
    Still-valid dispositions carry over."""
    from pipeline.tasks import add_task, make_task
    overrides = human_overrides(session)
    for e in committed:
        a = overrides.get(e.id)
        if a is None or e.owner == "human":
            continue
        if a.get("replaced_content_hash") and e.content_hash != a["replaced_content_hash"]:
            add_task(graph, make_task("human_override_check",
                                      f"{e.id} was regenerated with different content; does the human "
                                      f"{a['operation']} still apply?", participants=[e], created_by_stage="L",
                                      severity="medium"), previous)
    humans = [x for x in graph.active() if x.owner == "human" and x.kind == "item"]
    from schemas.conflicts import Conflict
    from pipeline.reconcile import conflict_id
    for h in humans:
        for e in committed:
            if e.status != "active" or e.kind != "item" or e.type != h.type or e.problem_id != h.problem_id:
                continue
            if e.target.tooth != h.target.tooth or e.content_hash == h.content_hash:
                continue
            if h.type in ("finding", "symptom", "instruction", "consent_element"):
                continue  # many legitimate items share type/tooth; only single-valued subjects conflict
            ev = h.evidence + e.evidence
            c = Conflict(id=conflict_id("contradiction", ev), kind="contradiction",
                         participants=[Participant(entity_id=h.id, version=h.version),
                                       Participant(entity_id=e.id, version=e.version)],
                         evidence=ev, subject=f"{h.type} (human entry vs regenerated)", origin="human")
            if graph.conflict(c.id) is None:
                graph.conflicts.append(c)
    rehash_all(graph, sources.roles)
    if previous is not None:
        have = {d.id for d in graph.dispositions}
        for d in previous.dispositions:
            if d.id in have or d.subject_type != "entity":
                continue
            e = graph.get(d.subject_id)
            if e is not None and e.status == "active" and d.subject_hashes == entity_hashes(e):
                graph.dispositions.append(d)
                e.dispositions.append(d.id)
    # Human entries carry over unchanged; their entry is re-recorded if the bound hashes moved (e.g. a role
    # overlay change). Confirmations are not: a dentist_confirmed disposition counts only while it binds.
    from pipeline.dispositions import bound_dispositions
    by_entity = {a["entity_id"]: a for a in load_assertions(session) if a.get("entity")}
    for e in graph.active():
        if e.owner == "human" and not bound_dispositions(graph, e, {"human_entered"}):
            a = by_entity.get(e.id, {})
            add_entity_disposition(graph, e, "human_entered", a.get("by_role", "Assistant"),
                                   f"carried over from a rerun: {a.get('reason', '')}")
    return committed


def carry_section_dispositions(graph, previous) -> None:
    """Section reviews carry over while the section record version is unchanged."""
    if previous is None:
        return
    have = {d.id for d in graph.dispositions}
    for d in previous.dispositions:
        if d.subject_type == "section" and d.id not in have:
            rec = next((s for s in graph.section_records if s.section == d.subject_id), None)
            if rec is not None and d.subject_hashes.get("record_version") == rec.version:
                graph.dispositions.append(d)


def add_comment(session, subject: str, role: str, text: str) -> None:
    """Reviewer comments: kept in the audit record, never rendered into the note."""
    data = read_json(session.path("comments.json"), [])
    data.append({"subject": subject, "role": role, "text": text, "timestamp": now()})
    atomic_write_json(session.path("comments.json"), data)


def flag_action(session, flag_id: str, action: str, role: str, reason: str = ""):
    """Dismiss / mark for dentist / resolve / comment on a flag. A dismissal never changes a check result."""
    from pipeline.flags import session_flag_actions
    from pipeline.orchestrator import load_latest
    from schemas.flags import Flag
    latest = load_latest(session) or {}
    flag = next((Flag.model_validate(f) for f in latest.get("flags", []) if f["id"] == flag_id), None)
    if flag is None:
        raise HumanActionError("no such flag")
    if action == "dismiss" and not reason:
        raise HumanActionError("a dismissal needs a reason")
    if action == "dismiss" and flag.safety_critical and role != "Dentist":
        raise HumanActionError("only the Dentist dismisses a safety-critical flag")
    session_flag_actions(session).add(flag, action, role, reason)


# ---------------------------------------------------------------- registry entry when no graph exists

def enter_registry(session, problem: dict, role: str, reason: str, *, client=None, agents=None):
    """Br (or B0) failed, so no graph could commit. A human enters the chief problem. By the Dentist it takes
    effect and extraction re-runs (B2-B4 now run and the whole batch commits); by an Assistant it waits as a
    pending registry for the Dentist (critical-change policy)."""
    _check_role(role)
    data = {"kind": "problem", "key": "human:P1", "role": "chief", **problem}
    data.setdefault("id", "pb_h1")
    entity = _new_human_entity(data, role, reason, data.get("assertion_source", "clinician_assessment"))
    if role == "Assistant":
        atomic_write_json(session.path("pending_registry.json"),
                          {"entity": entity.model_dump(mode="json", by_alias=True), "by_role": role, "reason": reason,
                           "timestamp": now()})
        return None
    return _commit_registry(session, entity, role, reason, client, agents)


def accept_pending_registry(session, role: str, reason: str = "", *, client=None, agents=None):
    if role != "Dentist":
        raise HumanActionError("only the Dentist accepts a pending registry")
    pending = read_json(session.path("pending_registry.json"))
    if not pending:
        raise HumanActionError("no pending registry")
    entity = ENTITY_ADAPTER.validate_python(pending["entity"])
    session.path("pending_registry.json").unlink()
    return _commit_registry(session, entity, "Dentist", f"{pending['reason']} (accepted by Dentist {reason})".strip(),
                            client, agents)


def _commit_registry(session, entity, role, reason, client, agents):
    from pipeline.orchestrator import run_pipeline
    from pipeline.overlays import load_roles
    from pipeline.graph import content_hash, support_hash
    entity.content_hash = content_hash(entity)
    entity.support_hash = support_hash(entity, load_roles(session))
    _save_assertion(session, {"operation": "add", "entity_id": entity.id, "by_role": role, "reason": reason,
                              "entity": entity.model_dump(mode="json", by_alias=True), "registry": True})
    return run_pipeline(session, client=client, agents=agents)
