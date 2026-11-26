"""7even5ive as an MCP server: the student's own Claude or ChatGPT asks it what's due.

Every tool goes through the gateway, so an MCP client gets exactly the rights the phone
has: reads are allowed, add_to_calendar waits for the student's Approve, the rest is denied.
Run:  SEVENTY5_TOKEN=... python -m seventy5.mcp_server          (stdio)
      SEVENTY5_TOKEN=... python -m seventy5.mcp_server --http   (streamable HTTP)
Why the token comes from the environment: locally one process serves one student; deployed,
AgentCore Gateway's inbound auth names the student instead.
Why MCPServer (mcp 2.x): the same SDK PortMax uses, so both install into one environment.
Not: a second implementation of the tools -- this file only adapts tools.py to MCP.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .app import build
from .gateway import Denied

state = build()
server = MCPServer(
    name="7even5ive",
    instructions=(
        "One student's college deadlines, exams, study materials, attendance and filtered "
        "email opportunities. Use due_this_week for 'what's due'. add_to_calendar only asks; "
        "the student approves on their phone."
    ),
)


def _call(tool: str, **args: Any) -> Any:
    try:
        student = state.gateway.authenticate(os.environ.get("SEVENTY5_TOKEN", ""))
        return state.gateway.call(student, tool, {k: v for k, v in args.items() if v is not None})
    except Denied as err:
        raise ToolError(f"denied: {err}") from err


@server.tool(description="Deadlines, exams and events due in the next 7 days, soonest first.")
def due_this_week() -> Any:
    return _call("due_this_week")


@server.tool(description="Study materials (notes, slides, manuals, papers), optionally for one subject.")
def materials(subject: str | None = None) -> Any:
    return _call("materials", subject=subject)


@server.tool(description="Attendance per subject from the portal, worst first: classes to attend "
                         "or that can be missed at the college's minimum.")
def attendance() -> Any:
    return _call("attendance")


@server.tool(description="Internships, events and notices from college email, spam and fakes removed.")
def opportunities() -> Any:
    return _call("opportunities")


@server.tool(description="Remind the student before a filed deadline or exam (by its id). "
                         "before_minutes defaults to a day. The reminder arrives on their phone.")
def set_reminder(item_id: int, before_minutes: int = 1440) -> Any:
    return _call("set_reminder", item_id=item_id, before_minutes=before_minutes)


@server.tool(description="The student's pending reminders, soonest first.")
def list_reminders() -> Any:
    return _call("list_reminders")


@server.tool(description="Cancel one pending reminder by its reminder_id.")
def cancel_reminder(reminder_id: int) -> Any:
    return _call("cancel_reminder", reminder_id=reminder_id)


@server.tool(description="Ask to add a filed deadline or exam (by its id) to Google Calendar. "
                         "Needs the student's approval on their phone; returns approval_needed until then.")
def add_to_calendar(item_id: int) -> Any:
    return _call("add_to_calendar", item_id=item_id)


@server.tool(description="The student's file library (from their WhatsApp bot): subjects of this "
                         "term, each with shelves material, pyq and info and how many files each holds.")
def list_library() -> Any:
    return _call("list_library")


@server.tool(description="Files on one shelf of one subject (subject_id from list_library; shelf "
                         "material, pyq or info), newest first. unsorted=true: files still waiting "
                         "for a subject. Page with offset.")
def list_library_files(subject_id: int | None = None, shelf: str | None = None,
                       unsorted: bool = False, offset: int = 0) -> Any:
    return _call("list_library_files", subject_id=subject_id, shelf=shelf, unsorted=unsorted,
                 offset=offset)


@server.tool(description="Open one file from the library by its id: a link that works for a few "
                         "minutes (give it to the student), or a note's text.")
def open_file(file_id: int) -> Any:
    return _call("open_file", file_id=file_id)


if __name__ == "__main__":
    server.run("streamable-http" if "--http" in sys.argv else "stdio")
