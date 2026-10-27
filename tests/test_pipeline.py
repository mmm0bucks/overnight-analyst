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
    hyps = json.loads((ws.parent / "state" / "hypotheses.json").read_text())
    return {h["id"]: h["status"] for h in hyps}


def test_golden_run(ws: Path) -> None:
    res = _run(ws)
    assert res.status == "ok", [g for g in res.gates if not g.passed]
    for f in ("collect", "analyze", "synthesize", "critique", "finalize"):
        assert (res.run_dir / f"{f}.json").exists()
    assert _state(ws) == {"H1": "confirmed", "H2": "confirmed", "H3": "confirmed",
                          "H4": "rejected", "H5": "open"}
    assert res.report.read_text().startswith("---")
    assert "overnight:begin" in (ws.parent / "vault/Overnight/Hypotheses.md").read_text()


def test_two_runs_same_day_do_not_collide(ws: Path) -> None:
    a, b = _run(ws), _run(ws)
    assert a.run_id != b.run_id and a.report != b.report
    runs = json.loads((ws.parent / "state" / "runs.json").read_text())
    assert [r["run_id"] for r in runs] == [a.run_id, b.run_id]


def test_preflight_failure_still_leaves_a_note(ws: Path) -> None:
    (ws / "warehouse.duckdb").unlink()
    res = _run(ws)
    assert res.status == "failed" and "warehouse.duckdb" in res.report.read_text()


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
