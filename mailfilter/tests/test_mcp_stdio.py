"""Claude Code's view of the mail filter: the MCP server over stdio, as `.mcp.json` starts it."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mailfilter.cli import main


def test_claude_code_can_ask_for_placement_deadlines(tmp_path: Path, monkeypatch: Any) -> None:
    database = f"sqlite:///{tmp_path / 'demo.db'}"
    monkeypatch.setenv("MAILFILTER_DATABASE_URL", database)
    assert main(["demo", "--student", "demo"]) == 0
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mailfilter.cli", "mcp"],
        env={**os.environ, "MAILFILTER_STUDENT_ID": "demo", "MAILFILTER_DATABASE_URL": database},
    )

    async def ask() -> Any:
        async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert [tool.name for tool in tools.tools] == ["get_opportunities"]
            return await session.call_tool(
                "get_opportunities", {"kind": "placement", "include_past": True}
            )

    result = asyncio.run(ask())
    payload = result.structured_content or json.loads(result.content[0].text)
    payload = payload.get("result", payload)
    nimbus = next(c for c in payload["data"] if c["title"] == "Nimbus Systems Campus Drive")
    assert nimbus["deadline"] == "2026-12-05T23:59:00+05:30"
    assert nimbus["form_link"] == "https://forms.gle/NimbusDrive2027"
