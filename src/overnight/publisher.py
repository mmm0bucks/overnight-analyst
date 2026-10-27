"""The only writer of the Obsidian vault and of the agent's state.

Writes are atomic (temp file + rename), the replaced file is backed up, secret-looking
strings are redacted, and shared notes are only changed inside managed-block markers.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from overnight.gates import Gate
from overnight.stages import SynthesizeOut
from overnight.tools import Source

BEGIN, END = "<!-- overnight:begin -->", "<!-- overnight:end -->"
SECRET = re.compile(r"sk-[\w-]{16,}|Bearer\s+[\w.-]{16,}|"
                    r"(?i:password|secret|api[_-]?key|token)\s*[:=]\s*\S+")


def redact(text: str) -> str:
    return SECRET.sub("[REDACTED]", text)


def atomic_write(path: Path, text: str, backup_dir: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup_dir and path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def upsert_block(existing: str | None, block: str, title: str) -> str:
    managed = f"{BEGIN}\n{block}\n{END}"
    if not existing:
        return f"# {title}\n\nYour notes outside the markers are kept.\n\n{managed}\n"
    if BEGIN in existing and END in existing:
        head, rest = existing.split(BEGIN, 1)
        return head + managed + rest.split(END, 1)[1]
    return f"{existing.rstrip()}\n\n{managed}\n"


def render_report(run_id: str, today: str, status: str, report: SynthesizeOut | None,
                  gates: list[Gate], sources: dict[str, Source], usage: dict[str, Any]) -> str:
    out = ["---", f"date: {today}", f"run_id: {run_id}", f"status: {status}",
           "tags: [overnight, report]", "---", "",
           f"# {report.headline if report else 'Overnight run failed'}", ""]
    if status != "ok":
        out += [f"> [!warning] Status: {status}"]
        out += [f"> - `{g.name}`: {g.detail}" for g in gates if not g.passed] + [""]
    for sec in report.sections if report else []:
        out += [f"## {sec.title}", ""]
        out += [f"- {b.text} [{', '.join(b.sources)}]" for b in sec.bullets] + [""]
    out += ["## Sources", ""]
    for s in sources.values():
        arg = s.args.get("query") or s.args.get("page")
        out.append(f"- **{s.id}** `{s.tool}`" + (f" `{arg}`" if arg else ""))
    out += ["", f"_usage: {json.dumps(usage)}_", ""]
    return redact("\n".join(out))


def publish(root: Path, vault: Path, run_dir: Path, run_id: str, today: str, status: str,
            report: SynthesizeOut | None, hypotheses: list[dict[str, Any]],
            gates: list[Gate], sources: dict[str, Source], usage: dict[str, Any]) -> Path:
    backup = run_dir / "backup"
    state = root / "state"
    atomic_write(state / "hypotheses.json", json.dumps(hypotheses, indent=1), backup)
    runs_file = state / "runs.json"
    runs = json.loads(runs_file.read_text()) if runs_file.exists() else []
    runs.append({"run_id": run_id, "date": today, "status": status, "usage": usage})
    atomic_write(runs_file, json.dumps(runs, indent=1), backup)

    path = vault / "Overnight" / "Reports" / f"{today} {run_id}.md"
    atomic_write(path, render_report(run_id, today, status, report, gates, sources, usage))
    table = ["| id | hypothesis | status | last checked |", "|---|---|---|---|"]
    table += [f"| {h['id']} | {h['statement']} | {h['status']} | {h.get('last_checked', '')} |"
              for h in hypotheses]
    note = vault / "Overnight" / "Hypotheses.md"
    old = note.read_text(encoding="utf-8") if note.exists() else None
    atomic_write(note, upsert_block(old, "\n".join(table), "Hypotheses"), backup)
    return path
