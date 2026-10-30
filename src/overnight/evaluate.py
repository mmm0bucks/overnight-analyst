"""Score repeated runs against the demo's ground truth (demo/expected.json)."""

from __future__ import annotations

import json
from pathlib import Path

from overnight.orchestrator import RunResult


def summarize(results: list[RunResult], expected: dict[str, str]) -> str:
    """Markdown: one row per run, then accuracy per hypothesis."""
    ids = sorted(expected)
    rows, correct = [], dict.fromkeys(ids, 0)
    for r in results:
        usage = json.loads((r.run_dir / "finalize.json").read_text())["usage"]
        analyze = r.run_dir / "analyze.json"
        got = {h["id"]: h["status"] for h in
               (json.loads(analyze.read_text())["hypotheses"] if analyze.exists() else [])}
        for h in ids:
            correct[h] += got.get(h) == expected[h]
        marks = [("✅ " if got.get(h) == expected[h] else "❌ ") + got.get(h, "—") for h in ids]
        rows.append(f"| {r.run_id} | {r.status} | {usage['tokens']} | {usage['seconds']} | "
                    + " | ".join(marks) + " |")
    n = len(results)
    total = sum(correct.values())
    head = "| run | status | tokens | seconds | " + " | ".join(ids) + " |"
    return "\n".join([
        f"# Eval: {n} run(s), {total}/{n * len(ids)} hypothesis checks correct", "",
        head, "|" + "---|" * (4 + len(ids)), *rows, "",
        "| hypothesis | expected | correct |", "|---|---|---|",
        *[f"| {h} | {expected[h]} | {correct[h]}/{n} |" for h in ids], ""])


def write_summary(results: list[RunResult], workspace: Path, out: Path) -> Path:
    expected = json.loads((workspace / "expected.json").read_text())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(summarize(results, expected), encoding="utf-8")
    return out
