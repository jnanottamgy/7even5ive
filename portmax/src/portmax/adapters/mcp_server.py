"""The development door: the five tools as a local MCP server, for Claude Code and the demo.

One student per server, named by PORTMAX_STUDENT_ID, reading PORTMAX_DATABASE_URL. It has no
gateway and no login of its own, which is why it is for our laptops and the stage, not students.

    PORTMAX_STUDENT_ID=1MC24CS042 uv run portmax mcp
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from portmax.contract import TOOL_DESCRIPTIONS, ToolName, utc_now
from portmax.errors import PortMaxError
from portmax.store import Store
from portmax.tools import answer


def build_server(store: Store, student_id: str) -> MCPServer:
    server = MCPServer(
        name="portmax",
        instructions=(
            "Read-only tools over the student's college portal data: attendance, timetable, "
            "internal marks, results and profile. Each answer says when it was last refreshed."
        ),
    )

    def respond(tool: ToolName) -> dict[str, Any]:
        try:
            return answer(store, student_id, tool, utc_now()).model_dump(mode="json")
        except PortMaxError as error:
            raise ToolError(f"{error.code}: {error.detail}") from error

    @server.tool(description=TOOL_DESCRIPTIONS["get_attendance"])
    def get_attendance() -> dict[str, Any]:
        return respond("get_attendance")

    @server.tool(description=TOOL_DESCRIPTIONS["get_timetable"])
    def get_timetable() -> dict[str, Any]:
        return respond("get_timetable")

    @server.tool(description=TOOL_DESCRIPTIONS["get_marks"])
    def get_marks() -> dict[str, Any]:
        return respond("get_marks")

    @server.tool(description=TOOL_DESCRIPTIONS["get_results"])
    def get_results() -> dict[str, Any]:
        return respond("get_results")

    @server.tool(description=TOOL_DESCRIPTIONS["get_profile"])
    def get_profile() -> dict[str, Any]:
        return respond("get_profile")

    return server


def main() -> None:
    store = Store(os.environ.get("PORTMAX_DATABASE_URL", "sqlite:///portmax.db"))
    build_server(store, os.environ["PORTMAX_STUDENT_ID"]).run("stdio")
