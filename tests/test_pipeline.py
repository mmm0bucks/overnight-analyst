"""End to end: whole pipeline with the offline policy on a temporary vault."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conftest import TODAY

from overnight.agent import Limits
from overnight.llm import LLMError, LLMResponse
from overnight.offline import OfflinePolicy
from overnight.orchestrator import RunResult, run

DEFAULT = Limits()


def _run(ws: Path, llm: Any = None, limits: Limits = DEFAULT) -> RunResult:
    return run(ws, ws.parent, ws.parent / "vault", llm or OfflinePolicy(), limits, TODAY)


def _state(ws: Path) -> dict[str, str]:
    hyps = json.loads((ws.parent / "state" / "hypotheses.json").read_text(encoding="utf-8"))
    return {h["id"]: h["status"] for h in hyps}


def test_golden_run(ws: Path) -> None:
    res = _run(ws)
    assert res.status == "ok", [g for g in res.gates if not g.passed]
    for f in ("collect", "analyze", "synthesize", "critique", "finalize"):
        assert (res.run_dir / f"{f}.json").exists()
    assert _state(ws) == {"H1": "confirmed", "H2": "confirmed", "H3": "confirmed",
                          "H4": "rejected", "H5": "inconclusive", "H6": "inconclusive",
                          "H7": "inconclusive", "H8": "inconclusive",
                          "H9": "confirmed"}  # offline: no SQL -> inconclusive, trusts H9's SQL
    assert res.report.read_text(encoding="utf-8").startswith("---")
    hyps_note = ws.parent / "vault/Overnight/Hypotheses.md"
    assert "overnight:begin" in hyps_note.read_text(encoding="utf-8")


def test_two_runs_same_day_do_not_collide(ws: Path) -> None:
    a, b = _run(ws), _run(ws)
    assert a.run_id != b.run_id and a.report != b.report
    runs = json.loads((ws.parent / "state" / "runs.json").read_text(encoding="utf-8"))
    assert [r["run_id"] for r in runs] == [a.run_id, b.run_id]


def test_preflight_failure_still_leaves_a_note(ws: Path) -> None:
    (ws / "warehouse.duckdb").unlink()
    res = _run(ws)
    assert res.status == "failed" and "warehouse.duckdb" in res.report.read_text(encoding="utf-8")


class FailingAnalyze(OfflinePolicy):
    def complete(self, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> LLMResponse:
        if "STAGE: analyze" in messages[0]["content"]:
            raise LLMError("HTTP 400: context length exceeded")
        return super().complete(messages, tools)


def test_failed_stage_gives_partial_and_keeps_memory(ws: Path) -> None:
    assert _run(ws, FailingAnalyze()).status == "partial"
    assert set(_state(ws).values()) == {"open"}  # untrusted run does not touch the backlog


def test_budget_stops_the_run(ws: Path) -> None:
    res = _run(ws, limits=Limits(max_tool_calls=2))
    assert res.status == "failed" and "tool calls" in res.gates[0].detail


MINUS = "\u2212"  # the character that broke it


def test_non_ascii_model_output_is_saved(ws: Path) -> None:
    """Regression: on Windows (cp1251) a minus sign in model output crashed writing
    analyze.json. CI also runs the tests without a UTF-8 locale to catch this."""
    f = ws / "hypotheses.json"
    text = f.read_text(encoding="utf-8").replace("more than once", f"more than once {MINUS}")
    f.write_text(text, encoding="utf-8")
    res = _run(ws)
    assert MINUS in (res.run_dir / "analyze.json").read_text(encoding="utf-8")


def test_stage_order_is_a_langgraph_graph() -> None:
    from overnight.orchestrator import night_graph

    mermaid = night_graph(lambda stage, st: {}).get_graph().draw_mermaid()
    for edge in ("__start__ -.-> collect", "collect -.-> analyze", "analyze -.-> synthesize",
                 "synthesize -.-> critique", "critique -.-> __end__", "analyze -.-> __end__",
                 "critique -.-> synthesize"):
        assert edge in mermaid


class Reviewer(OfflinePolicy):
    """Offline policy whose reviewer asks for a rewrite the first `strict` times."""

    def __init__(self, strict: int) -> None:
        self.strict, self.reviews, self.reviews_seen = strict, 0, list[Any]()

    def synthesize(self, inputs: dict[str, Any], results: list[Any]) -> LLMResponse:
        self.reviews_seen.append(inputs.get("review"))
        return super().synthesize(inputs, results)

    def critique(self, inputs: dict[str, Any], results: list[Any]) -> LLMResponse:
        self.reviews += 1
        if self.reviews <= self.strict:
            return LLMResponse(content=json.dumps({"verdict": "revise",
                                                   "issues": ["headline overstates"]}))
        return super().critique(inputs, results)


def test_revise_sends_the_report_back_once(ws: Path) -> None:
    llm = Reviewer(strict=1)
    res = _run(ws, llm)
    assert res.status == "ok" and llm.reviews == 2
    assert llm.reviews_seen == [None, {"verdict": "revise", "issues": ["headline overstates"]}]
    assert (res.run_dir / "synthesize.draft.json").exists()
    final = json.loads((res.run_dir / "finalize.json").read_text(encoding="utf-8"))
    assert final["usage"]["revisions"] == 1


def test_rewrite_loop_is_bounded(ws: Path) -> None:
    llm = Reviewer(strict=99)  # never satisfied
    res = _run(ws, llm)
    assert llm.reviews == 2 and res.status == "ok"  # "revise" still passes the gate
