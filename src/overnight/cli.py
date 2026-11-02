"""`overnight init-demo` builds the synthetic warehouse; `overnight run` runs one night;
`overnight eval --runs N` runs N fresh nights and scores them against demo/expected.json."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from overnight import attacks as attack_lib
from overnight import demo_data
from overnight.agent import Limits
from overnight.evaluate import rag_summary, write_summary
from overnight.llm import LLM, HttpLLM, LLMResponse
from overnight.offline import NullAgent, OfflinePolicy
from overnight.orchestrator import RunResult, run
from overnight.rag import Embedder, HashEmbedder, HttpEmbedder


class Metered:
    """Saves the key's spend after every model call, so a killed run is still counted."""

    def __init__(self, llm: LLM, file: Path) -> None:
        self.llm, self.file = llm, file
        self.spent = json.loads(file.read_text(encoding="utf-8"))["tokens"] if file.exists() else 0

    def complete(self, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> LLMResponse:
        resp = self.llm.complete(messages, tools)
        self.add(resp.tokens)
        return resp

    def add(self, tokens: int) -> None:
        self.spent += tokens
        self.file.parent.mkdir(exist_ok=True)
        self.file.write_text(json.dumps({"tokens": self.spent}), encoding="utf-8")


def add_spend(tokens: int, file: Path = Path("state") / "spend.json") -> None:
    """Add tokens spent outside the LLM calls (embeddings) to the key's counter."""
    if tokens:
        spent = json.loads(file.read_text(encoding="utf-8"))["tokens"] if file.exists() else 0
        file.parent.mkdir(exist_ok=True)
        file.write_text(json.dumps({"tokens": spent + tokens}), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="overnight")
    p.add_argument("cmd", choices=["init-demo", "run", "eval", "rag-eval", "attack-eval"])
    p.add_argument("--root", type=Path, default=Path.cwd(), help="where runs/ and state/ live")
    p.add_argument("--workspace", type=Path, help="inputs (default: <root>/demo)")
    p.add_argument("--vault", type=Path, help="Obsidian vault (default: <root>/vault)")
    p.add_argument("--llm", choices=["offline", "http", "null"], default="offline")
    p.add_argument("--today", type=date.fromisoformat,
                   help="default: real date for run, the demo's fixed date for evals")
    p.add_argument("--runs", type=int, default=3, help="eval: how many fresh runs")
    p.add_argument("--only", help="attack-eval: comma-separated attack ids (default: all)")
    p.add_argument("--embed", choices=["hash", "http"], default="hash",
                   help="wiki search vectors: hash (offline, not semantic) or the API's model")
    a = p.parse_args(argv)
    # evals pin the date: otherwise "overdue" drifts with the calendar and runs aren't comparable
    a.today = a.today or (demo_data.TODAY if "eval" in a.cmd else date.today())
    ws = a.workspace or a.root / "demo"

    if a.cmd == "init-demo":
        print("warehouse:", demo_data.build(ws / "warehouse.duckdb"))
        return 0
    embedder: Embedder = HashEmbedder()
    if a.embed == "http":
        url, key = os.getenv("OVERNIGHT_LLM_BASE_URL"), os.getenv("OVERNIGHT_LLM_API_KEY")
        if not (url and key):
            p.error("set OVERNIGHT_LLM_BASE_URL and _API_KEY (see .env.example)")
        embedder = HttpEmbedder(url, key, os.getenv("OVERNIGHT_EMBED_MODEL", "bge-m3"))
    if a.cmd == "rag-eval":
        out = a.root / "eval" / f"rag-{datetime.now():%Y%m%d-%H%M%S}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rag_summary(ws, embedder), encoding="utf-8")
        print(out.read_text(encoding="utf-8"), f"saved: {out}", sep="\n")
        add_spend(embedder.tokens)
        return 0

    # Lifetime cap for a prepaid key, shared by all --root dirs: ./state/spend.json in the
    # directory you run from (where .env lives).
    # ponytail: checked between calls, so one call (<= ~50k tokens) can overshoot the cap.
    total = int(os.getenv("OVERNIGHT_TOTAL_TOKENS", 0))  # 0 = no lifetime cap
    llm: LLM = NullAgent() if a.llm == "null" else OfflinePolicy()
    meter = None
    ping = None
    if a.llm == "http":
        env = {k: os.getenv(f"OVERNIGHT_LLM_{k}") for k in ("BASE_URL", "API_KEY", "MODEL")}
        if not all(env.values()):
            p.error("set OVERNIGHT_LLM_BASE_URL, _API_KEY and _MODEL (see .env.example)")
        http = HttpLLM(env["BASE_URL"] or "", env["API_KEY"] or "", env["MODEL"] or "")
        llm = meter = Metered(http, Path("state") / "spend.json")
        ping = http.ping
    # eval: every run gets a fresh root, so no run sees another one's closed hypotheses;
    # attack-eval: every attack also gets its own copy of the workspace with a planted payload
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    attacks = (json.loads((ws / "attacks.json").read_text(encoding="utf-8"))
               if a.cmd == "attack-eval" else [])
    if a.only:
        attacks = [x for x in attacks if x["id"] in a.only.split(",")]
    if a.cmd == "run":
        jobs = [(ws, a.root)]
    elif a.cmd == "eval":
        jobs = [(ws, a.root / "eval" / stamp / str(i)) for i in range(1, a.runs + 1)]
    else:
        base = a.root / "eval" / f"attacks-{stamp}"
        jobs = [(attack_lib.prepare(ws, x, base / x["id"] / "demo"), base / x["id"])
                for x in attacks]
    results: list[RunResult] = []
    counted = 0  # embedding tokens already added to the counter
    for job_ws, root in jobs:
        per_run = int(os.getenv("OVERNIGHT_MAX_TOKENS", Limits.max_tokens))
        if meter and total:
            if meter.spent >= total:
                p.error(f"token budget of this key is spent: {meter.spent}/{total}")
            per_run = min(per_run, total - meter.spent)
        limits = Limits(max_tokens=per_run,
                        max_tool_calls=int(os.getenv("OVERNIGHT_MAX_TOOL_CALLS", 60)),
                        max_seconds=float(os.getenv("OVERNIGHT_MAX_SECONDS", 900)))
        res = run(job_ws, root, a.vault or root / "vault", llm, limits, a.today, ping, embedder)
        if meter:
            print(f"tokens: key total {meter.spent}" + (f"/{total}" if total else ""))
        print(f"run {res.run_id}: {res.status}")
        for g in res.gates:
            print(f"  [{'x' if g.passed else ' '}] {g.name} {g.detail}")
        print("report:", res.report)
        results.append(res)
        if meter:  # embedding tokens go to the same key counter
            meter.add(embedder.tokens - counted)
        else:
            add_spend(embedder.tokens - counted)
        counted = embedder.tokens

    if a.cmd == "eval":
        print("summary:", write_summary(results, ws, a.root / "eval" / stamp / "summary.md"))
        return 0
    if a.cmd == "attack-eval":
        expected = json.loads((ws / "expected.json").read_text(encoding="utf-8"))
        before = attack_lib.row_counts(ws / "warehouse.duckdb")
        rows = [attack_lib.judge(x, r, job_ws, before, expected)
                for x, r, (job_ws, _) in zip(attacks, results, jobs, strict=True)]
        out = base / "summary.md"
        out.write_text(attack_lib.summarize(rows, attacks), encoding="utf-8")
        print(out.read_text(encoding="utf-8"), f"saved: {out}", sep="\n")
        return 0
    return 0 if results[0].status == "ok" else 1
