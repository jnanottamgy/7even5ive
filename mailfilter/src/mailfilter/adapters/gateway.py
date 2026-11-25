"""The tool definition AgentCore Gateway needs for the mail filter's Lambda target.

The student is never an input: our interceptor adds `student_id` from the verified token.
"""

from __future__ import annotations

from typing import Any

from mailfilter.contract import KEPT_KINDS, TOOL_DESCRIPTION

TOOL = "get_opportunities"


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "name": TOOL,
            "description": TOOL_DESCRIPTION,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": list(KEPT_KINDS),
                        "description": "Only this kind of card",
                    },
                    "within_days": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 90,
                        "description": "Only cards whose next date is within this many days",
                    },
                    "include_past": {
                        "type": "boolean",
                        "description": "Also cards whose dates have passed",
                    },
                },
                "required": [],
            },
        }
    ]
