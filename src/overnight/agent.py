"""Budget and the bounded tool-calling loop that runs one stage."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from overnight.llm import LLM
from overnight.stages import Stage
from overnight.tools import Toolbox


@dataclass(frozen=True)
class Limits:
    max_tokens: int = 100_000  # per run
    max_tool_calls: int = 60
    max_seconds: float = 900
    max_sql_per_stage: int = 5
    max_sql_rows: int = 1000


class BudgetExceeded(RuntimeError):
    pass


class StageFailed(RuntimeError):
    pass


@dataclass
class Budget:
    limits: Limits
    tokens: int = 0
    tool_calls: int = 0
    started: float = field(default_factory=time.monotonic)

    def check(self) -> None:
        lim, secs = self.limits, time.monotonic() - self.started
        if self.tokens >= lim.max_tokens:
            raise BudgetExceeded(f"tokens {self.tokens}/{lim.max_tokens}")
        if self.tool_calls >= lim.max_tool_calls:
            raise BudgetExceeded(f"tool calls {self.tool_calls}/{lim.max_tool_calls}")
        if secs >= lim.max_seconds:
            raise BudgetExceeded(f"time {secs:.0f}s/{lim.max_seconds:.0f}s")

    def usage(self) -> dict[str, Any]:
        secs = round(time.monotonic() - self.started, 1)
        return {"tokens": self.tokens, "tool_calls": self.tool_calls, "seconds": secs}


def extract_json(text: str) -> Any:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])


def run_stage(stage: Stage, llm: LLM, user: str, box: Toolbox, budget: Budget,
              emit: Callable[[dict[str, Any]], None], max_turns: int = 12) -> BaseModel:
    messages: list[dict[str, Any]] = [{"role": "system", "content": stage.system()},
                                      {"role": "user", "content": user}]
    tools = box.schemas(stage.tools)
    repaired = False
    for _ in range(max_turns):
        budget.check()
        resp = llm.complete(messages, tools)
        budget.tokens += resp.tokens
        emit({"event": "llm", "stage": stage.name, "tokens": resp.tokens,
              "tools": [c.name for c in resp.tool_calls]})
        if resp.tool_calls:
            messages.append({"role": "assistant", "content": resp.content or None,
                             "tool_calls": [c.as_message() for c in resp.tool_calls]})
            for c in resp.tool_calls:
                budget.check()
                budget.tool_calls += 1
                result = box.call(stage.tools, c.name, c.arguments)
                emit({"event": "tool", "stage": stage.name, "tool": c.name,
                      "result": result[:200]})
                messages.append({"role": "tool", "tool_call_id": c.id, "content": result})
            continue
        try:
            return stage.schema.model_validate(extract_json(resp.content))
        except (ValueError, ValidationError) as e:
            if repaired:
                raise StageFailed(f"{stage.name}: invalid output after repair: {e}") from e
            repaired = True
            emit({"event": "repair", "stage": stage.name, "error": str(e)[:300]})
            messages += [{"role": "assistant", "content": resp.content},
                         {"role": "user", "content": f"Output broke the contract: {e}. "
                                                     "Reply with the corrected JSON only."}]
    raise StageFailed(f"{stage.name}: no final answer after {max_turns} turns")
