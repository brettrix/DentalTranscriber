"""JSON storage per session: atomic writes (temp file + rename), per-session lock, hashing helpers."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = Path(os.environ.get("SCRIBE_SESSIONS_DIR", ROOT / "data" / "sessions"))


class SessionBusy(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical(obj: Any) -> str:
    return json.dumps(_plain(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _plain(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", by_alias=True)
    return obj


def sha256_text(text: str | bytes) -> str:
    data = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(data).hexdigest()


def hash_obj(obj: Any) -> str:
    return sha256_text(canonical(obj))


def short_hash(obj: Any, n: int = 12) -> str:
    return hash_obj(obj)[:n]


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_bytes(path, json.dumps(_plain(obj), indent=2, ensure_ascii=False, sort_keys=False).encode("utf-8"))


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def append_jsonl(path: Path, obj: Any) -> None:
    """Append-only log. One line per record; never rewritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(_plain(obj), ensure_ascii=False, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.write(line)
        fh.flush()
        fcntl.flock(fh, fcntl.LOCK_UN)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


class Session:
    """A session folder (random UUID) holding sources, overlays, graph versions and execution history."""

    def __init__(self, session_id: str, root: Path | None = None):
        self.id = session_id
        self.dir = (root or SESSIONS_DIR) / session_id
        self._lock_fh = None

    @classmethod
    def create(cls, root: Path | None = None, **meta) -> "Session":
        s = cls(str(uuid.uuid4()), root)
        s.dir.mkdir(parents=True, exist_ok=False)
        s.write_meta({"id": s.id, "created": now(), **meta})
        return s

    # ---- paths
    def path(self, *parts: str) -> Path:
        return self.dir.joinpath(*parts)

    # ---- metadata
    def meta(self) -> dict:
        return read_json(self.path("session.json"), {})

    def write_meta(self, meta: dict) -> None:
        atomic_write_json(self.path("session.json"), meta)

    def update_meta(self, **changes) -> dict:
        meta = self.meta()
        meta.update(changes)
        self.write_meta(meta)
        return meta

    # ---- lock against duplicate Streamlit runs
    @contextlib.contextmanager
    def lock(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        fh = open(self.path(".lock"), "w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            raise SessionBusy(f"session {self.id} is already being processed")
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()

    def is_locked(self) -> bool:
        fh = open(self.path(".lock"), "w")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh, fcntl.LOCK_UN)
            return False
        except BlockingIOError:
            return True
        finally:
            fh.close()


def list_sessions(root: Path | None = None) -> list[Session]:
    base = root or SESSIONS_DIR
    if not base.exists():
        return []
    out = [Session(p.name, base) for p in base.iterdir() if p.is_dir() and (p / "session.json").exists()]
    return sorted(out, key=lambda s: s.meta().get("created", ""), reverse=True)
