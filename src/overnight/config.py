"""Runtime configuration, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Limits:
    max_tokens: int = 200_000
    max_tool_calls: int = 60
    max_seconds: float = 900.0
    max_sql_per_stage: int = 5
    max_sql_rows: int = 1000


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class Paths:
    """Where things live. The agent itself only ever writes inside ``runs``."""

    workspace: Path  # demo inputs: tasks.json, wiki/, warehouse.duckdb
    runs: Path  # one directory per run (artifacts, logs)
    state: Path  # memory between runs; written by the publisher only
    vault: Path  # Obsidian vault; written by the publisher only

    @classmethod
    def under(cls, root: Path, workspace: Path) -> Paths:
        return cls(
            workspace=workspace, runs=root / "runs", state=root / "state", vault=root / "vault"
        )


def limits_from_env() -> Limits:
    d = Limits()
    return Limits(
        max_tokens=int(os.getenv("OVERNIGHT_MAX_TOKENS", d.max_tokens)),
        max_tool_calls=int(os.getenv("OVERNIGHT_MAX_TOOL_CALLS", d.max_tool_calls)),
        max_seconds=float(os.getenv("OVERNIGHT_MAX_SECONDS", d.max_seconds)),
    )


def llm_from_env() -> LLMSettings:
    missing = [
        k
        for k in ("OVERNIGHT_LLM_BASE_URL", "OVERNIGHT_LLM_API_KEY", "OVERNIGHT_LLM_MODEL")
        if not os.getenv(k)
    ]
    if missing:
        raise RuntimeError(f"missing env vars: {', '.join(missing)} (or run with --llm offline)")
    return LLMSettings(
        base_url=os.environ["OVERNIGHT_LLM_BASE_URL"].rstrip("/"),
        api_key=os.environ["OVERNIGHT_LLM_API_KEY"],
        model=os.environ["OVERNIGHT_LLM_MODEL"],
    )
