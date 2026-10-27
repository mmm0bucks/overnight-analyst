"""Read-only tools the agent can call. Every call is registered as a numbered source
(S1, S2, ...) so that any claim in the report can be traced back to raw tool output."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from overnight import sqlguard
from overnight.sources.tracker import Tracker
from overnight.sources.wiki import Wiki

MAX_RESULT_CHARS = 6000


@dataclass
class Source:
    id: str
    tool: str
    args: dict[str, Any]
    result: Any
    stage: str


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., Any]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class SourceLog:
    sources: dict[str, Source] = field(default_factory=dict)

    def add(self, tool: str, args: dict[str, Any], result: Any, stage: str) -> Source:
        sid = f"S{len(self.sources) + 1}"
        src = Source(sid, tool, args, result, stage)
        self.sources[sid] = src
        return src

    def dump(self) -> list[dict[str, Any]]:
        return [s.__dict__ for s in self.sources.values()]


class SQLQuota(RuntimeError):
    pass


class Toolbox:
    def __init__(self, tracker: Tracker, wiki: Wiki, db_path: Path, today: date,
                 max_sql: int = 5, max_rows: int = 1000) -> None:
        self.tracker, self.wiki, self.db_path, self.today = tracker, wiki, db_path, today
        self.max_sql, self.max_rows = max_sql, max_rows
        self.sql_used = 0

    def reset_quota(self) -> None:
        self.sql_used = 0

    # -- tool implementations ------------------------------------------------
    def list_tasks(self) -> list[dict[str, Any]]:
        return [
            {"id": t.id, "title": t.title, "status": t.status,
             "due": t.due.isoformat() if t.due else None, "overdue": t.overdue(self.today)}
            for t in self.tracker.list_tasks()
        ]

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self.tracker.get_task(task_id).model_dump(mode="json")

    def list_wiki_pages(self) -> list[str]:
        return self.wiki.pages()

    def read_wiki(self, page: str) -> str:
        return self.wiki.read(page)

    def search_wiki(self, query: str) -> list[dict[str, str]]:
        return self.wiki.search(query)

    def run_sql(self, query: str, purpose: str = "") -> dict[str, Any]:
        if self.sql_used >= self.max_sql:
            raise SQLQuota(f"SQL quota for this stage is {self.max_sql} queries")
        q = sqlguard.validate(query, self.max_rows)
        self.sql_used += 1
        con = duckdb.connect(str(self.db_path), read_only=True)  # layer 2
        try:
            cur = con.execute(q)
            cols = [d[0] for d in cur.description or []]
            rows = [[_jsonable(v) for v in row] for row in cur.fetchall()]
        finally:
            con.close()
        return {"query": q, "purpose": purpose, "columns": cols, "rows": rows}

    def tools(self, names: list[str]) -> list[Tool]:
        s = {"type": "object", "properties": {}, "required": []}
        catalog = {
            "list_tasks": Tool("list_tasks", "List tasks in the tracker with due dates and "
                               "an 'overdue' flag.", s, self.list_tasks),
            "get_task": Tool("get_task", "Read one task in full.", {
                "type": "object", "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"]}, self.get_task),
            "list_wiki_pages": Tool("list_wiki_pages", "List wiki page names.", s,
                                    self.list_wiki_pages),
            "read_wiki": Tool("read_wiki", "Read a wiki page by name.", {
                "type": "object", "properties": {"page": {"type": "string"}},
                "required": ["page"]}, self.read_wiki),
            "search_wiki": Tool("search_wiki", "Full-text search over the wiki.", {
                "type": "object", "properties": {"query": {"type": "string"}},
                "required": ["query"]}, self.search_wiki),
            "run_sql": Tool("run_sql", "Run ONE read-only DuckDB query (SELECT/WITH/SHOW/"
                            "DESCRIBE/EXPLAIN). Tables: campaigns, contacts, responses. "
                            f"LIMIT is capped at {self.max_rows}; max {self.max_sql} "
                            "queries per stage.", {
                "type": "object",
                "properties": {"query": {"type": "string"},
                               "purpose": {"type": "string",
                                           "description": "what this query checks"}},
                "required": ["query", "purpose"]}, self.run_sql),
        }
        return [catalog[n] for n in names]


def _jsonable(v: Any) -> Any:
    if isinstance(v, (int, float, str)) or v is None:
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def render_result(source: Source) -> str:
    text = json.dumps({"source": source.id, "result": source.result}, ensure_ascii=False,
                      default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + '... [truncated]"}'
    return text
