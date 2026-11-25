"""The development door: the mail filter's tool as a local MCP server, for Claude Code and the
demo. One student per server (MAILFILTER_STUDENT_ID), reading MAILFILTER_DATABASE_URL. It has no
login of its own, which is why it is for our laptops and the stage, not students.

    MAILFILTER_STUDENT_ID=demo uv run mailfilter mcp
"""

from __future__ import annotations

import os
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mailfilter.config import Settings
from mailfilter.contract import TOOL_DESCRIPTION
from mailfilter.errors import MailFilterError
from mailfilter.store import Store
from mailfilter.timekit import utc_now
from mailfilter.tools import opportunities_answer


def build_server(store: Store, student_id: str, settings: Settings) -> MCPServer:
    server = MCPServer(
        name="mailfilter",
        instructions=(
            "Read-only tool over the student's college mail: placements, internships and "
            "exam-cell notices, with deadlines and form links copied from the mail and checked."
        ),
    )

    @server.tool(description=TOOL_DESCRIPTION)
    def get_opportunities(
        kind: Literal["placement", "internship", "exam_notice"] | None = None,
        within_days: int | None = None,
        include_past: bool = False,
    ) -> dict[str, Any]:
        if within_days is not None and not 1 <= within_days <= 90:
            raise ToolError("bad_arguments: within_days must be 1 to 90")
        try:
            answer = opportunities_answer(
                store, student_id, utc_now(), settings, kind=kind, within_days=within_days,
                include_past=include_past,
            )  # fmt: skip
        except MailFilterError as error:
            raise ToolError(f"{error.code}: {error.detail}") from error
        return answer.model_dump(mode="json")

    return server


def main() -> None:
    settings = Settings.from_env()
    store = Store(settings.database_url)
    build_server(store, os.environ["MAILFILTER_STUDENT_ID"], settings).run("stdio")
