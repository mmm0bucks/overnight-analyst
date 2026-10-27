"""LLM clients: OpenAI-compatible HTTP and a scripted one for tests."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

BACKOFF = (2.0, 4.0, 8.0)
RETRYABLE = {429, 500, 502, 503, 504}
MAX_OUTPUT = 2000  # output tokens per call: caps cost of a runaway answer


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def as_message(self) -> dict[str, Any]:
        return {"id": self.id, "type": "function",
                "function": {"name": self.name, "arguments": json.dumps(self.arguments)}}


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens: int = 0


class LLM(Protocol):
    def complete(self, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> LLMResponse: ...


class LLMError(RuntimeError):
    pass


class HttpLLM:
    def __init__(self, base_url: str, api_key: str, model: str,
                 transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.model, self.sleep = model, sleep
        self.http = httpx.Client(base_url=base_url, timeout=120, transport=transport,
                                 headers={"Authorization": f"Bearer {api_key}"})

    def ping(self) -> None:
        r = self.http.get("/models")
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code}")

    def complete(self, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> LLMResponse:
        body: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0,
                                "max_tokens": MAX_OUTPUT}
        if tools:
            body["tools"] = tools
        for wait in (*BACKOFF, None):
            try:
                r = self.http.post("/chat/completions", json=body)
            except httpx.TransportError as e:
                if wait is None:
                    raise LLMError(f"network: {e}") from e
                self.sleep(wait)
                continue
            if r.status_code in RETRYABLE and wait is not None:
                self.sleep(wait)
                continue
            if r.status_code >= 400:  # other 4xx (e.g. context overflow) are not retried
                raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            msg = data["choices"][0]["message"]
            calls = [ToolCall(c["id"], c["function"]["name"],
                              json.loads(c["function"].get("arguments") or "{}"))
                     for c in msg.get("tool_calls") or []]
            return LLMResponse(msg.get("content") or "", calls,
                               int((data.get("usage") or {}).get("total_tokens", 0)))
        raise AssertionError("unreachable")


class ScriptedLLM:
    """Replays canned responses and records the messages it was given."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses, self.seen = list(responses), list[list[dict[str, Any]]]()

    def complete(self, messages: list[dict[str, Any]],
                 tools: list[dict[str, Any]]) -> LLMResponse:
        self.seen.append(list(messages))
        return self.responses.pop(0)
