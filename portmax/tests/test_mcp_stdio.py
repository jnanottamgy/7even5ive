"""Claude Code's view of PortMax: the MCP server over stdio, as `.mcp.json` starts it."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from portmax.mock_portal.scripted import seed_demo


def test_claude_code_can_ask_for_dbms_attendance_and_what_it_means(tmp_path: Path) -> None:
    database = f"sqlite:///{tmp_path / 'demo.db'}"
    seed_demo(database, "demo")
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "portmax.cli", "mcp"],
        env={**os.environ, "PORTMAX_STUDENT_ID": "demo", "PORTMAX_DATABASE_URL": database},
    )

    async def ask() -> Any:
        async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} >= {"get_attendance", "get_attendance_plan"}
            attendance = await session.call_tool("get_attendance", {})
            return attendance, await session.call_tool("get_attendance_plan", {})

    def payload(result: Any) -> Any:
        found = result.structured_content or json.loads(result.content[0].text)
        return found.get("result", found)

    attendance, plan = asyncio.run(ask())
    dbms = next(row for row in payload(attendance)["data"] if row["subject_code"] == "CS52")
    assert (dbms["attended"], dbms["held"], dbms["percent"]) == (22, 30, 73.33)
    worst = payload(plan)["data"][0]
    assert worst["subject_code"] == "CS52" and worst["message"].startswith(
        "CS52 73.33%: attend the next 2 classes in a row"
    )
