"""The production door: an AWS Lambda that AgentCore Gateway calls as a Lambda target.

Every tool call reaches this function only through the gateway, after its inbound auth, our
interceptor and the Cedar rules. The student is whoever the gateway authenticated: our REQUEST
interceptor writes `student_id` into the arguments from the verified token, overwriting anything
a model put there, so this function trusts that field and nothing else about identity.

The gateway names the tool in the Lambda context as `<target>___<tool>`. Check the event shape
against AWS's current Lambda-target documentation before the first deploy.
"""

from __future__ import annotations

import os
from functools import cache
from typing import Any

from portmax.contract import ALL_TOOLS, AnyToolName, utc_now
from portmax.errors import PortMaxError
from portmax.store import Store
from portmax.tools import answer, attendance_plan_answer

TOOL_NAME_KEY = "bedrockAgentCoreToolName"


@cache
def _store() -> Store:
    # Created once per warm Lambda; the schema is owned by migrations in production.
    return Store(os.environ["PORTMAX_DATABASE_URL"], create=False)


def tool_name(event: dict[str, Any], context: Any) -> AnyToolName | None:
    custom = getattr(getattr(context, "client_context", None), "custom", None) or {}
    raw = custom.get(TOOL_NAME_KEY) or event.get("tool") or ""
    name = str(raw).split("___")[-1]
    for tool in ALL_TOOLS:
        if tool == name:
            return tool
    return None


def handle(event: dict[str, Any], context: Any, store: Store) -> dict[str, Any]:
    tool = tool_name(event, context)
    if tool is None:
        return {"error": {"code": "unknown_tool", "detail": "not a PortMax tool"}}
    student_id = event.get("student_id")
    if not isinstance(student_id, str) or not student_id:
        return {"error": {"code": "unauthenticated", "detail": "no student on this call"}}
    try:
        if tool == "get_attendance_plan":
            return attendance_plan_answer(store, student_id, utc_now()).model_dump(mode="json")
        return answer(store, student_id, tool, utc_now()).model_dump(mode="json")
    except PortMaxError as error:
        return {"error": {"code": error.code, "detail": error.detail}}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return handle(event, context, _store())
