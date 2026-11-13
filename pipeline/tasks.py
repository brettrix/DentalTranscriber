"""Human-review tasks (section 6.8): stable ids, inputs hashes, reopen on changed inputs."""
from __future__ import annotations

from pipeline.storage import hash_obj
from schemas.conflicts import Participant
from schemas.dispositions import Task


def _span_ids(evidence) -> list[str]:
    return sorted(f"{s.source_type}:{s.source_id}:{s.start}-{s.end}" for s in evidence)


def make_task(kind: str, reason: str, *, evidence=(), participants=(), rule_hash: str | None = None,
              created_by_stage: str, severity: str = "medium", staging_ids=(), section: str | None = None,
              stage_run_id: str | None = None, key: str | None = None) -> Task:
    evidence = list(evidence)
    parts = [p if isinstance(p, Participant) else Participant(entity_id=p.id, version=p.version) for p in participants]
    stable = key or hash_obj([kind, _span_ids(evidence), sorted(p.entity_id for p in parts), section,
                              sorted(staging_ids), stage_run_id and stage_run_id[:0]])
    inputs_hash = hash_obj({"evidence": [s.model_dump(mode="json") for s in evidence],
                            "participants": sorted(f"{p.entity_id}@{p.version}" for p in parts),
                            "reason": reason, "rule_hash": rule_hash})
    return Task(id="tk_" + hash_obj([kind, stable])[:12], kind=kind, reason=reason, evidence=evidence,
                participants=parts, rule_hash=rule_hash, inputs_hash=inputs_hash, created_by_stage=created_by_stage,
                severity=severity, staging_ids=list(staging_ids), section=section, stage_run_id=stage_run_id)


def add_task(graph, task: Task, previous=None) -> Task:
    """Add (or keep) a task. A previous completion carries over only if its disposition is bound to the same
    inputs_hash; otherwise the task is open."""
    existing = graph.task(task.id)
    if existing is not None:
        return existing
    prior = previous.task(task.id) if previous is not None else None
    if prior is not None and prior.status == "completed" and prior.disposition_id:
        disp = previous.disposition(prior.disposition_id)
        if disp is not None and disp.subject_hashes.get("inputs_hash") == task.inputs_hash:
            task.status, task.disposition_id = "completed", prior.disposition_id
            if graph.disposition(disp.id) is None:
                graph.dispositions.append(disp)
    graph.tasks.append(task)
    return task
