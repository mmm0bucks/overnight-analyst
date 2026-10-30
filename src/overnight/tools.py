"""Read-only tools. Every successful call is stored as a numbered source (S1, S2, ...)
so any claim in the report can be traced back to raw tool output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from overnight.sqlguard import validate

NO_ARGS: dict[str, Any] = {"type": "object", "properties": {}}
SCHEMAS: dict[str, tuple[str, dict[str, Any]]] = {
    "list_tasks": ("List tracker tasks with due dates and an 'overdue' flag.", NO_ARGS),
    "list_wiki_pages": ("List wiki page names.", NO_ARGS),
    "read_wiki": ("Read a wiki page.", {"type": "object", "required": ["page"],
                                        "properties": {"page": {"type": "string"}}}),
    "run_sql": ("Run ONE read-only DuckDB query (SELECT/WITH/SHOW/DESCRIBE/EXPLAIN). "
                "Tables: campaigns, contacts, responses. Max 1000 rows, 8 queries per stage.",
                {"type": "object", "required": ["query", "purpose"],
                 "properties": {"query": {"type": "string"}, "purpose": {"type": "string"}}}),
}


@dataclass
class Source:
    id: str
    tool: str
    args: dict[str, Any]
    result: Any


class Toolbox:
    def __init__(self, workspace: Path, today: date, sql_per_stage: int = 8,
                 max_rows: int = 1000) -> None:
        self.ws, self.today = workspace, today
        self.sql_per_stage, self.max_rows, self.sql_left = sql_per_stage, max_rows, sql_per_stage
        self.sources: dict[str, Source] = {}
        self.seen: dict[str, str] = {}  # call -> source id, within the current stage

    def new_stage(self) -> None:
        self.sql_left, self.seen = self.sql_per_stage, {}

    def schemas(self, names: list[str]) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {
            "name": n, "description": SCHEMAS[n][0], "parameters": SCHEMAS[n][1]}}
            for n in names]

    def available(self, names: list[str]) -> list[str]:
        return [n for n in names if n != "run_sql" or self.sql_left > 0]

    def call(self, allowed: list[str], name: str, args: dict[str, Any]) -> str:
        """Run a tool for the model. Errors go back to the model as text, never up."""
        if name not in allowed:
            return json.dumps({"error": f"tool '{name}' is not allowed here"})
        key = json.dumps([name, args], sort_keys=True)
        if key in self.seen:  # models re-read the same page in a loop instead of answering
            return json.dumps({"error": f"already returned above as {self.seen[key]}; "
                                        "use it instead of calling again"})
        try:
            result = getattr(self, name)(**args)
        except Exception as e:
            return json.dumps({"error": f"{type(e).__name__}: {e}"})
        sid = f"S{len(self.sources) + 1}"
        self.sources[sid] = Source(sid, name, args, result)
        self.seen[key] = sid
        return json.dumps({"source": sid, "result": result}, ensure_ascii=False, default=str)

    def list_tasks(self) -> list[dict[str, Any]]:
        tasks = json.loads((self.ws / "tasks.json").read_text(encoding="utf-8"))
        today = self.today.isoformat()
        return [{**t, "overdue": t["status"] != "done" and (t.get("due") or today) < today}
                for t in tasks]

    def list_wiki_pages(self) -> list[str]:
        return sorted(p.stem for p in (self.ws / "wiki").glob("*.md"))

    def read_wiki(self, page: str) -> str:
        if page not in self.list_wiki_pages():  # also blocks ../ traversal
            raise KeyError(f"unknown page: {page}")
        return (self.ws / "wiki" / f"{page}.md").read_text(encoding="utf-8")

    def run_sql(self, query: str, purpose: str = "") -> dict[str, Any]:
        if self.sql_left <= 0:
            raise RuntimeError(f"SQL quota of {self.sql_per_stage} per stage is used up")
        q = validate(query, self.max_rows)  # layer 1: lexical guard
        self.sql_left -= 1
        with duckdb.connect(str(self.ws / "warehouse.duckdb"), read_only=True) as con:  # layer 2
            cur = con.execute(q)
            cols = [d[0] for d in cur.description or []]
            rows = [[v if isinstance(v, (int, float, str)) or v is None else str(v)
                     for v in row] for row in cur.fetchall()]
        return {"query": q, "purpose": purpose, "columns": cols, "rows": rows}
