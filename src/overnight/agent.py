"""A bounded tool-calling loop for a single stage."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from overnight.budget import Budget
from overnight.llm import LLM, Message
from overnight.tools import SourceLog, Tool, render_result

T = TypeVar("T", bound=BaseModel)
EventSink = Callable[[dict[str, Any]], None]


class StageFailed(RuntimeError):
    pass


def extract_json(text: str) -> Any:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    if not raw:
        raise ValueError("no JSON object found in model output")
    return json.loads(raw)


def run_stage(
    *,
    stage: str,
    llm: LLM,
    system: str,
    user: str,
    tools: list[Tool],
    schema: type[T],
    budget: Budget,
    sources: SourceLog,
    emit: EventSink,
    max_turns: int = 12,
) -> T:
    by_name = {t.name: t for t in tools}
    messages: list[Message] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    repaired = False
    for turn in range(max_turns):
        budget.check()
        resp = llm.complete(messages, [t.schema() for t in tools])
        budget.add_llm(resp.tokens)
        emit({"event": "llm", "stage": stage, "turn": turn, "tokens": resp.tokens,
              "tool_calls": [c.name for c in resp.tool_calls]})
        if resp.tool_calls:
            messages.append({
                "role": "assistant", "content": resp.content or None,
                "tool_calls": [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                    for c in resp.tool_calls
                ],
            })
            for call in resp.tool_calls:
                budget.check()
                budget.add_tool_call()
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": _dispatch(stage, call.name, call.arguments,
                                                      by_name, sources, emit)})
            continue
        try:
            return schema.model_validate(extract_json(resp.content))
        except (ValueError, ValidationError) as e:
            if repaired:
                raise StageFailed(f"{stage}: invalid output after repair: {e}") from e
            repaired = True
            emit({"event": "repair", "stage": stage, "error": str(e)[:300]})
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content":
                             f"Your output did not match the contract: {e}. "
                             "Reply with the corrected JSON object only."})
    raise StageFailed(f"{stage}: no final answer after {max_turns} turns")


def _dispatch(stage: str, name: str, args: dict[str, Any], by_name: dict[str, Tool],
              sources: SourceLog, emit: EventSink) -> str:
    tool = by_name.get(name)
    if tool is None:
        emit({"event": "tool_denied", "stage": stage, "tool": name})
        return json.dumps({"error": f"tool '{name}' is not available in stage '{stage}'"})
    try:
        result = tool.fn(**args)
    except Exception as e:  # tool errors go back to the model, not up the stack
        emit({"event": "tool_error", "stage": stage, "tool": name, "error": str(e)[:300]})
        return json.dumps({"error": f"{type(e).__name__}: {e}"})
    src = sources.add(name, args, result, stage)
    emit({"event": "tool", "stage": stage, "tool": name, "source": src.id})
    return render_result(src)
