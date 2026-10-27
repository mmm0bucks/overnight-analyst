"""Deterministic orchestrator around the LLM stages.

It owns everything the model should not be trusted with: preflight, budgets,
stage ordering, failure isolation, artifacts, quality gates and publishing.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from overnight.agent import StageFailed, run_stage
from overnight.budget import Budget, BudgetExceeded
from overnight.config import Limits, Paths
from overnight.gates import Gate, overall_status, run_gates
from overnight.llm import LLM, LLMError
from overnight.publisher import publish
from overnight.schemas import AnalyzeOut, Hypothesis, SynthesizeOut
from overnight.sources.tracker import LocalTracker
from overnight.sources.wiki import Wiki
from overnight.stages import STAGES
from overnight.tools import SourceLog, Toolbox


@dataclass
class RunResult:
    run_id: str
    status: str
    run_dir: Path
    report: Path | None
    gates: list[Gate]


class PreflightError(RuntimeError):
    pass


def new_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"  # unique even for same-day reruns


def preflight(paths: Paths, ping: Callable[[], None] | None) -> None:
    ws = paths.workspace
    missing = [p for p in ("tasks.json", "wiki", "warehouse.duckdb", "hypotheses.json")
               if not (ws / p).exists()]
    if missing:
        raise PreflightError(f"workspace incomplete: {', '.join(missing)} "
                             "(run `overnight init-demo`)")
    if ping is not None:
        try:
            ping()
        except Exception as e:
            raise PreflightError(f"LLM endpoint unreachable: {e}") from e


def load_hypotheses(paths: Paths) -> list[Hypothesis]:
    f = paths.state / "hypotheses.json"
    if not f.exists():
        f = paths.workspace / "hypotheses.json"  # seed backlog on first run
    return [Hypothesis.model_validate(h) for h in json.loads(f.read_text(encoding="utf-8"))]


def run(*, paths: Paths, llm: LLM, limits: Limits, today: date,
        ping: Callable[[], None] | None = None, run_id: str | None = None) -> RunResult:
    run_id = run_id or new_run_id()
    run_dir = paths.runs / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    events = (run_dir / "events.jsonl").open("a", encoding="utf-8")

    def emit(e: dict[str, Any]) -> None:
        e = {"ts": datetime.now().isoformat(timespec="seconds"), **e}
        events.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        events.flush()

    budget = Budget(limits)
    sources = SourceLog()
    artifacts: dict[str, BaseModel] = {}
    status_by_stage: dict[str, str] = {}
    budget_error: str | None = None
    today_s = today.isoformat()
    hypotheses: list[Hypothesis] = []

    try:
        try:
            preflight(paths, ping)
            emit({"event": "preflight", "ok": True})
        except PreflightError as e:
            emit({"event": "preflight", "ok": False, "error": str(e)})
            status_by_stage["preflight"] = f"failed: {e}"
            gates = [Gate("preflight", False, str(e))]
            report = publish(paths=paths, run_dir=run_dir, run_id=run_id, today=today_s,
                             status="failed", report=None, analysis=None,
                             hypotheses=load_hypotheses(paths) if _has_seed(paths) else [],
                             gates=gates, sources=sources, usage=budget.snapshot())
            _dump(run_dir / "stages.json", status_by_stage)
            return RunResult(run_id, "failed", run_dir, report, gates)

        hypotheses = load_hypotheses(paths)
        ws = paths.workspace
        box = Toolbox(LocalTracker(ws / "tasks.json"), Wiki(ws / "wiki"),
                      ws / "warehouse.duckdb", today, limits.max_sql_per_stage,
                      limits.max_sql_rows)
        open_hyps = [h.model_dump() for h in hypotheses if h.status in ("open", "inconclusive")]

        for stage in STAGES:
            inputs: dict[str, Any] = {}
            for need in stage.needs:
                if need == "hypotheses":
                    inputs["hypotheses"] = open_hyps
                elif need in artifacts:
                    inputs[need] = artifacts[need].model_dump()
            if "collect" in stage.needs and "collect" not in artifacts:
                status_by_stage[stage.name] = "skipped: collect missing"
                continue
            box.reset_quota()
            emit({"event": "stage_start", "stage": stage.name})
            try:
                out = run_stage(stage=stage.name, llm=llm, system=stage.system(),
                                user=stage.user(today_s, inputs),
                                tools=box.tools(stage.tools), schema=stage.schema,
                                budget=budget, sources=sources, emit=emit)
            except BudgetExceeded as e:
                budget_error = str(e)
                status_by_stage[stage.name] = f"failed: {e}"
                emit({"event": "stage_failed", "stage": stage.name, "error": str(e)})
                break  # no point starting the next stage
            except (StageFailed, LLMError) as e:
                status_by_stage[stage.name] = f"failed: {e}"
                emit({"event": "stage_failed", "stage": stage.name, "error": str(e)})
                continue
            artifacts[stage.name] = out
            status_by_stage[stage.name] = "ok"
            _dump(run_dir / f"{stage.name}.json", out.model_dump())
            emit({"event": "stage_ok", "stage": stage.name, **budget.snapshot()})

        gates = run_gates(artifacts, status_by_stage, sources, budget_error)
        status = overall_status(gates, artifacts)
        _dump(run_dir / "stages.json", status_by_stage)
        _dump(run_dir / "sources.json", sources.dump())
        _dump(run_dir / "finalize.json", {"status": status,
                                          "gates": [g.__dict__ for g in gates],
                                          "usage": budget.snapshot()})
        synth = artifacts.get("synthesize")
        analysis = artifacts.get("analyze")
        report = publish(
            paths=paths, run_dir=run_dir, run_id=run_id, today=today_s, status=status,
            report=synth if isinstance(synth, SynthesizeOut) else None,
            analysis=analysis if isinstance(analysis, AnalyzeOut) else None,
            hypotheses=hypotheses, gates=gates, sources=sources, usage=budget.snapshot())
        emit({"event": "published", "status": status, "report": str(report)})
        return RunResult(run_id, status, run_dir, report, gates)
    finally:
        events.close()


def _has_seed(paths: Paths) -> bool:
    return (paths.state / "hypotheses.json").exists() or \
        (paths.workspace / "hypotheses.json").exists()


def _dump(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
