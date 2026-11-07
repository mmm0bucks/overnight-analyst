"""Orchestrator around the LLM stages: preflight, order, budget, failure isolation,
artifacts, gates, publishing. The model gets none of these jobs.

The stage order is a LangGraph StateGraph: each stage is a node, and conditional edges
end the night early (failed preflight, spent budget). Gates and publishing stay plain code
after the graph: the framework routes, our code decides what is true.

Every step is saved to a SQLite checkpointer under state/, keyed by the run id, so a night
that crashed can be resumed without paying again for finished stages, and a night can pause
before publishing until a human approves it."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from functools import partial
from itertools import pairwise
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from overnight.agent import Budget, BudgetExceeded, Limits, StageFailed, run_stage
from overnight.gates import Gate, run_gates, status
from overnight.llm import LLM, LLMError
from overnight.mcp_sources import McpSources
from overnight.publisher import publish
from overnight.rag import Embedder
from overnight.stages import STAGES, AnalyzeOut, Stage, SynthesizeOut
from overnight.tools import Source, Toolbox

REQUIRED = ("tasks.json", "wiki", "warehouse.duckdb", "hypotheses.json")


class Night(TypedDict):
    """Graph state. Plain JSON only, so a checkpointer can save it as is."""

    arts: dict[str, dict[str, Any]]  # stage name -> its validated output
    errors: dict[str, str]  # stage name -> why it failed or was skipped
    stop: bool  # the budget is spent: no further stage may run
    revisions: int  # how many times the report went back to the editor
    today: str  # the night's date, so a resumed run uses the same one
    sources: dict[str, dict[str, Any]]  # tool results so far: gates need them after a resume
    usage: dict[str, int]  # tokens and tool calls so far, carried over a resume
    approve: bool  # pause for a human before publishing
    approved: bool | None  # the human's answer; None if nobody was asked


MAX_REVISIONS = 1  # one rewrite after a "revise" verdict; then the gates have the last word


def ask_human(st: Night) -> dict[str, Any]:
    """Pause here until `overnight approve` or `reject`; the answer is what interrupt returns.
    Nothing happens before interrupt(), because the node restarts from the top on resume."""
    report, review = st["arts"].get("synthesize", {}), st["arts"].get("critique", {})
    answer = interrupt({"headline": report.get("headline"), "review": review.get("verdict")})
    return {"approved": bool(answer)}


def night_graph(do_stage: Callable[[Stage, Night], dict[str, Any]],
                checkpointer: Any = None) -> Any:
    """START -> collect -> analyze -> synthesize -> critique -> [approve] -> END, leaving
    early on a failed preflight or a spent budget. A failed stage does not stop the night.
    A "revise" verdict sends the report back to synthesize once, with the reviewer's issues."""
    g = StateGraph(Night)
    names = [s.name for s in STAGES]
    for s in STAGES:
        g.add_node(s.name, partial(do_stage, s))
    # the target lists only tell LangGraph where an edge may go, for the drawn graph
    g.add_conditional_edges(START, lambda st: END if st["errors"] else names[0],
                            [names[0], END])
    for a, b in pairwise(names):
        g.add_conditional_edges(a, lambda st, b=b: END if st["stop"] else b, [b, END])

    def after_review(st: Night) -> str:
        verdict = st["arts"].get("critique", {}).get("verdict")
        again = verdict == "revise" and st["revisions"] < MAX_REVISIONS and not st["stop"]
        return "synthesize" if again else "approve" if st["approve"] else END

    g.add_node("approve", partial(ask_human))
    g.add_conditional_edges(names[-1], after_review, ["synthesize", "approve", END])
    g.add_edge("approve", END)
    return g.compile(checkpointer=checkpointer)


def new_run_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"  # unique per run


@dataclass
class RunResult:
    run_id: str
    status: str
    run_dir: Path
    report: Path | None  # None while the night waits for approval
    gates: list[Gate]


def run(workspace: Path, root: Path, vault: Path, llm: LLM, limits: Limits, today: date,
        ping: Callable[[], None] | None = None, embedder: Embedder | None = None, *,
        approve: bool = False, resume: str | None = None,
        decision: bool | None = None, run_id: str | None = None,
        mcp: Path | None = None) -> RunResult:
    """One night. `resume` continues a saved run by id (after a crash, or with the human's
    `decision` when it waits for approval). `run_id` lets a caller know the id up front.
    `mcp` is a config of MCP servers for the tracker and wiki tools (see mcp_sources.py)."""
    run_id = resume or run_id or new_run_id()
    run_dir = root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=bool(resume))
    (root / "state").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(root / "state" / "checkpoints.sqlite", check_same_thread=False)
    config: Any = {"configurable": {"thread_id": run_id}}
    log = (run_dir / "events.jsonl").open("a", encoding="utf-8")

    def emit(event: dict[str, Any]) -> None:
        log.write(json.dumps({"ts": f"{datetime.now():%H:%M:%S}", **event}, default=str) + "\n")
        log.flush()

    state_file = root / "state" / "hypotheses.json"
    seed = state_file if state_file.exists() else workspace / "hypotheses.json"
    hypotheses: list[dict[str, Any]] = (json.loads(seed.read_text(encoding="utf-8"))
                                        if seed.exists() else [])
    for h in hypotheses:
        h.setdefault("status", "open")
    errors: dict[str, str] = {}
    graph = None  # built below; do_stage needs the objects first

    def saved() -> Any:
        return graph.get_state(config) if graph else None

    open_hyps = [h for h in hypotheses if h["status"] in ("open", "inconclusive")]

    def do_stage(stage: Stage, st: Night) -> dict[str, Any]:
        done, failed = st["arts"], dict(st["errors"])
        if "collect" in stage.needs and "collect" not in done:
            failed[stage.name] = "skipped: no collect output"
            return {"errors": failed}
        inputs = {n: open_hyps if n == "hypotheses" else done[n]
                  for n in stage.needs if n == "hypotheses" or n in done}
        redo = stage.name == "synthesize" and "critique" in done
        if redo:  # keep the first draft and its review next to the final ones
            inputs["review"] = done["critique"]
            for name in ("synthesize", "critique"):
                (run_dir / f"{name}.json").replace(run_dir / f"{name}.draft.json")
        box.new_stage()
        try:
            out = run_stage(stage, llm, stage.user(today.isoformat(), inputs), box, budget, emit)
        except (StageFailed, LLMError, BudgetExceeded) as e:
            failed[stage.name] = str(e)
            emit({"event": "stage_failed", "stage": stage.name, "error": str(e)})
            return {"errors": failed, "stop": isinstance(e, BudgetExceeded), **progress()}
        (run_dir / f"{stage.name}.json").write_text(out.model_dump_json(indent=1),
                                                 encoding="utf-8")
        return {"arts": {**done, stage.name: out.model_dump(mode="json")},
                "revisions": st["revisions"] + int(redo), **progress()}

    def progress() -> dict[str, Any]:  # what a resumed run must not lose
        return {"sources": {k: json.loads(json.dumps(asdict(v), default=str))
                            for k, v in box.sources.items()},
                "usage": {"tokens": budget.tokens, "tool_calls": budget.tool_calls}}

    graph = night_graph(do_stage, SqliteSaver(conn))
    before = saved().values if resume else None
    if resume and not before:
        raise ValueError(f"no saved run {run_id} under {root / 'state'}")
    if before:
        today = date.fromisoformat(before["today"])
    budget, box = Budget(limits), Toolbox(workspace, today, limits.max_sql_per_stage,
                                          limits.max_sql_rows, embedder)
    try:  # tracker and wiki over MCP, if configured; a source that does not start fails
        box.remote = McpSources.load(mcp, workspace, today) if mcp else None  # the preflight
    except Exception as e:
        if before:
            raise
        errors["preflight"] = f"MCP sources: {e}"
    try:
        if before:  # carry over what the crashed or paused part already did
            box.sources = {k: Source(**v) for k, v in before["sources"].items()}
            budget.tokens = before["usage"]["tokens"]
            budget.tool_calls = before["usage"]["tool_calls"]
            emit({"event": "resumed", "from": list(saved().next), "decision": decision})
            night = graph.invoke(None if decision is None else Command(resume=decision), config)
        else:
            missing = [f for f in REQUIRED if not (workspace / f).exists()]
            try:
                if missing:
                    raise RuntimeError(f"workspace incomplete: {', '.join(missing)} "
                                       "(run `overnight init-demo`)")
                if ping:
                    ping()
            except Exception as e:  # preflight failed: skip stages, still publish a note
                errors["preflight"] = str(e)
            night = graph.invoke({"arts": {}, "errors": errors, "stop": False, "revisions": 0,
                                  "today": today.isoformat(), "sources": {},
                                  "usage": {"tokens": 0, "tool_calls": 0},
                                  "approve": approve, "approved": None}, config)
    finally:
        if box.remote:
            box.remote.close()
    if saved().next:  # paused before publishing: nothing is written to the vault yet
        emit({"event": "waiting_for_approval", "report": night["arts"].get("synthesize")})
        log.close()
        conn.close()
        return RunResult(run_id, "waiting", run_dir, None, [])
    errors = night["errors"]
    arts = {s.name: s.schema.model_validate(night["arts"][s.name])
            for s in STAGES if s.name in night["arts"]}

    gates = run_gates(arts, errors, box.sources, {h["id"]: h["statement"] for h in open_hyps})
    if night["approved"] is not None:
        gates.append(Gate("human_approved", night["approved"],
                          "" if night["approved"] else "rejected at approval"))
    result = status(gates, arts)
    analysis = arts.get("analyze")
    if result == "ok" and isinstance(analysis, AnalyzeOut):  # only trusted runs update memory
        found = {h.id: h.status for h in analysis.hypotheses}
        for h in open_hyps:  # only what was asked: closed hypotheses are not re-decided here
            if h["id"] in found:
                h.update(status=found[h["id"]], last_checked=today.isoformat())
    usage = {**budget.usage(), "revisions": night["revisions"]}
    (run_dir / "finalize.json").write_text(json.dumps(
        {"status": result, "gates": [g.__dict__ for g in gates], "usage": usage,
         "sources": [s.__dict__ for s in box.sources.values()]}, indent=1, default=str),
        encoding="utf-8")
    synth = arts.get("synthesize")
    report = publish(root, vault, run_dir, run_id, today.isoformat(), result,
                     synth if isinstance(synth, SynthesizeOut) else None,
                     hypotheses, gates, box.sources, usage)
    emit({"event": "published", "status": result})
    log.close()
    conn.close()
    return RunResult(run_id, result, run_dir, report, gates)
