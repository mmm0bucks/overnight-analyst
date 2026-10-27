"""Hard per-run budget. Checked before every LLM call and between stages."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from overnight.config import Limits


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    limits: Limits
    tokens: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    started: float = field(default_factory=time.monotonic)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def check(self) -> None:
        if self.tokens >= self.limits.max_tokens:
            raise BudgetExceeded(f"token budget spent: {self.tokens}/{self.limits.max_tokens}")
        if self.tool_calls >= self.limits.max_tool_calls:
            raise BudgetExceeded(
                f"tool-call budget spent: {self.tool_calls}/{self.limits.max_tool_calls}"
            )
        if self.elapsed >= self.limits.max_seconds:
            raise BudgetExceeded(f"time budget spent: {self.elapsed:.0f}s")

    def add_llm(self, tokens: int) -> None:
        self.llm_calls += 1
        self.tokens += tokens

    def add_tool_call(self) -> None:
        self.tool_calls += 1

    def snapshot(self) -> dict[str, float | int]:
        return {
            "tokens": self.tokens,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "seconds": round(self.elapsed, 2),
        }
