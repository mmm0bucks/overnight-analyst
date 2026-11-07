"""HTTP API around the same nights the CLI runs: start one, ask how it goes, read the report,
approve or reject it. `overnight serve` starts it.

Nights run one at a time in a background thread: they share state/ (memory, checkpoints,
spend) and the model key, so two at once would only race. The model is chosen like in the
CLI (`serve --llm offline|http`); OVERNIGHT_API_TOKEN, if set, is required as X-API-Key.
"""

from __future__ import annotations

import json
import os
import secrets
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from overnight.agent import Limits
from overnight.cli import Metered, make_llm
from overnight.orchestrator import RunResult, new_run_id, run


class Start(BaseModel):
    approve: bool = False  # wait for POST /runs/{id}/approve before publishing


def create_app(root: Path, llm_kind: str = "offline") -> FastAPI:
    llm, ping = make_llm(llm_kind)
    token = os.getenv("OVERNIGHT_API_TOKEN")
    pool = ThreadPoolExecutor(max_workers=1)  # one night at a time
    jobs: dict[str, Future[RunResult]] = {}
    app = FastAPI(title="overnight-analyst", version="0.1.0")

    def auth(x_api_key: str | None = Header(default=None)) -> None:
        if token and not (x_api_key and secrets.compare_digest(x_api_key, token)):
            raise HTTPException(401, "missing or wrong X-API-Key")

    total = int(os.getenv("OVERNIGHT_TOTAL_TOKENS", 0))  # the key's lifetime cap, as in the CLI

    def night(key: str, **kw: Any) -> Future[RunResult]:
        per_run = int(os.getenv("OVERNIGHT_MAX_TOKENS", Limits.max_tokens))
        if isinstance(llm, Metered) and total:
            if llm.spent >= total:
                raise HTTPException(402, f"token budget of this key is spent: {llm.spent}")
            per_run = min(per_run, total - llm.spent)
        limits = Limits(max_tokens=per_run)
        jobs[key] = pool.submit(run, root / "demo", root, root / "vault", llm, limits,
                                date.today(), ping, **kw)
        return jobs[key]

    def state(run_id: str) -> dict[str, Any]:
        job = jobs.get(run_id)
        if job and not job.done():
            return {"run_id": run_id, "status": "running"}
        if job and job.exception():
            return {"run_id": run_id, "status": "error", "error": str(job.exception())}
        if job and job.result().status == "waiting":
            return {"run_id": run_id, "status": "waiting"}
        run_dir = root / "runs" / run_id  # also nights started before a restart
        final, events = run_dir / "finalize.json", run_dir / "events.jsonl"
        if not final.exists():
            last = events.read_text(encoding="utf-8").splitlines()[-1:] if events.exists() else []
            if last and json.loads(last[0])["event"] == "waiting_for_approval":
                return {"run_id": run_id, "status": "waiting"}
            raise HTTPException(404, f"no run {run_id}")
        data = json.loads(final.read_text(encoding="utf-8"))
        return {"run_id": run_id, "status": data["status"], "usage": data["usage"],
                "failed_gates": [g["name"] for g in data["gates"] if not g["passed"]]}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/runs", status_code=202, dependencies=[Depends(auth)])
    def start(body: Start | None = None) -> dict[str, Any]:
        run_id = new_run_id()
        night(run_id, run_id=run_id, approve=bool(body and body.approve))
        return {"run_id": run_id, "status": "running"}

    @app.get("/runs/{run_id}", dependencies=[Depends(auth)])
    def status(run_id: str) -> dict[str, Any]:
        return state(run_id)

    @app.get("/runs/{run_id}/report", response_class=PlainTextResponse,
             dependencies=[Depends(auth)])
    def report(run_id: str) -> str:
        found = state(run_id)
        if found["status"] in ("running", "waiting", "error"):
            raise HTTPException(409, f"run {run_id} is {found['status']}, no report yet")
        notes = (root / "vault" / "Overnight" / "Reports").glob(f"* {run_id}.md")
        note = next(notes, None)
        if not note:
            raise HTTPException(404, f"no report for {run_id}")
        return note.read_text(encoding="utf-8")

    def decide(run_id: str, decision: bool) -> dict[str, Any]:
        if state(run_id)["status"] != "waiting":
            raise HTTPException(409, f"run {run_id} is not waiting for approval")
        night(run_id, resume=run_id, decision=decision)
        return {"run_id": run_id, "status": "running"}

    @app.post("/runs/{run_id}/approve", status_code=202, dependencies=[Depends(auth)])
    def approve(run_id: str) -> dict[str, Any]:
        return decide(run_id, True)

    @app.post("/runs/{run_id}/reject", status_code=202, dependencies=[Depends(auth)])
    def reject(run_id: str) -> dict[str, Any]:
        return decide(run_id, False)

    return app
