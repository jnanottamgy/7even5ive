"""Lambda entry points. Each function is one small job; template.yaml wires them up.

    http_handler      API Gateway -> the FastAPI app (bot webhook, cards, approve)
    cascade_handler   SQS -> one event at a time through the cascade
    notify_handler    EventBridge, every minute -> fire due reminders

Why keys come from SSM at cold start: they never sit in the template, the code or the
Lambda console; the functions' role may read /7even5ive/* and nothing else.
Why ReportBatchItemFailures: one bad event in a batch is retried alone, not the batch.
Not yet: the MCP server on Lambda -- it runs locally over stdio until AgentCore fronts it.
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)
logging.getLogger().setLevel(logging.INFO)


KEYS = ("DATABASE_URL", "PORTMAX_DATABASE_URL", "JEV_API_KEY", "BEDROCK_MODEL_ID",
        "BOT_WEBHOOK_SECRET", "APPROVAL_SECRET")


def _load_ssm() -> None:
    prefix = os.environ.get("SSM_PREFIX")
    if not prefix:
        return
    import boto3

    # By name, not by path: the role's policy covers /7even5ive/* and nothing broader.
    names = [f"{prefix}/{key}" for key in KEYS]
    found = boto3.client("ssm").get_parameters(Names=names, WithDecryption=True)
    for param in found["Parameters"]:
        os.environ.setdefault(param["Name"].rsplit("/", 1)[-1], param["Value"])


_load_ssm()  # before anything reads seventy5.config

from .app import App, build  # noqa: E402

_app: App | None = None
_http: Any = None


def _state() -> App:
    global _app
    if _app is None:
        _app = build()  # one per warm container: one database connection, reused
    return _app


def http_handler(event: dict[str, Any], context: Any) -> Any:
    global _http
    if _http is None:
        from mangum import Mangum

        from .api import create

        _http = Mangum(create(_state()), lifespan="off")
    return _http(event, context)


def cascade_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    app = _state()
    failures = []
    for record in event.get("Records", []):
        try:
            app.process(int(record["body"]))
        except Exception:  # logged by id only; SQS retries it, then the DLQ keeps it
            log.exception("cascade failed", extra={"sqs_message": record.get("messageId")})
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}


def notify_handler(event: dict[str, Any], context: Any) -> dict[str, int]:
    from .notify import LogSender, fire_due

    return {"fired": fire_due(_state().db, LogSender())}
