"""Team-mode checks: Cs windows and per-attribute comparison (with Ce for free text), and Co omissions."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from agents.cs_support import UNKNOWN
from agents.io import LINKER_SET
from pipeline import normalize
from pipeline.repair import Issue, covered_by, owner_for_entity, owner_for_type
from pipeline.storage import hash_obj, now
from pipeline.verify import locate_span
from schemas.entities import Span, compare_table, entity_section, get_path

MAX_CONCURRENT_CALLS = 4
CONTEXT = 2  # utterances on each side of the evidence


def semantic_config_hash(run) -> str:
    cs, ce = run.agent("Cs"), run.agent("Ce")
    return hash_obj({"cs": cs.prompt_hash(), "ce": ce.prompt_hash(), "cs_model": cs.config["model"],
                     "ce_model": ce.config["model"]})[:16]


def _paths(entity, n_problems: int) -> list[str]:
    table = compare_table(entity.kind, getattr(entity, "type", None))
    skip = {"type", "scope", "problem_id", "key", "target_relation"}
    out = [p for p, m in table.items() if m.get("compare") != "excluded" and p not in skip
           and p.split(".")[-1] not in LINKER_SET]
    if entity.kind == "item" and entity.scope == "problem" and n_problems > 1:
        out.append("problem")
    return out


def _window(entity, sources) -> str:
    idxs = [sources.utterance_index(s.source_id) for s in entity.evidence if s.source_type == "transcript"]
    idxs = [i for i in idxs if i >= 0]
    lines = []
    if idxs:
        utts = sources.utterances.utterances
        lo, hi = max(0, min(idxs) - CONTEXT), min(len(utts) - 1, max(idxs) + CONTEXT)
        lines += [f"[{u.id}] ({u.speaker} {sources.role_of(u.speaker) or 'Unknown'}) {u.text}" for u in utts[lo:hi + 1]]
    for s in entity.evidence:
        if s.source_type == "quick_note":
            q = sources.note(s.source_id)
            if q:
                lines.append(f"[{q.id}] (quick note typed by the assistant) {q.text}")
        elif s.source_type == "visit_meta":
            lines.append(f"[visit_meta] {s.text}")
    return "\n".join(lines)


def neutral_problem_list(graph, sources) -> str:
    """Problem ids with only the raw source text of their complaint evidence, plus a new-problem option."""
    lines = []
    for p in graph.active("problem"):
        texts = []
        for s in p.evidence:
            t = sources.source_text(s.source_type, s.source_id)
            if t and t not in texts:
                texts.append(t)
        lines.append(f"- {p.id}: " + " / ".join(texts))
    lines.append("- new_problem: none of these")
    return "\n".join(lines)


def _what(entity) -> str:
    if entity.kind == "item":
        return f"one {entity.type} item"
    return f"one {entity.kind}" + (" (a complaint the visit addresses)" if entity.kind == "problem" else
                                   " (how another tooth relates to the problem)")


def _clean(v) -> str:
    return re.sub(r"[^a-z0-9/ ]", "", str(v).lower()).strip()


NEGATED = {"absent", "denied"}
# Both describe exam results; patient-vs-clinician attribution stays strict (DECISIONS.md).
SOURCE_GROUPS = [{"clinician_observation", "test_response"}]


def compare_entity(entity, values: dict, n_problems: int):
    """Per-attribute comparison. Returns (mismatches, unknown_critical, ce_pairs).
    Critical free-text attributes are compared one by one; non-critical free text is compared as one combined
    description, so the same detail recorded under a neighbouring field is not a mismatch (DECISIONS.md)."""
    table = compare_table(entity.kind, getattr(entity, "type", None))
    mismatches, unknown, pairs = [], [], []
    loose_p, loose_c = [], []
    for path in _paths(entity, n_problems):
        c = values.get(path, UNKNOWN if path == "problem" else None)
        if path == "problem":
            if c == UNKNOWN:
                unknown.append("problem")
            elif c != entity.problem_id:
                mismatches.append(f"problem: producer {entity.problem_id} vs checker {c}")
            continue
        meta = table[path]
        p = get_path(entity, path)
        if c == UNKNOWN:
            if meta.get("critical") and p is not None:
                unknown.append(path)
            continue
        method = meta["compare"]
        if not meta.get("critical") and p in (None, "") and method in ("exact", "normalized"):
            continue  # the checker reading an extra non-critical detail doesn't contradict the producer
        if method == "exact":
            if path == "assertion" and p in NEGATED and c in NEGATED:
                same = True
            elif path == "assertion_source" and any(p in grp and c in grp for grp in SOURCE_GROUPS):
                same = True
            else:
                same = normalize.values_equal(p, c) or (p is None and c in (None, "", []))
        elif method == "normalized":
            try:
                same = normalize.values_equal(normalize.normalize_value(meta["rule"], p),
                                              normalize.normalize_value(meta["rule"], c))
            except normalize.NormalizationError:
                same = False
        elif not meta.get("critical"):
            if p not in (None, ""):
                loose_p.append(str(p))
            if c not in (None, ""):
                loose_c.append(str(c))
            continue
        else:
            if p in (None, "") and c in (None, ""):
                same = True
            elif p in (None, "") or c in (None, ""):
                same = False
            elif _clean(p) == _clean(c):
                same = True
            else:
                pairs.append({"attribute": path, "a": p, "b": c})
                continue
        if not same:
            mismatches.append(f"{path}: producer {p!r} vs checker {c!r}")
    if loose_p:
        a, b = "; ".join(loose_p), "; ".join(loose_c)
        if not loose_c:
            mismatches.append(f"free-text details: producer {a!r}, checker found none")
        elif _clean(a) != _clean(b):
            pairs.append({"attribute": "free-text details", "a": a, "b": b})
    return mismatches, unknown, pairs


def run_semantic(run, entities, attempt: int = 1):
    """Cs per section (+ Ce), recording one semantic_support execution per entity. Returns (config, issues)."""
    g, sources = run.graph, run.sources
    config = semantic_config_hash(run)
    by_section: dict[str, list] = {}
    for e in entities:
        if not e.is_human and e.status == "active":
            by_section.setdefault(entity_section(e), []).append(e)
    n_problems = len(g.active("problem"))
    plist = neutral_problem_list(g, sources)
    from pipeline.template import template
    sec_types = {s["id"]: s["item_types"] for s in template()["sections"]}

    def cs_call(section):
        ents = by_section[section]
        windows = [{"window_id": f"W{i + 1}", "what": _what(e), "paths": _paths(e, n_problems),
                    "focus": [{"source_id": s.source_id, "quote": s.text} for s in e.evidence],
                    "window_text": _window(e, sources)} for i, e in enumerate(ents)]
        needs_list = any(e.kind == "item" and e.scope == "problem" for e in ents) and n_problems > 1
        st = now()
        try:
            out = run.agent("Cs").check(section, windows, plist if needs_list else None, sec_types.get(section, []),
                                        attempt=attempt)
            return section, ents, out, None, st
        except Exception as exc:  # noqa: BLE001
            return section, ents, None, exc, st

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CALLS) as pool:
        cs_results = list(pool.map(cs_call, list(by_section)))

    issues: list[Issue] = []
    pending: list[tuple] = []  # (section, entity, mismatches, unknown, pairs)
    for section, ents, out, exc, st in cs_results:
        if exc is not None:
            run.record("C", "Cs", "failed", error=f"{section}: {type(exc).__name__}: {str(exc)[:200]}", started=st,
                       extra={"section": section, "attempt": attempt})
            for e in ents:
                run.check_log.record(e, "semantic_support", "not_assessed_due_to_failure", [f"Cs failed: {exc}"],
                                     config, attempt, run.run_id)
            continue
        run.record("C", "Cs", "succeeded", started=st, extra={"section": section, "attempt": attempt})
        results = {w.window_id: w for w in out.windows}
        for i, e in enumerate(ents):
            w = results.get(f"W{i + 1}")
            if w is None:
                run.check_log.record(e, "semantic_support", "unconfirmed", ["checker returned no result for window"],
                                     config, attempt, run.run_id)
                continue
            mism, unknown, pairs = compare_entity(e, w.values, n_problems)
            pending.append((section, e, mism, unknown, pairs))
            for extra in w.extra_assertions:
                spans = _spans(extra.evidence, sources)
                # Utterance-level coverage: Co does the fine-grained omission check with the entity list.
                if spans and not all(covered_by(g, s.source_type, s.source_id) for s in spans):
                    issues.append(Issue(kind="omission", owner=owner_for_type(extra.suggested_type, run.mode),
                                        details=f"Cs window extra: {extra.description}", origin="Cs",
                                        evidence=[{"source_type": s.source_type, "source_id": s.source_id,
                                                   "quote": s.text} for s in spans],
                                        suggested_type=extra.suggested_type, section=section))

    # Ce: batch the free-text pairs per section.
    verdicts: dict[str, str] = {}
    failed_sections: set[str] = set()
    jobs: dict[str, list[dict]] = {}
    for section, e, _, _, pairs in pending:
        for k, pr in enumerate(pairs):
            jobs.setdefault(section, []).append({**pr, "pair_id": f"{e.id}:{k}"})

    def ce_call(section):
        st = now()
        try:
            return section, run.agent("Ce").compare(section, jobs[section], attempt=attempt), None, st
        except Exception as exc:  # noqa: BLE001
            return section, None, exc, st

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CALLS) as pool:
        for section, out, exc, st in pool.map(ce_call, list(jobs)):
            if exc is not None:
                failed_sections.add(section)
                run.record("C", "Ce", "failed", error=f"{section}: {type(exc).__name__}", started=st,
                           extra={"section": section, "attempt": attempt})
            else:
                run.record("C", "Ce", "succeeded", started=st, extra={"section": section, "attempt": attempt})
                verdicts.update({v.pair_id: v.verdict for v in out.verdicts})
    if not jobs:
        run.record("C", "Ce", "not_applicable", extra={"attempt": attempt})

    for section, e, mism, unknown, pairs in pending:
        details = list(mism)
        ce_failed = False
        for k, pr in enumerate(pairs):
            v = verdicts.get(f"{e.id}:{k}")
            if v is None:
                ce_failed = ce_failed or section in failed_sections
                if section not in failed_sections:
                    details.append(f"{pr['attribute']}: no equivalence verdict")
            elif v != "equivalent":
                details.append(f"{pr['attribute']}: {v} (producer {pr['a']!r} vs checker {pr['b']!r})")
        if details:
            result = "fail"
        elif ce_failed:
            result = "not_assessed_due_to_failure"
        elif unknown:
            result = "unconfirmed"
            details = [f"not established from the evidence window: {', '.join(unknown)}"]
        else:
            result = "pass"
        run.check_log.record(e, "semantic_support", result, details, config, attempt, run.run_id)
        if result == "fail":
            issues.append(Issue(kind="semantic_mismatch", owner=owner_for_entity(e, run.mode), entity_id=e.id,
                                entity_version=e.version, check="semantic_support",
                                details="; ".join(details)[:1500], origin="Cs", section=section))
    if attempt == 2:
        run.issues += issues
    return config, issues


def _spans(quotes, sources) -> list[Span]:
    out = []
    for q in quotes:
        version = sources.utterances.version if q.source_type == "transcript" else sources.quick_notes.version
        s = Span(source_type=q.source_type, source_id=q.source_id, source_version=version, text=q.quote)
        locate_span(s, sources)
        out.append(s)
    return out


def entity_list(graph) -> str:
    lines = []
    for e in graph.active():
        ev = ",".join(sorted({s.source_id for s in e.evidence}))
        if e.kind == "item":
            keys = {k: v for k, v in e.attributes.items() if v not in (None, "", False) and k not in LINKER_SET}
            lines.append(f"- {e.id} {e.type} tooth={e.target.tooth} {e.assertion} {keys} evidence={ev}")
        elif e.kind == "problem":
            lines.append(f"- {e.id} problem {e.role}: {e.complaint_text!r} target={e.clinical_target.tooth} evidence={ev}")
        else:
            lines.append(f"- {e.id} relationship tooth {e.tooth} {e.relation_kind} evidence={ev}")
    return "\n".join(lines)


def run_omission(run, attempt: int = 1, sections: set[str] | None = None) -> list[Issue]:
    g, sources = run.graph, run.sources
    st = now()
    try:
        out = run.agent("Co").find(sources, entity_list(g), attempt=attempt)
    except Exception as exc:  # noqa: BLE001
        run.record("C", "Co", "failed", error=f"{type(exc).__name__}: {str(exc)[:200]}", started=st,
                   extra={"attempt": attempt})
        return []
    run.record("C", "Co", "succeeded", started=st, extra={"attempt": attempt})
    from schemas.entities import ITEM_SECTION
    issues = []
    for o in out.omissions:
        spans = _spans(o.evidence, sources)
        if not spans or all(covered_by(g, s.source_type, s.source_id, s.start, s.end) and
                            any(getattr(x, "type", x.kind) == o.suggested_type
                                for x in covered_by(g, s.source_type, s.source_id, s.start, s.end))
                            for s in spans):
            continue
        section = ITEM_SECTION.get(o.suggested_type or "", "chief_complaint" if o.suggested_type in
                                   ("problem", "relationship") else None)
        if sections is not None and section not in sections:
            continue
        issues.append(Issue(kind="omission", owner=owner_for_type(o.suggested_type, run.mode),
                            details=f"Co: {o.statement}", origin="Co", suggested_type=o.suggested_type,
                            section=section, evidence=[{"source_type": s.source_type, "source_id": s.source_id,
                                                        "quote": s.text} for s in spans]))
    if attempt == 2:
        run.issues += issues
    return issues
