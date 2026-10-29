"""`overnight init-demo` builds the synthetic warehouse; `overnight run` runs one night."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from overnight import demo_data
from overnight.agent import Limits
from overnight.llm import LLM, HttpLLM
from overnight.offline import OfflinePolicy
from overnight.orchestrator import run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="overnight")
    p.add_argument("cmd", choices=["init-demo", "run"])
    p.add_argument("--root", type=Path, default=Path.cwd(), help="where runs/ and state/ live")
    p.add_argument("--workspace", type=Path, help="inputs (default: <root>/demo)")
    p.add_argument("--vault", type=Path, help="Obsidian vault (default: <root>/vault)")
    p.add_argument("--llm", choices=["offline", "http"], default="offline")
    p.add_argument("--today", type=date.fromisoformat, default=date.today())
    a = p.parse_args(argv)
    ws = a.workspace or a.root / "demo"

    if a.cmd == "init-demo":
        print("warehouse:", demo_data.build(ws / "warehouse.duckdb"))
        return 0

    llm: LLM = OfflinePolicy()
    ping = None
    if a.llm == "http":
        env = {k: os.getenv(f"OVERNIGHT_LLM_{k}") for k in ("BASE_URL", "API_KEY", "MODEL")}
        if not all(env.values()):
            p.error("set OVERNIGHT_LLM_BASE_URL, _API_KEY and _MODEL (see .env.example)")
        http = HttpLLM(env["BASE_URL"] or "", env["API_KEY"] or "", env["MODEL"] or "")
        llm, ping = http, http.ping
    # Lifetime cap for a prepaid key, shared by all --root dirs: ./state/spend.json in the
    # directory you run from (where .env lives).
    # ponytail: checked between calls, so one call (<= ~50k tokens) can overshoot the cap.
    spend_file = Path("state") / "spend.json"
    spent = json.loads(spend_file.read_text())["tokens"] if spend_file.exists() else 0
    total = int(os.getenv("OVERNIGHT_TOTAL_TOKENS", 0))  # 0 = no lifetime cap
    per_run = int(os.getenv("OVERNIGHT_MAX_TOKENS", Limits.max_tokens))
    if a.llm == "http" and total:
        if spent >= total:
            p.error(f"token budget of this key is spent: {spent}/{total}")
        per_run = min(per_run, total - spent)
    limits = Limits(max_tokens=per_run,
                    max_tool_calls=int(os.getenv("OVERNIGHT_MAX_TOOL_CALLS", 60)),
                    max_seconds=float(os.getenv("OVERNIGHT_MAX_SECONDS", 900)))

    res = run(ws, a.root, a.vault or a.root / "vault", llm, limits, a.today, ping)
    if a.llm == "http":
        used = json.loads((res.run_dir / "finalize.json").read_text())["usage"]["tokens"]
        spend_file.parent.mkdir(exist_ok=True)
        spend_file.write_text(json.dumps({"tokens": spent + used}))
        print(f"tokens: this run {used}, total {spent + used}" + (f"/{total}" if total else ""))
    print(f"run {res.run_id}: {res.status}")
    for g in res.gates:
        print(f"  [{'x' if g.passed else ' '}] {g.name} {g.detail}")
    print("report:", res.report)
    return 0 if res.status == "ok" else 1
