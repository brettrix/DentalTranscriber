"""Overlays (roles, corrections) and the frozen source bundle every stage reads."""
from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.storage import Session, atomic_write_json, hash_obj, now, read_json, sha256_text
from schemas.sources import CorrectionsOverlay, QuickNotesSource, RolesOverlay, UtterancesSource, VisitMeta


def write_roles(session: Session, overlay: RolesOverlay, reason: str = "") -> RolesOverlay:
    meta = session.meta()
    current = meta.get("roles_version", 0)
    overlay = overlay.model_copy(update={"version": current + 1})
    atomic_write_json(session.path("overlays", f"roles_v{overlay.version}.json"), overlay)
    history = meta.get("overlay_history", [])
    history.append({"overlay": "roles", "version": overlay.version, "reason": reason, "timestamp": now()})
    session.update_meta(roles_version=overlay.version, overlay_history=history)
    return overlay


def confirm_roles(session: Session, mapping: dict[str, str], by: str = "human") -> RolesOverlay:
    from schemas.sources import RoleEntry
    return write_roles(session, RolesOverlay(entries={s: RoleEntry(role=r, set_by=by) for s, r in mapping.items()},
                                             confirmed=True), reason=f"confirmed by {by}")


def load_roles(session: Session) -> RolesOverlay:
    v = session.meta().get("roles_version")
    if not v:
        return RolesOverlay()
    return RolesOverlay.model_validate(read_json(session.path("overlays", f"roles_v{v}.json")))


def load_corrections(session: Session) -> CorrectionsOverlay:
    v = session.meta().get("corrections_version")
    if not v:
        return CorrectionsOverlay(version=0)
    return CorrectionsOverlay.model_validate(read_json(session.path("overlays", f"corrections_v{v}.json")))


@dataclass
class Sources:
    utterances: UtterancesSource
    quick_notes: QuickNotesSource
    visit_meta: VisitMeta
    roles: RolesOverlay
    corrections: CorrectionsOverlay
    hashes: dict[str, str] = field(default_factory=dict)

    def utterance(self, uid: str):
        return next((u for u in self.utterances.utterances if u.id == uid), None)

    def note(self, qid: str):
        return next((q for q in self.quick_notes.notes if q.id == qid), None)

    def role_of(self, speaker: str) -> str | None:
        entry = self.roles.entries.get(speaker)
        return entry.role if entry else None

    def source_text(self, source_type: str, source_id: str) -> str | None:
        if source_type == "transcript":
            u = self.utterance(source_id)
            return u.text if u else None
        if source_type == "quick_note":
            q = self.note(source_id)
            return q.text if q else None
        return None

    def utterance_index(self, uid: str) -> int:
        for i, u in enumerate(self.utterances.utterances):
            if u.id == uid:
                return i
        return -1

    @property
    def overlay_versions(self) -> dict[str, int]:
        return {"roles": self.roles.version, "corrections": self.corrections.version}

    def transcript_block(self) -> str:
        lines = [f"[{u.id}] ({u.speaker} {self.role_of(u.speaker) or 'Unknown'}) {u.text}"
                 for u in self.utterances.utterances]
        return "\n".join(lines)

    def quick_notes_block(self) -> str:
        return "\n".join(f"[{q.id}] {q.text}" for q in self.quick_notes.notes) or "(none)"


def load_sources(session: Session) -> Sources:
    utt = UtterancesSource.model_validate(read_json(session.path("sources", "utterances.json")))
    qn = QuickNotesSource.model_validate(read_json(session.path("sources", "quick_notes.json"), {"notes": []}))
    vm = VisitMeta.model_validate(read_json(session.path("sources", "visit_meta.json"), {}))
    roles = load_roles(session)
    corr = load_corrections(session)
    hashes = {"utterances": hash_obj(utt), "quick_notes": hash_obj(qn), "visit_meta": hash_obj(vm),
              "roles": hash_obj(roles), "corrections": hash_obj(corr)}
    raw = session.meta().get("provider_response_hash")
    if raw:
        hashes["provider_response"] = raw
    return Sources(utt, qn, vm, roles, corr, hashes)


def sources_from_objects(utterances: UtterancesSource, quick_notes: QuickNotesSource | None = None,
                         visit_meta: VisitMeta | None = None, roles: RolesOverlay | None = None) -> Sources:
    qn = quick_notes or QuickNotesSource()
    vm = visit_meta or VisitMeta()
    ro = roles or RolesOverlay(confirmed=True)
    corr = CorrectionsOverlay(version=0)
    hashes = {"utterances": hash_obj(utterances), "quick_notes": hash_obj(qn), "visit_meta": hash_obj(vm),
              "roles": hash_obj(ro), "corrections": hash_obj(corr)}
    return Sources(utterances, qn, vm, ro, corr, hashes)


def source_text_hash(text: str) -> str:
    return sha256_text(text)
