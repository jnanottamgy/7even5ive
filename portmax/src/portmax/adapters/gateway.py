"""The tool definitions AgentCore Gateway needs for our Lambda target.

The input schema is empty on purpose: the model never chooses the student. Our interceptor adds
`student_id` from the verified token after the model's call and before this Lambda runs.
"""

from __future__ import annotations

from typing import Any

from portmax.contract import TOOL_DESCRIPTIONS, TOOLS


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": tool,
            "description": TOOL_DESCRIPTIONS[tool],
            "inputSchema": {"type": "object", "properties": {}, "required": []},
        }
        for tool in TOOLS
    ]
