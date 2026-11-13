"""Split a role-play script file into eval case folders: transcript.txt, quick_notes.txt, visit_meta.json, answer_key.md."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def split(script_path: Path, out_dir: Path) -> list[str]:
    text = script_path.read_text("utf-8")
    made = []
    for m in re.finditer(r"^## Case (\d+): (.+?)$(.*?)(?=^## Case |\Z)", text, re.M | re.S):
        num, title, body = m.group(1), m.group(2).strip(), m.group(3)
        qn = re.search(r"\*\*Quick notes\*\*\s*```\s*\n(.*?)```", body, re.S)
        script = re.search(r"\*\*Script\*\*\s*\n(.*?)\n\*\*Answer key\*\*", body, re.S)
        key = re.search(r"\*\*Answer key\*\*\s*\n(.*?)(?=\n---|\Z)", body, re.S)
        d = out_dir / f"case{num}"
        d.mkdir(parents=True, exist_ok=True)
        lines = [l.strip() for l in script.group(1).strip().splitlines() if l.strip()]
        (d / "transcript.txt").write_text("\n".join(lines) + "\n", "utf-8")
        (d / "quick_notes.txt").write_text(qn.group(1).strip() + "\n" if qn else "", "utf-8")
        (d / "visit_meta.json").write_text(json.dumps({"date": "2026-11-12", "provider": "Dr. Hale",
                                                        "assistant": "Assistant", "visit_type": "limited exam",
                                                        "title": title}, indent=2) + "\n", "utf-8")
        (d / "answer_key.md").write_text(f"# Case {num}: {title}\n\n{key.group(1).strip() if key else ''}\n", "utf-8")
        made.append(d.name)
    return made


if __name__ == "__main__":
    print(split(Path(sys.argv[1]), Path(sys.argv[2])))
