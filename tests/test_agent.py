from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import TODAY

from overnight.agent import Budget, BudgetExceeded, Limits, StageFailed, run_stage
from overnight.llm import LLMResponse, ScriptedLLM, ToolCall
from overnight.stages import CritiqueOut, Stage
from overnight.tools import Toolbox

STAGE = Stage("t", "role", ["list_wiki_pages", "run_sql"], CritiqueOut, [])
DEFAULT = Limits()
ACCEPT = LLMResponse(content='{"verdict": "accept"}')


def _run(ws: Path, *responses: LLMResponse, limits: Limits = DEFAULT) -> tuple[Any, ...]:
    llm, box, events = ScriptedLLM(list(responses)), Toolbox(ws, TODAY), list[dict[str, Any]]()
    out = run_stage(STAGE, llm, "u", box, Budget(limits), events.append)
    return out, llm, box, events


def _call(name: str, **args: Any) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall("x", name, args)])


def test_tool_result_is_a_numbered_source(ws: Path) -> None:
    out, llm, box, _ = _run(ws, _call("list_wiki_pages"), ACCEPT)
    assert out.verdict == "accept" and list(box.sources) == ["S1"]
    assert '"source": "S1"' in llm.seen[1][-1]["content"]


def test_tool_not_allowed_in_stage_is_refused(ws: Path) -> None:
    _, llm, box, _ = _run(ws, _call("list_tasks"), ACCEPT)
    assert not box.sources and "not allowed" in llm.seen[1][-1]["content"]


def test_rejected_sql_goes_back_to_model(ws: Path) -> None:
    _, llm, box, _ = _run(ws, _call("run_sql", query="DROP TABLE contacts"), ACCEPT)
    assert not box.sources and "SQLRejected" in llm.seen[1][-1]["content"]


def test_one_repair_for_bad_json(ws: Path) -> None:
    out, *_, events = _run(ws, LLMResponse(content='{"verdict": "maybe"}'),
                           LLMResponse(content='```json\n{"verdict": "accept"}\n```'))
    assert out.verdict == "accept" and [e["event"] for e in events].count("repair") == 1


def test_second_bad_json_fails_stage(ws: Path) -> None:
    with pytest.raises(StageFailed):
        _run(ws, LLMResponse(content="nope"), LLMResponse(content="still nope"))


def test_budget_checked_before_each_call(ws: Path) -> None:
    first = LLMResponse(tool_calls=[ToolCall("x", "list_wiki_pages", {})], tokens=500)
    with pytest.raises(BudgetExceeded):
        _run(ws, first, ACCEPT, limits=Limits(max_tokens=100))


class SQLAddict:
    """Mimics the first real run: keeps calling run_sql while it is offered."""

    def complete(self, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> LLMResponse:
        if any(t["function"]["name"] == "run_sql" for t in tools):
            q = {"query": f"SELECT {len(messages)}", "purpose": "p"}
            return LLMResponse(tool_calls=[ToolCall("x", "run_sql", q)])
        return ACCEPT


def test_stage_finishes_when_sql_quota_is_used_up(ws: Path) -> None:
    box, events = Toolbox(ws, TODAY, sql_per_stage=2), list[dict[str, Any]]()
    out = run_stage(STAGE, SQLAddict(), "u", box, Budget(DEFAULT), events.append)
    assert out.verdict == "accept"  # type: ignore[attr-defined]
    assert sum(e["event"] == "tool" for e in events) == 2


def test_repeated_call_is_not_run_again(ws: Path) -> None:
    _, llm, box, _ = _run(ws, _call("list_wiki_pages"), _call("list_wiki_pages"), ACCEPT)
    assert list(box.sources) == ["S1"] and "already returned above as S1" in \
        llm.seen[2][-1]["content"]
