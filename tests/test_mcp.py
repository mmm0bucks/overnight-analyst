"""Tracker and wiki over MCP: the same answers as local files, write tools refused, SQL local."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import TODAY

from overnight.agent import Limits
from overnight.mcp_sources import McpSources
from overnight.offline import OfflinePolicy
from overnight.orchestrator import run
from overnight.tools import Toolbox

FAKE_JIRA = '''
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

app = MCPServer("fake-jira")

@app.tool()
def create_issue(summary: str) -> str:
    return "created"

@app.tool(annotations=ToolAnnotations(read_only_hint=False))
def search_issues(jql: str) -> list[str]:
    return []

@app.tool(annotations=ToolAnnotations(read_only_hint=True))
def get_issue(key: str) -> dict:
    return {"key": key}

app.run("stdio")
'''


def test_demo_servers_answer_like_the_local_tools(ws: Path) -> None:
    local, remote = Toolbox(ws, TODAY), McpSources.load(ws / "mcp.json", ws, TODAY)
    try:
        for name, args in [("list_tasks", {}), ("list_wiki_pages", {}),
                           ("search_wiki", {"query": "duplicate responses"}),
                           ("read_wiki", {"page": "glossary"})]:
            assert remote.call(name, args) == getattr(local, name)(**args), name
    finally:
        remote.close()


def test_a_night_over_mcp_finds_the_same(ws: Path) -> None:
    def night(root: Path, **kw: Any) -> tuple[str, Any]:
        res = run(ws, root, root / "vault", OfflinePolicy(), Limits(), TODAY, **kw)
        return res.status, json.loads((res.run_dir / "analyze.json").read_text(encoding="utf-8"))

    assert night(ws.parent / "mcp", mcp=ws / "mcp.json") == night(ws.parent / "local")


def _jira(tmp_path: Path, tools: dict[str, Any]) -> McpSources:
    script = tmp_path / "fake_jira.py"
    script.write_text(FAKE_JIRA, encoding="utf-8")
    return McpSources({"jira": {"command": "python", "args": [str(script)]}}, tools)


@pytest.mark.parametrize("tool", ["create_issue", "search_issues"])
def test_a_tool_that_can_write_is_refused(tmp_path: Path, tool: str) -> None:
    # create_issue: no annotations, the name says it writes; search_issues: the server says so
    with pytest.raises(ValueError, match="can write"):
        _jira(tmp_path, {"list_tasks": {"server": "jira", "tool": tool}})


def test_only_mapped_read_tools_are_reachable(tmp_path: Path) -> None:
    src = _jira(tmp_path, {"read_wiki": {"server": "jira", "tool": "get_issue",
                                         "rename": {"page": "key"}}})
    try:
        assert src.call("read_wiki", {"page": "T-1"}) == {"key": "T-1"}
        assert list(src.tools) == ["read_wiki"]  # create_issue exists, but not for us
    finally:
        src.close()


def test_sql_never_goes_over_mcp() -> None:
    with pytest.raises(ValueError, match="must stay local"):
        McpSources({}, {"run_sql": {"server": "any"}})


def test_a_source_that_does_not_start_fails_the_preflight(ws: Path) -> None:
    bad = ws / "bad.json"
    bad.write_text(json.dumps({"servers": {"x": {"command": "no-such-command-xyz"}},
                               "tools": {"list_tasks": {"server": "x"}}}), encoding="utf-8")
    res = run(ws, ws.parent, ws.parent / "vault", OfflinePolicy(), Limits(), TODAY, mcp=bad)
    assert res.status == "failed" and "MCP sources" in res.gates[0].detail
