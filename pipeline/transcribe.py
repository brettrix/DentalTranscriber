"""T0 transcriber: text mode (role-prefixed typed transcript) and Deepgram Nova-3 Medical (REST).

Both write the provider response untouched, then normalized utterances.json with no roles.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

from glossary import KEYTERMS
from pipeline.storage import Session, atomic_write_bytes, atomic_write_json, sha256_text
from schemas.sources import QuickNote, QuickNotesSource, RoleEntry, RolesOverlay, Utterance, UtterancesSource, VisitMeta

ROLE_PREFIXES = {"dentist": "Dentist", "assistant": "Assistant", "patient": "Patient", "other": "Other",
                 "doctor": "Dentist", "dr": "Dentist"}
_LINE = re.compile(r"^\s*([A-Za-z]+)\s*(?:\[(S\d+)\])?\s*:\s*(.*)$")

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_PARAMS = {
    "model": "nova-3-medical",
    "diarize": "true",
    "utterances": "true",
    "smart_format": "true",
    "punctuate": "true",
}
ALLOWED_AUDIO = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".flac": "audio/flac"}
MAX_AUDIO_BYTES = 50 * 1024 * 1024
MAX_AUDIO_SECONDS = 30 * 60


class TranscriptFormatError(ValueError):
    pass


# ---------------------------------------------------------------- text mode

def parse_text_transcript(text: str) -> tuple[list[Utterance], dict[str, RoleEntry]]:
    """Lines like 'DENTIST: ...' or 'Dentist: ...' (any case); optional explicit id 'DENTIST [S2]: ...'.
    Unprefixed lines continue the previous utterance. One speaker id per role unless given explicitly."""
    utterances: list[Utterance] = []
    roles: dict[str, RoleEntry] = {}
    role_to_speaker: dict[str, str] = {}
    next_id = 0
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = _LINE.match(raw)
        role = ROLE_PREFIXES.get(m.group(1).lower()) if m else None
        if not m or role is None:
            if not utterances:
                raise TranscriptFormatError(f"first line has no role prefix: {raw[:60]!r}")
            prev = utterances[-1]
            utterances[-1] = prev.model_copy(update={"text": f"{prev.text} {raw.strip()}"})
            continue
        speaker = m.group(2)
        if speaker is None:
            if role not in role_to_speaker:
                while f"S{next_id}" in roles:
                    next_id += 1
                role_to_speaker[role] = f"S{next_id}"
                next_id += 1
            speaker = role_to_speaker[role]
        if speaker in roles and roles[speaker].role != role:
            raise TranscriptFormatError(f"speaker {speaker} has two roles")
        roles[speaker] = RoleEntry(role=role, set_by="text_prefix")
        body = m.group(3).strip()
        if not body:
            continue
        utterances.append(Utterance(id=f"u{len(utterances) + 1}", speaker=speaker, text=body))
    if not utterances:
        raise TranscriptFormatError("no utterances found")
    return utterances, roles


def transcribe_text(session: Session, text: str) -> UtterancesSource:
    raw = text.encode("utf-8")
    atomic_write_bytes(session.path("sources", "provider_response.txt"), raw)
    utterances, roles = parse_text_transcript(text)
    src = UtterancesSource(provider="text", utterances=utterances)
    atomic_write_json(session.path("sources", "utterances.json"), src)
    from pipeline.overlays import write_roles
    write_roles(session, RolesOverlay(entries=roles, confirmed=True), reason="text prefixes")
    session.update_meta(input_mode="text", provider_response_hash=sha256_text(raw))
    return src


# ---------------------------------------------------------------- Deepgram

def deepgram_params() -> list[tuple[str, str]]:
    params = list(DEEPGRAM_PARAMS.items())
    params += [("keyterm", term) for term in KEYTERMS[:100]]
    return params


def check_audio(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in ALLOWED_AUDIO:
        raise ValueError(f"unsupported audio type {ext}; allowed: {', '.join(ALLOWED_AUDIO)}")
    if path.stat().st_size > MAX_AUDIO_BYTES:
        raise ValueError("audio file is over 50 MB")
    return ALLOWED_AUDIO[ext]


def normalize_deepgram(response: dict) -> list[Utterance]:
    """Deepgram utterances -> {id, speaker 'S<n>', start, end, text}. Falls back to word grouping by speaker."""
    results = response.get("results") or {}
    utts = results.get("utterances")
    out: list[Utterance] = []
    if utts:
        for u in utts:
            text = (u.get("transcript") or "").strip()
            if not text:
                continue
            out.append(Utterance(id=f"u{len(out) + 1}", speaker=f"S{int(u.get('speaker', 0))}",
                                 start=float(u.get("start", 0.0)), end=float(u.get("end", 0.0)), text=text))
        return out
    channels = results.get("channels") or []
    words = (channels[0]["alternatives"][0].get("words") or []) if channels else []
    cur: dict | None = None
    for w in words:
        spk = f"S{int(w.get('speaker', 0))}"
        token = w.get("punctuated_word") or w.get("word") or ""
        if cur and cur["speaker"] == spk:
            cur["text"] += " " + token
            cur["end"] = float(w.get("end", cur["end"]))
        else:
            if cur:
                out.append(Utterance(id=f"u{len(out) + 1}", **cur))
            cur = {"speaker": spk, "start": float(w.get("start", 0.0)), "end": float(w.get("end", 0.0)), "text": token}
    if cur:
        out.append(Utterance(id=f"u{len(out) + 1}", **cur))
    return out


def transcribe_audio(session: Session, audio_path: Path, *, api_key: str | None = None, post=requests.post) -> UtterancesSource:
    content_type = check_audio(audio_path)
    if post is requests.post:
        from pipeline.ledger import require_real
        require_real("Deepgram")
    key = api_key or os.environ.get("DEEPGRAM_API_KEY")
    if not key:
        raise RuntimeError("DEEPGRAM_API_KEY is not set")
    data = audio_path.read_bytes()
    atomic_write_bytes(session.path("sources", f"audio{audio_path.suffix.lower()}"), data)
    resp = post(DEEPGRAM_URL, params=deepgram_params(), data=data,
                headers={"Authorization": f"Token {key}", "Content-Type": content_type}, timeout=300)
    if resp.status_code >= 400:
        raise RuntimeError(f"Deepgram error {resp.status_code}: {resp.text[:300]}")
    raw = resp.content
    atomic_write_bytes(session.path("sources", "provider_response.json"), raw)
    response = json.loads(raw)
    if post is requests.post:
        from pipeline.ledger import record
        record("deepgram", agent="T0", model="nova-3-medical", result="ok",
               extra={"audio_seconds": (response.get("metadata") or {}).get("duration")})
    duration = float((response.get("metadata") or {}).get("duration") or 0.0)
    if duration > MAX_AUDIO_SECONDS:
        raise ValueError("audio is over 30 minutes")
    src = UtterancesSource(provider="deepgram:nova-3-medical", utterances=normalize_deepgram(response))
    atomic_write_json(session.path("sources", "utterances.json"), src)
    from pipeline.overlays import write_roles
    speakers = sorted({u.speaker for u in src.utterances})
    # Audio roles need human confirmation before Stage B; start unconfirmed with placeholder roles.
    write_roles(session, RolesOverlay(entries={s: RoleEntry(role="Other", set_by="unconfirmed") for s in speakers},
                                      confirmed=False), reason="audio speakers detected")
    session.update_meta(input_mode="audio", provider_response_hash=sha256_text(raw),
                        transcriber={"url": DEEPGRAM_URL, "params": DEEPGRAM_PARAMS, "keyterms": len(KEYTERMS)})
    return src


# ---------------------------------------------------------------- quick notes and visit meta

def write_quick_notes(session: Session, text: str) -> QuickNotesSource:
    notes = [QuickNote(id=f"q{i + 1}", text=line.strip()) for i, line in
             enumerate(l for l in (text or "").splitlines() if l.strip())]
    src = QuickNotesSource(notes=notes)
    atomic_write_json(session.path("sources", "quick_notes.json"), src)
    return src


def write_visit_meta(session: Session, **meta) -> VisitMeta:
    vm = VisitMeta(**meta)
    atomic_write_json(session.path("sources", "visit_meta.json"), vm)
    return vm
