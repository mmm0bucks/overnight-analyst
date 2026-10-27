from __future__ import annotations

import json

import httpx
import pytest

from overnight.config import LLMSettings
from overnight.llm import HttpLLM, LLMError

S = LLMSettings("https://llm.test/v1", "k", "m")
OK = {"choices": [{"message": {"content": None, "tool_calls": [
    {"id": "c1", "function": {"name": "list_tasks", "arguments": "{}"}}]}}],
      "usage": {"total_tokens": 42}}


def _llm(handler: object, sleeps: list[float]) -> HttpLLM:
    return HttpLLM(S, transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
                   sleep=sleeps.append)


def test_retries_429_then_parses_tool_calls() -> None:
    calls = iter([429, 503, 200])
    sleeps: list[float] = []

    def h(req: httpx.Request) -> httpx.Response:
        code = next(calls)
        return httpx.Response(code, json=OK if code == 200 else {})

    r = _llm(h, sleeps).complete([{"role": "user", "content": "hi"}], [])
    assert sleeps == [2.0, 4.0]
    assert r.tokens == 42 and r.tool_calls[0].name == "list_tasks"


def test_client_errors_are_not_retried() -> None:
    sleeps: list[float] = []
    with pytest.raises(LLMError, match="HTTP 400"):
        _llm(lambda req: httpx.Response(400, text="context length exceeded"),
             sleeps).complete([], [])
    assert sleeps == []


def test_gives_up_after_backoff() -> None:
    sleeps: list[float] = []
    with pytest.raises(LLMError, match="HTTP 500"):
        _llm(lambda req: httpx.Response(500), sleeps).complete([], [])
    assert sleeps == [2.0, 4.0, 8.0]


def test_sends_tools_and_auth() -> None:
    seen: dict[str, object] = {}

    def h(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=OK)

    _llm(h, []).complete([], [{"type": "function", "function": {"name": "x"}}])
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["tools"][0]["function"]["name"] == "x"  # type: ignore[index]
