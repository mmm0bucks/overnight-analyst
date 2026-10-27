"""Plain-code orchestrator around the LLM stages: preflight, order, budget, failure
isolation, artifacts, gates, publishing. The model gets none of these jobs."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from overnight.agent import Budget, BudgetExceeded, Limits, StageFailed, run_stage
from overnight.gates import Gate, run_gates, status
from overnight.llm import LLM, LLMError
from overnight.publisher import publish
from overnight.stages import STAGES, AnalyzeOut, SynthesizeOut
from overnight.tools import Toolbox

REQUIRED = ("tasks.json", "wiki", "warehouse.duckdb", "hypotheses.json")


@dataclass
class RunResult:
    run_id: str
    status: str
    run_dir: Path
    report: Path
    gates: list[Gate]


def run(workspace: Path, root: Path, vault: Path, llm: LLM, limits: Limits, today: date,
        ping: Callable[[], None] | None = None) -> RunResult:
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"  # unique per run
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True)
    log = (run_dir / "events.jsonl").open("a", encoding="utf-8")

    def emit(event: dict[str, Any]) -> None:
        log.write(json.dumps({"ts": f"{datetime.now():%H:%M:%S}", **event}, default=str) + "\n")
        log.flush()

    state_file = root / "state" / "hypotheses.json"
    seed = state_file if state_file.exists() else workspace / "hypotheses.json"
    hypotheses: list[dict[str, Any]] = json.loads(seed.read_text()) if seed.exists() else []
    for h in hypotheses:
        h.setdefault("status", "open")
    budget, box = Budget(limits), Toolbox(workspace, today, limits.max_sql_per_stage,
                                          limits.max_sql_rows)
    arts: dict[str, BaseModel] = {}
    errors: dict[str, str] = {}

    missing = [f for f in REQUIRED if not (workspace / f).exists()]
    try:
        if missing:
            raise RuntimeError(f"workspace incomplete: {', '.join(missing)} "
                               "(run `overnight init-demo`)")
        if ping:
            ping()
    except Exception as e:  # preflight failed: skip stages, still publish a note
        errors["preflight"] = str(e)

    open_hyps = [h for h in hypotheses if h["status"] in ("open", "inconclusive")]
    for stage in [] if errors else STAGES:
        if "collect" in stage.needs and "collect" not in arts:
            errors[stage.name] = "skipped: no collect output"
            continue
        inputs = {n: open_hyps if n == "hypotheses" else arts[n].model_dump()
                  for n in stage.needs if n == "hypotheses" or n in arts}
        box.sql_left = limits.max_sql_per_stage
        try:
            arts[stage.name] = run_stage(stage, llm, stage.user(today.isoformat(), inputs),
                                         box, budget, emit)
        except (StageFailed, LLMError, BudgetExceeded) as e:
            errors[stage.name] = str(e)
            emit({"event": "stage_failed", "stage": stage.name, "error": str(e)})
            if isinstance(e, BudgetExceeded):
                break
            continue
        (run_dir / f"{stage.name}.json").write_text(arts[stage.name].model_dump_json(indent=1))

    gates = run_gates(arts, errors, box.sources)
    result = status(gates, arts)
    analysis = arts.get("analyze")
    if result == "ok" and isinstance(analysis, AnalyzeOut):  # only trusted runs update memory
        found = {h.id: h.status for h in analysis.hypotheses}
        for h in hypotheses:
            if h["id"] in found:
                h.update(status=found[h["id"]], last_checked=today.isoformat())
    usage = budget.usage()
    (run_dir / "finalize.json").write_text(json.dumps(
        {"status": result, "gates": [g.__dict__ for g in gates], "usage": usage,
         "sources": [s.__dict__ for s in box.sources.values()]}, indent=1, default=str))
    synth = arts.get("synthesize")
    report = publish(root, vault, run_dir, run_id, today.isoformat(), result,
                     synth if isinstance(synth, SynthesizeOut) else None,
                     hypotheses, gates, box.sources, usage)
    emit({"event": "published", "status": result})
    log.close()
    return RunResult(run_id, result, run_dir, report, gates)
