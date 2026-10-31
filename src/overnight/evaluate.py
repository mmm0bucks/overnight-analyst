"""Score repeated runs against the demo's ground truth (demo/expected.json), and the wiki
search against labelled queries (demo/rag_eval.json)."""

from __future__ import annotations

import json
from pathlib import Path

from overnight.orchestrator import RunResult
from overnight.rag import Embedder, WikiIndex, chunk_pages


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


def rag_summary(workspace: Path, embedder: Embedder, k: int = 3) -> str:
    """Page-level recall@k and MRR for bm25, dense and hybrid search."""
    queries = json.loads((workspace / "rag_eval.json").read_text(encoding="utf-8"))
    index = WikiIndex(chunk_pages(workspace / "wiki"), embedder)
    rows = []
    for mode in ("bm25", "dense", "hybrid"):
        recall = mrr = 0.0
        for q in queries:
            pages = list(dict.fromkeys(c.page for c in index.search(q["q"], k=20, mode=mode)))
            relevant = set(q["relevant"])
            recall += len(relevant & set(pages[:k])) / len(relevant)
            mrr += next((1 / (i + 1) for i, p in enumerate(pages) if p in relevant), 0.0)
        rows.append(f"| {mode} | {recall / len(queries):.2f} | {mrr / len(queries):.2f} |")
    name = type(embedder).__name__
    return "\n".join([f"# Wiki search: {len(queries)} queries, embedder {name}", "",
                      f"| mode | recall@{k} | MRR |", "|---|---|---|", *rows, ""])
