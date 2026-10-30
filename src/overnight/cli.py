"""`overnight init-demo` builds the synthetic warehouse; `overnight run` runs one night;
`overnight eval --runs N` runs N fresh nights and scores them against demo/expected.json."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from overnight import demo_data
from overnight.agent import Limits
from overnight.evaluate import write_summary
from overnight.llm import LLM, HttpLLM, LLMResponse
from overnight.offline import OfflinePolicy
from overnight.orchestrator import RunResult, run


class Metered:
    """Saves the key's spend after every model call, so a killed run is still counted."""

    def __init__(self, llm: LLM, file: Path) -> None:
        self.llm, self.file = llm, file
        self.spent = json.loads(file.read_text())["tokens"] if file.exists() else 0

    def complete(self, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> LLMResponse:
        resp = self.llm.complete(messages, tools)
        self.spent += resp.tokens
        self.file.parent.mkdir(exist_ok=True)
        self.file.write_text(json.dumps({"tokens": self.spent}))
        return resp


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="overnight")
    p.add_argument("cmd", choices=["init-demo", "run", "eval"])
    p.add_argument("--root", type=Path, default=Path.cwd(), help="where runs/ and state/ live")
    p.add_argument("--workspace", type=Path, help="inputs (default: <root>/demo)")
    p.add_argument("--vault", type=Path, help="Obsidian vault (default: <root>/vault)")
    p.add_argument("--llm", choices=["offline", "http"], default="offline")
    p.add_argument("--today", type=date.fromisoformat, default=date.today())
    p.add_argument("--runs", type=int, default=3, help="eval: how many fresh runs")
    a = p.parse_args(argv)
    ws = a.workspace or a.root / "demo"

    if a.cmd == "init-demo":
        print("warehouse:", demo_data.build(ws / "warehouse.duckdb"))
        return 0

    # Lifetime cap for a prepaid key, shared by all --root dirs: ./state/spend.json in the
    # directory you run from (where .env lives).
    # ponytail: checked between calls, so one call (<= ~50k tokens) can overshoot the cap.
    total = int(os.getenv("OVERNIGHT_TOTAL_TOKENS", 0))  # 0 = no lifetime cap
    llm: LLM = OfflinePolicy()
    meter = None
    ping = None
    if a.llm == "http":
        env = {k: os.getenv(f"OVERNIGHT_LLM_{k}") for k in ("BASE_URL", "API_KEY", "MODEL")}
        if not all(env.values()):
            p.error("set OVERNIGHT_LLM_BASE_URL, _API_KEY and _MODEL (see .env.example)")
        http = HttpLLM(env["BASE_URL"] or "", env["API_KEY"] or "", env["MODEL"] or "")
        llm = meter = Metered(http, Path("state") / "spend.json")
        ping = http.ping
    # eval: every run gets a fresh root, so no run sees another one's closed hypotheses
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    roots = ([a.root] if a.cmd == "run" else
             [a.root / "eval" / stamp / str(i) for i in range(1, a.runs + 1)])
    results: list[RunResult] = []
    for root in roots:
        per_run = int(os.getenv("OVERNIGHT_MAX_TOKENS", Limits.max_tokens))
        if meter and total:
            if meter.spent >= total:
                p.error(f"token budget of this key is spent: {meter.spent}/{total}")
            per_run = min(per_run, total - meter.spent)
        limits = Limits(max_tokens=per_run,
                        max_tool_calls=int(os.getenv("OVERNIGHT_MAX_TOOL_CALLS", 60)),
                        max_seconds=float(os.getenv("OVERNIGHT_MAX_SECONDS", 900)))
        res = run(ws, root, a.vault or root / "vault", llm, limits, a.today, ping)
        if meter:
            print(f"tokens: key total {meter.spent}" + (f"/{total}" if total else ""))
        print(f"run {res.run_id}: {res.status}")
        for g in res.gates:
            print(f"  [{'x' if g.passed else ' '}] {g.name} {g.detail}")
        print("report:", res.report)
        results.append(res)

    if a.cmd == "eval":
        print("summary:", write_summary(results, ws, a.root / "eval" / stamp / "summary.md"))
        return 0
    return 0 if results[0].status == "ok" else 1
