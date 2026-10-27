"""Command line entry point: `overnight init-demo` and `overnight run`."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from overnight import demo_data
from overnight.config import Paths, limits_from_env, llm_from_env
from overnight.llm import LLM, HttpLLM
from overnight.offline import OfflinePolicy
from overnight.orchestrator import run


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="overnight")
    p.add_argument("--root", type=Path, default=Path.cwd(),
                   help="where runs/, state/ and vault/ live (default: cwd)")
    p.add_argument("--workspace", type=Path, default=None,
                   help="inputs folder (default: <root>/demo)")
    p.add_argument("--vault", type=Path, default=None,
                   help="Obsidian vault to publish into (default: <root>/vault)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-demo", help="generate the synthetic warehouse")
    r = sub.add_parser("run", help="run the overnight pipeline once")
    r.add_argument("--llm", choices=["offline", "http"], default="offline")
    r.add_argument("--today", type=date.fromisoformat, default=date.today())
    a = p.parse_args(argv)

    ws = a.workspace or a.root / "demo"
    paths = Paths.under(a.root, ws)
    if a.vault:
        paths = Paths(workspace=ws, runs=paths.runs, state=paths.state, vault=a.vault)

    if a.cmd == "init-demo":
        db = demo_data.build(ws / "warehouse.duckdb")
        print(f"synthetic warehouse written to {db}")
        return 0

    llm: LLM
    ping = None
    if a.llm == "http":
        http = HttpLLM(llm_from_env())
        llm, ping = http, http.ping
    else:
        llm = OfflinePolicy()
    res = run(paths=paths, llm=llm, limits=limits_from_env(), today=a.today, ping=ping)
    print(f"run {res.run_id}: {res.status}")
    for g in res.gates:
        print(f"  [{'x' if g.passed else ' '}] {g.name} {g.detail}")
    print(f"report: {res.report}")
    return 0 if res.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
