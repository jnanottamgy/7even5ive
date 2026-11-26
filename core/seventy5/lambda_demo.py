"""The demo as one AWS Lambda behind API Gateway: handler `seventy5.lambda_demo.handler`.

Why: the team's architecture is serverless. This runs the same self-contained demo as
`seventy5.cloud` (the morning's messages, the mock college portal, the recorded answers) on
Lambda, routed by path exactly as there: /api and /bot to the core, /v1 to PortMax, /mcp to the
MCP server, everything else to the mock portal. deploy/aws/7even5ive-serverless.yaml wires it up.

Two kinds of invocation:
- API Gateway: an HTTP request, answered through Mangum.
- EventBridge, once a minute, with {"seventy5": "tick"}: the background jobs a long-running
  server would run in its loop -- due reminders and urgent calls, the 1 PM and 9 PM college mail
  check, Classroom. Lambda has no always-on process (handoff section 4), so the schedule is the
  loop. Each job is safe to run twice and is cut short in time (Lambda answers within 30 s).

Settings: every key lives in Parameter Store under SSM_PREFIX (/7even5ive-demo by default) as
SecureStrings, read once at a cold start, before anything reads seventy5.config. Nothing secret
is in the template, the code or the Lambda console; a missing key just leaves its stand-in.
Where the data lives: with DATABASE_URL in Parameter Store (Supabase Postgres, through its
pooler), everything persists there, accounts included, and the demo student is refreshed once a
day. Without it, SQLite files in /tmp (the only writable place on Lambda), reseeded with the demo
morning on every cold start.
Why one instance: the mock portal keeps its login sessions in memory (and, without Supabase, the
data lives in this instance's /tmp), so the stack pins the function to one concurrent instance.
Why lazy: the app is built on the first request, not at import, so a slow cold start counts
against the request's timeout instead of Lambda's shorter init limit.
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)

# One tick's jobs together must finish well inside Lambda's 29 s: they share this deadline, and
# each job only starts work it can finish before it (mail.MAIL_RESERVE, google.CLASSROOM_RESERVE).
TICK_BUDGET_SECONDS = 22.0


def load_settings(prefix: str | None, client: Any = None) -> list[str]:
    """Parameters under the prefix become environment variables (real ones win). Returns the
    names it set, never the values. A failure is logged and leaves the stand-ins."""
    if not prefix:
        return []
    try:
        if client is None:
            import boto3  # in the Lambda runtime

            client = boto3.client("ssm")
        names: list[str] = []
        token: str | None = None
        while True:
            page = client.get_parameters_by_path(
                Path=prefix, WithDecryption=True, Recursive=False,
                **({"NextToken": token} if token else {}))
            for param in page.get("Parameters", []):
                name = param["Name"].rsplit("/", 1)[-1]
                if name not in os.environ:
                    os.environ[name] = param["Value"]
                    names.append(name)
            token = page.get("NextToken")
            if not token:
                return names
    except Exception as err:  # noqa: BLE001 - a missing permission must not stop the demo
        log.warning("settings not loaded from Parameter Store", extra={"error": type(err).__name__})
        return []


def use_tmp_unless_supabase() -> None:
    """Without a Supabase DATABASE_URL, the three SQLite files live in /tmp (Lambda's code folder
    is read-only) and start over at each cold start. With one, all three share Supabase."""
    if not os.environ.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
        os.environ.setdefault("DATABASE_URL", "/tmp/75.db")
        os.environ.setdefault("PORTMAX_DATABASE_URL", "sqlite:////tmp/portmax.db")
        os.environ.setdefault("MAILFILTER_DATABASE_URL", "sqlite:////tmp/mailfilter.db")
    os.environ.setdefault("CACHE_DIR", "/tmp/cache")


if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    # Before anything reads seventy5.config. Parameter Store first: its DATABASE_URL (Supabase)
    # must not lose to the /tmp default.
    _loaded = load_settings(os.environ.get("SSM_PREFIX"))
    log.info("settings from Parameter Store", extra={"names": sorted(_loaded)})
    use_tmp_unless_supabase()

_handler: Any = None
_router: Any = None
_scheduler: Any = None


def _ensure() -> Any:
    global _handler, _router
    if _handler is None:
        from mangum import Mangum

        from .cloud import build_router

        _router = build_router()
        _handler = Mangum(_router, lifespan="off")
    return _handler


def tick() -> dict[str, Any]:
    """One turn of the background loop: every job that is due runs once, within the budget."""
    global _scheduler
    _ensure()
    from .cloud import current_jobs
    from .scheduler import Scheduler

    import time

    if _scheduler is None:
        # Built once per instance: interval jobs remember their last run in memory, daily jobs
        # in the database (a restart never runs the 1 PM check twice).
        _scheduler = Scheduler(lambda: _router.app.db, current_jobs(_router))
    app = _router.app  # a demo reset makes a new app: set its deadline each time
    app.deadline = time.monotonic() + TICK_BUDGET_SECONDS
    try:
        ran = [job.name for job in _scheduler.jobs if _scheduler.run_once(job)]
    finally:
        app.deadline = None
    return {"ran": ran}


def handler(event: dict[str, Any], context: Any) -> Any:
    if isinstance(event, dict) and event.get("seventy5") == "tick":
        return tick()
    return _ensure()(event, context)
