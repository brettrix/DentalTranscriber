"""Maintenance commands. `python manage.py purge --older-than 7d` deletes old sessions, audio and traces."""
from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime, timedelta, timezone

from pipeline.storage import SESSIONS_DIR, list_sessions


def _parse_age(text: str) -> timedelta:
    m = re.fullmatch(r"(\d+)([dh])", text)
    if not m:
        raise SystemExit("--older-than takes e.g. 7d or 12h")
    n = int(m.group(1))
    return timedelta(days=n) if m.group(2) == "d" else timedelta(hours=n)


def purge(older_than: str = "7d", dry_run: bool = False) -> list[str]:
    cutoff = datetime.now(timezone.utc) - _parse_age(older_than)
    removed = []
    for s in list_sessions():
        created = s.meta().get("created")
        if created and datetime.fromisoformat(created) < cutoff:
            removed.append(s.id)
            if not dry_run:
                shutil.rmtree(s.dir)
    return removed


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("purge")
    p.add_argument("--older-than", default="7d")
    p.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.cmd == "purge":
        removed = purge(args.older_than, args.dry_run)
        print(f"{'would remove' if args.dry_run else 'removed'} {len(removed)} session(s) from {SESSIONS_DIR}")


if __name__ == "__main__":
    main()
