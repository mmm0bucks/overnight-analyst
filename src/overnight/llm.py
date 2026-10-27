"""LLM clients behind one small protocol.

* ``HttpLLM``   - any OpenAI-compatible /chat/completions endpoint with tool calling.
* ``ScriptedLLM`` - replays canned responses; used in tests.
The offline rule-based policy lives in ``offline.py``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from overnight.config import LLMSettings

Message = dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens: int = 0


class LLM(Protocol):
    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse: ...


class LLMError(RuntimeError):
    pass


RETRYABLE = {429, 500, 502, 503, 504}


class HttpLLM:
    def __init__(
        self,
        settings: LLMSettings,
        timeout: float = 120.0,
        backoff: tuple[float, ...] = (2.0, 4.0, 8.0),
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.s = settings
        self.backoff = backoff
        self.sleep = sleep
        self.client = httpx.Client(
            base_url=settings.base_url,
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def ping(self) -> None:
        """Preflight: cheap request that proves network + auth work."""
        r = self.client.get("/models")
        if r.status_code >= 400:
            raise LLMError(f"preflight failed: HTTP {r.status_code}")

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        payload: dict[str, Any] = {"model": self.s.model, "messages": messages, "temperature": 0}
        if tools:
            payload["tools"] = tools
        for attempt in range(len(self.backoff) + 1):
            try:
                r = self.client.post("/chat/completions", json=payload)
            except httpx.TransportError as e:
                if attempt == len(self.backoff):
                    raise LLMError(f"network error: {e}") from e
                self.sleep(self.backoff[attempt])
                continue
            if r.status_code in RETRYABLE and attempt < len(self.backoff):
                self.sleep(self.backoff[attempt])
                continue
            if r.status_code >= 400:  # other 4xx (incl. context overflow) are not retried
                raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
            return self._parse(r.json())
        raise LLMError("unreachable")  # pragma: no cover

    @staticmethod
    def _parse(data: dict[str, Any]) -> LLMResponse:
        msg = data["choices"][0]["message"]
        calls = [
            ToolCall(
                id=c["id"],
                name=c["function"]["name"],
                arguments=json.loads(c["function"].get("arguments") or "{}"),
            )
            for c in msg.get("tool_calls") or []
        ]
        tokens = int((data.get("usage") or {}).get("total_tokens", 0))
        return LLMResponse(content=msg.get("content") or "", tool_calls=calls, tokens=tokens)


class ScriptedLLM:
    """Returns pre-baked responses in order. Records what it was asked."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.seen: list[list[Message]] = []

    def complete(self, messages: list[Message], tools: list[dict[str, Any]]) -> LLMResponse:
        self.seen.append(list(messages))
        if not self.responses:
            raise LLMError("script exhausted")
        return self.responses.pop(0)
