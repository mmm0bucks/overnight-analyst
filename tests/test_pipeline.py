"""End-to-end: the full pipeline with the offline policy on a temporary vault."""

from __future__ import annotations

import json
from typing import Any

from conftest import TODAY

from overnight.config import Limits, Paths
from overnight.llm import LLMError, LLMResponse, Message
from overnight.offline import OfflinePolicy
from overnight.orchestrator import run


def test_golden_run(paths: Paths, limits: Limits) -> None:
    res = run(paths=paths, llm=OfflinePolicy(), limits=limits, today=TODAY)
    assert res.status == "ok", [g for g in res.gates if not g.passed]
    for f in ("collect", "analyze", "synthesize", "critique", "finalize", "sources", "stages"):
        assert (res.run_dir / f"{f}.json").exists()
    state = {h["id"]: h["status"] for h in
             json.loads((paths.state / "hypotheses.json").read_text())}
    assert state == {"H1": "confirmed", "H2": "confirmed", "H3": "confirmed",
                     "H4": "rejected", "H5": "open"}
    assert res.report is not None and res.report.read_text().startswith("---")
    assert "<!-- overnight:begin -->" in (paths.vault / "Overnight" / "Hypotheses.md").read_text()


def test_two_runs_same_day_do_not_collide(paths: Paths, limits: Limits) -> None:
    a = run(paths=paths, llm=OfflinePolicy(), limits=limits, today=TODAY)
    b = run(paths=paths, llm=OfflinePolicy(), limits=limits, today=TODAY)
    assert a.run_id != b.run_id and a.report != b.report
    runs = json.loads((paths.state / "runs.json").read_text())
    assert [r["run_id"] for r in runs] == [a.run_id, b.run_id]


def test_preflight_failure_still_leaves_a_note(paths: Paths, limits: Limits) -> None:
    (paths.workspace / "warehouse.duckdb").unlink()
    res = run(paths=paths, llm=OfflinePolicy(), limits=limits, today=TODAY)
    assert res.status == "failed"
    assert res.report is not None and "warehouse.duckdb" in res.report.read_text()


class FlakyAnalyze(OfflinePolicy):
    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        if "STAGE: analyze" in messages[0]["content"]:
            raise LLMError("HTTP 400: context length exceeded")
        return super().complete(messages, tools)


def test_failed_stage_degrades_to_partial_and_keeps_state(paths: Paths, limits: Limits) -> None:
    res = run(paths=paths, llm=FlakyAnalyze(), limits=limits, today=TODAY)
    assert res.status == "partial"
    statuses = {h["status"] for h in json.loads((paths.state / "hypotheses.json").read_text())}
    assert statuses == {"open"}  # untrusted run does not change the backlog


def test_budget_stops_the_run(paths: Paths) -> None:
    res = run(paths=paths, llm=OfflinePolicy(), limits=Limits(max_tool_calls=2), today=TODAY)
    assert res.status in {"partial", "failed"}
    assert any(g.name == "within_budget" and not g.passed for g in res.gates)
