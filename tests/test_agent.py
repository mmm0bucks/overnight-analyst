from __future__ import annotations

from typing import Any

import pytest

from overnight.agent import StageFailed, run_stage
from overnight.budget import Budget, BudgetExceeded
from overnight.config import Limits
from overnight.llm import LLMResponse, ScriptedLLM, ToolCall
from overnight.schemas import CritiqueOut
from overnight.tools import SourceLog, Tool

ECHO = Tool("echo", "echo", {"type": "object", "properties": {}}, lambda: {"n": 7})


def _run(llm: ScriptedLLM, tools: list[Tool] | None = None,
         limits: Limits | None = None) -> tuple[CritiqueOut, SourceLog, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    src = SourceLog()
    out = run_stage(stage="t", llm=llm, system="s", user="u", tools=tools or [ECHO],
                    schema=CritiqueOut, budget=Budget(limits or Limits()), sources=src,
                    emit=events.append)
    return out, src, events


def test_tool_call_registers_source_and_returns_it_to_model() -> None:
    llm = ScriptedLLM([LLMResponse(tool_calls=[ToolCall("a", "echo", {})]),
                       LLMResponse(content='{"verdict": "accept"}')])
    out, src, _ = _run(llm)
    assert out.verdict == "accept"
    assert list(src.sources) == ["S1"]
    assert '"source": "S1"' in llm.seen[1][-1]["content"]


def test_unknown_tool_is_denied_not_executed() -> None:
    llm = ScriptedLLM([LLMResponse(tool_calls=[ToolCall("a", "rm_rf", {})]),
                       LLMResponse(content='{"verdict": "accept"}')])
    _, src, events = _run(llm)
    assert not src.sources
    assert any(e["event"] == "tool_denied" for e in events)


def test_tool_exception_goes_back_to_model() -> None:
    boom = Tool("boom", "", {"type": "object"}, lambda: 1 / 0)
    llm = ScriptedLLM([LLMResponse(tool_calls=[ToolCall("a", "boom", {})]),
                       LLMResponse(content='{"verdict": "revise"}')])
    out, _, _ = _run(llm, [boom])
    assert out.verdict == "revise"
    assert "ZeroDivisionError" in llm.seen[1][-1]["content"]


def test_invalid_output_gets_one_repair() -> None:
    llm = ScriptedLLM([LLMResponse(content='{"verdict": "maybe"}'),
                       LLMResponse(content='```json\n{"verdict": "accept"}\n```')])
    out, _, events = _run(llm)
    assert out.verdict == "accept"
    assert [e["event"] for e in events].count("repair") == 1


def test_second_invalid_output_fails_stage() -> None:
    llm = ScriptedLLM([LLMResponse(content="nope"), LLMResponse(content="still nope")])
    with pytest.raises(StageFailed):
        _run(llm)


def test_budget_is_checked_before_each_call() -> None:
    llm = ScriptedLLM([LLMResponse(tool_calls=[ToolCall("a", "echo", {})], tokens=500),
                       LLMResponse(content='{"verdict": "accept"}')])
    with pytest.raises(BudgetExceeded):
        _run(llm, limits=Limits(max_tokens=100))
