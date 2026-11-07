"""Two small MCP servers over the demo workspace that stand in for a tracker (like Jira) and
a wiki (like Confluence). The agent reaches them only through its MCP client
(mcp_sources.py), the same way it would reach the real ones:

    python -m overnight.mcp_demo tracker --workspace demo --today 2026-10-31
    python -m overnight.mcp_demo wiki --workspace demo
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from overnight.tools import SCHEMAS, Toolbox

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False)


def build(kind: str, workspace: Path, today: date) -> MCPServer:
    box = Toolbox(workspace, today)  # the same read functions the agent used directly
    app = MCPServer(f"overnight-demo-{kind}")

    def tool(fn: Any) -> Any:
        return app.tool(description=SCHEMAS[fn.__name__][0], annotations=READ_ONLY)(fn)

    if kind == "tracker":
        @tool
        def list_tasks() -> dict[str, Any]:
            return box.list_tasks()
    else:
        @tool
        def list_wiki_pages() -> list[str]:
            return box.list_wiki_pages()

        @tool
        def search_wiki(query: str) -> list[dict[str, str]]:
            return box.search_wiki(query)

        @tool
        def read_wiki(page: str) -> str:
            return box.read_wiki(page)
    return app


def main() -> None:
    p = argparse.ArgumentParser(prog="overnight.mcp_demo")
    p.add_argument("kind", choices=["tracker", "wiki"])
    p.add_argument("--workspace", type=Path, default=Path("demo"))
    p.add_argument("--today", type=date.fromisoformat, default=date.today())
    a = p.parse_args()
    build(a.kind, a.workspace, a.today).run("stdio")


if __name__ == "__main__":
    main()
