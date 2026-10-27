from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from overnight.llm import HttpLLM, LLMError

OK = {"choices": [{"message": {"content": None, "tool_calls": [
    {"id": "c1", "function": {"name": "list_tasks", "arguments": "{}"}}]}}],
      "usage": {"total_tokens": 42}}


def _llm(handler: Callable[[httpx.Request], httpx.Response], sleeps: list[float]) -> HttpLLM:
    return HttpLLM("https://llm.test/v1", "k", "m", httpx.MockTransport(handler), sleeps.append)


def test_retries_429_and_5xx_then_parses_tool_calls() -> None:
    codes, sleeps = iter([429, 503, 200]), list[float]()
    r = _llm(lambda req: httpx.Response(c := next(codes), json=OK if c == 200 else {}),
             sleeps).complete([], [])
    assert sleeps == [2.0, 4.0] and r.tokens == 42 and r.tool_calls[0].name == "list_tasks"


def test_other_4xx_not_retried() -> None:
    sleeps: list[float] = []
    with pytest.raises(LLMError, match="HTTP 400"):
        _llm(lambda req: httpx.Response(400, text="context length"), sleeps).complete([], [])
    assert sleeps == []


def test_gives_up_after_backoff() -> None:
    sleeps: list[float] = []
    with pytest.raises(LLMError, match="HTTP 500"):
        _llm(lambda req: httpx.Response(500), sleeps).complete([], [])
    assert sleeps == [2.0, 4.0, 8.0]


def test_sends_auth_and_tools() -> None:
    seen: list[httpx.Request] = []
    _llm(lambda req: seen.append(req) or httpx.Response(200, json=OK), []).complete(
        [], [{"type": "function", "function": {"name": "x"}}])
    assert seen[0].headers["authorization"] == "Bearer k"
    assert json.loads(seen[0].content)["tools"][0]["function"]["name"] == "x"
