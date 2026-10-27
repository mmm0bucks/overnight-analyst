"""The only component that writes to the Obsidian vault and to persistent state.

The agent writes only into its own run directory. Publishing is atomic (temp file +
rename), backs up what it replaces, redacts secret-looking strings, and never touches
human text outside the managed block markers.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from overnight.config import Paths
from overnight.gates import Gate
from overnight.schemas import AnalyzeOut, Hypothesis, SynthesizeOut
from overnight.tools import SourceLog

BEGIN, END = "<!-- overnight:begin -->", "<!-- overnight:end -->"
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|Bearer\s+[A-Za-z0-9._\-]{16,}|"
    r"(?i:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S+)"
)


def redact(text: str) -> str:
    return SECRET_RE.sub("[REDACTED]", text)


def atomic_write(path: Path, text: str, backup_dir: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup_dir is not None and path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def upsert_managed_block(existing: str | None, block: str, title: str) -> str:
    managed = f"{BEGIN}\n{block.rstrip()}\n{END}"
    if not existing:
        return f"# {title}\n\nNotes above and below the markers are yours.\n\n{managed}\n"
    if BEGIN in existing and END in existing:
        head, rest = existing.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        return f"{head}{managed}{tail}"
    return f"{existing.rstrip()}\n\n{managed}\n"


def render_report(run_id: str, today: str, status: str, report: SynthesizeOut | None,
                  gates: list[Gate], sources: SourceLog, usage: dict[str, Any]) -> str:
    failed = [g for g in gates if not g.passed]
    lines = [
        "---",
        f"date: {today}",
        f"run_id: {run_id}",
        f"status: {status}",
        "tags: [overnight, report]",
        "---",
        "",
        f"# {report.headline if report else 'Overnight run failed'}",
        "",
    ]
    if status != "ok":
        lines += [f"> [!warning] Status: {status}"]
        lines += [f"> - gate `{g.name}` failed: {g.detail}" for g in failed] or [">"]
        lines.append("")
    if report:
        for sec in report.sections:
            lines += [f"## {sec.title}", ""]
            lines += [f"- {b.text} [{', '.join(b.sources)}]" for b in sec.bullets] or ["- —"]
            lines.append("")
    lines += ["## Sources", ""]
    for s in sources.sources.values():
        arg = s.args.get("query") or s.args.get("page") or s.args.get("task_id") or ""
        lines.append(f"- **{s.id}** `{s.tool}` {('— `' + str(arg) + '`') if arg else ''}")
    lines += ["", f"_usage: {json.dumps(usage)}_", ""]
    return redact("\n".join(lines))


def render_hypotheses(hyps: list[Hypothesis]) -> str:
    rows = ["| id | hypothesis | status | last checked |", "|---|---|---|---|"]
    rows += [f"| {h.id} | {h.statement} | {h.status} | {h.last_checked or ''} |" for h in hyps]
    return "\n".join(rows)


def publish(*, paths: Paths, run_dir: Path, run_id: str, today: str, status: str,
            report: SynthesizeOut | None, analysis: AnalyzeOut | None,
            hypotheses: list[Hypothesis], gates: list[Gate], sources: SourceLog,
            usage: dict[str, Any]) -> Path:
    backup = run_dir / "backup"
    # 1. state: hypothesis statuses only change when the analysis passed its gates
    trusted = status == "ok"
    if analysis and trusted:
        res = {h.id: h for h in analysis.hypotheses}
        for h in hypotheses:
            if h.id in res:
                h.status = res[h.id].status
                h.last_checked = today
    atomic_write(paths.state / "hypotheses.json",
                 json.dumps([h.model_dump() for h in hypotheses], indent=1, ensure_ascii=False),
                 backup)
    runs_file = paths.state / "runs.json"
    runs = json.loads(runs_file.read_text(encoding="utf-8")) if runs_file.exists() else []
    runs.append({"run_id": run_id, "date": today, "status": status, "usage": usage})
    atomic_write(runs_file, json.dumps(runs, indent=1), backup)

    # 2. vault
    report_path = paths.vault / "Overnight" / "Reports" / f"{today} {run_id}.md"
    atomic_write(report_path, render_report(run_id, today, status, report, gates, sources, usage))
    hyp_note = paths.vault / "Overnight" / "Hypotheses.md"
    existing = hyp_note.read_text(encoding="utf-8") if hyp_note.exists() else None
    atomic_write(hyp_note, upsert_managed_block(existing, render_hypotheses(hypotheses),
                                                "Hypotheses"), backup)
    return report_path
