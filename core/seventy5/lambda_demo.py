"""The demo as one AWS Lambda behind API Gateway: handler `seventy5.lambda_demo.handler`.

Why: the team's architecture is serverless. This runs the same self-contained demo as
`seventy5.cloud` (the morning's messages, the mock college portal, the recorded answers) on
Lambda, routed by path exactly as there: /api and /bot to the core, /v1 to PortMax, everything
else to the mock portal. deploy/aws/7even5ive-serverless.yaml wires it up.

Why /tmp: it is the only writable place on Lambda. The demo's SQLite files live there and are
reseeded with the demo morning on every cold start, so each start is a clean demo.
Why one instance: the mock portal keeps its login sessions in memory and the data lives in this
instance's /tmp, so the stack pins the function to one concurrent instance (see the template).
The production pipeline (several functions sharing Supabase) is core/template.yaml.
Why lazy: the app is built on the first request, not at import, so a slow cold start counts
against the request's timeout instead of Lambda's shorter init limit.
"""

from __future__ import annotations

import os
from typing import Any

if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    # Before anything reads seventy5.config: Lambda's code folder is read-only.
    os.environ.setdefault("DATABASE_URL", "/tmp/75.db")
    os.environ.setdefault("PORTMAX_DATABASE_URL", "sqlite:////tmp/portmax.db")

_handler: Any = None


def handler(event: dict[str, Any], context: Any) -> Any:
    global _handler
    if _handler is None:
        from mangum import Mangum

        from .cloud import build_router

        _handler = Mangum(build_router(), lifespan="off")
    return _handler(event, context)
