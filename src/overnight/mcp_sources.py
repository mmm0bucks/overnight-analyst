"""The agent as an MCP client: its tracker and wiki tools can come from MCP servers (the demo
ones, or real Jira/Confluence servers) instead of local files.

A JSON config says which servers to start and which of OUR tools each one provides:

    {"servers": {"wiki": {"command": "python", "args": ["-m", "overnight.mcp_demo", "wiki",
                                                        "--workspace", "{workspace}"]}},
     "tools": {"search_wiki": {"server": "wiki"},
               "read_wiki": {"server": "wiki", "tool": "confluence_get_page",
                             "rename": {"page": "page_id"}}}}

Only mapped tools are reachable, so whatever else a server offers (create an issue, post a
comment) is never shown to the model. A mapped tool that the server marks as writing, or whose
name says it writes, is refused at start. The model still sees our own tool schemas, and every
result still goes through the Toolbox: numbered as a source, spotlighted as untrusted data.
SQL never goes through MCP: it stays local, behind the SQL guard.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
import sys
import threading
from contextlib import AsyncExitStack
from datetime import date
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LOCAL_ONLY = {"run_sql"}  # the warehouse never leaves the SQL guard
WRITES = re.compile(r"create|update|delete|remove|add|edit|write|post|comment|transition|"
                    r"assign|move|upload|set", re.I)


class McpSources:
    def __init__(self, servers: dict[str, dict[str, Any]], tools: dict[str, dict[str, Any]],
                 timeout: float = 60) -> None:
        if LOCAL_ONLY & tools.keys():
            raise ValueError(f"{sorted(LOCAL_ONLY & tools.keys())} must stay local")
        self.tools, self.timeout = tools, timeout
        self.sessions: dict[str, ClientSession] = {}
        self.loop = asyncio.new_event_loop()  # MCP is async; the agent is not
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        ready: concurrent.futures.Future[None] = concurrent.futures.Future()
        self.main = asyncio.run_coroutine_threadsafe(self._serve(servers, ready), self.loop)
        try:
            ready.result(timeout)
        except BaseException:
            self.loop.call_soon_threadsafe(self.loop.stop)
            raise

    @classmethod
    def load(cls, config: Path, workspace: Path, today: date) -> McpSources:
        """Read a config; {workspace} and {today} in server args are filled in."""
        raw = json.loads(config.read_text(encoding="utf-8"))
        fill = {"{workspace}": str(workspace), "{today}": today.isoformat()}
        servers = {name: {**s, "args": [fill.get(a, a) for a in s.get("args", [])]}
                   for name, s in raw["servers"].items()}
        return cls(servers, raw["tools"])

    async def _serve(self, servers: dict[str, dict[str, Any]],
                     ready: concurrent.futures.Future[None]) -> None:
        # anyio needs the same task to open and close the sessions, so this one task owns
        # them for the whole night and only waits for close()
        self.stop = asyncio.Event()
        try:
            async with AsyncExitStack() as stack:
                for name in {t["server"] for t in self.tools.values()}:
                    s = servers[name]
                    command = sys.executable if s["command"] == "python" else s["command"]
                    params = StdioServerParameters(command=command, args=s.get("args", []),
                                                   env=s.get("env"))
                    read, write = await stack.enter_async_context(stdio_client(params))
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    self._check((await session.list_tools()).tools, name)
                    self.sessions[name] = session
                ready.set_result(None)
                await self.stop.wait()
        except BaseException as e:  # anyio wraps errors in groups: report the real one
            while isinstance(e, BaseExceptionGroup) and len(e.exceptions) == 1:
                e = e.exceptions[0]
            if not ready.done():
                ready.set_exception(e)
                return
            raise

    def _check(self, offered: list[Any], server: str) -> None:
        by_name = {t.name: t for t in offered}
        for ours, m in self.tools.items():
            if m["server"] != server:
                continue
            name = m.get("tool", ours)
            t = by_name.get(name)
            if t is None:
                raise ValueError(f"server {server!r} has no tool {name!r} (for {ours})")
            a = t.annotations
            if (a and (a.read_only_hint is False or a.destructive_hint)) or (
                    not (a and a.read_only_hint) and WRITES.search(name)):
                raise ValueError(f"{server}.{name} can write: refused for a read-only agent")

    def call(self, ours: str, args: dict[str, Any]) -> Any:
        """Call the remote tool behind one of our tool names and return plain JSON."""
        m = self.tools[ours]
        remote = {m.get("rename", {}).get(k, k): v for k, v in args.items()}
        coro = self.sessions[m["server"]].call_tool(m.get("tool", ours),
                                                    {**m.get("fixed", {}), **remote})
        res: Any = asyncio.run_coroutine_threadsafe(coro, self.loop).result(self.timeout)
        text = "".join(getattr(c, "text", "") for c in res.content)
        if res.is_error:
            raise RuntimeError(text or "remote tool failed")
        data = res.structured_content
        if isinstance(data, dict) and data.keys() == {"result"}:  # a non-dict return, wrapped
            return data["result"]
        if data is not None:
            return data
        try:
            return json.loads(text)
        except ValueError:
            return text

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.stop.set)
        try:
            self.main.result(self.timeout)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
