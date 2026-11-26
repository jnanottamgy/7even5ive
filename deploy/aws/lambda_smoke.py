"""Smoke test for the Lambda zip: runs its handler on API Gateway events, as Lambda would.

    cd core && python build_lambda_zip.py && cd ..
    python deploy/aws/lambda_smoke.py core/.build-lambda

Needs Python 3.12 on Linux x86_64, the platform of the zip's wheels (CI runs it there).
Checks health, the cards, the gateway's refusals, PortMax's runner and the mock portal's login
page; exits non-zero on the first failure.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import Any

BUILD = sys.argv[1] if len(sys.argv) > 1 else "core/.build-lambda"
TMP = tempfile.mkdtemp()
os.environ.update(
    AWS_LAMBDA_FUNCTION_NAME="smoke",
    DATABASE_URL=f"{TMP}/75.db",
    PORTMAX_DATABASE_URL=f"sqlite:///{TMP}/portmax.db",
    PORTMAX_DEV_TOKENS="demo-student-token:demo",
)
sys.path.insert(0, BUILD)

from seventy5.lambda_demo import handler

TOKEN = {"authorization": "Bearer demo-student-token"}


def call(path: str, method: str = "GET", headers: dict[str, str] | None = None,
         body: str = "") -> dict[str, Any]:
    raw_path, _, query = path.partition("?")
    head = {"host": "smoke.test", "x-forwarded-proto": "https", **(headers or {})}
    event = {
        "version": "2.0", "routeKey": "$default", "rawPath": raw_path, "rawQueryString": query,
        "headers": head, "body": body, "isBase64Encoded": False,
        "requestContext": {
            "accountId": "smoke", "apiId": "smoke", "domainName": "smoke.test",
            "domainPrefix": "smoke", "requestId": "smoke", "routeKey": "$default",
            "stage": "$default", "time": "26/Nov/2026:00:00:00 +0000", "timeEpoch": 0,
            "http": {"method": method, "path": raw_path, "protocol": "HTTP/1.1",
                     "sourceIp": "127.0.0.1", "userAgent": "smoke"},
        },
    }
    return handler(event, None)


def check(name: str, ok: bool, detail: object = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}", detail if not ok else "")
    if not ok:
        sys.exit(1)


health = call("/api/health")
check("health", health["statusCode"] == 200 and json.loads(health["body"])["service"] == "7even5ive", health)
cards = call("/api/cards", headers=TOKEN)
body = json.loads(cards["body"]) if cards["statusCode"] == 200 else {}
check("cards with the demo morning", len(body.get("due_this_week", [])) == 4, cards["statusCode"])
check("attendance seeded", len(body.get("attendance", {}).get("subjects", [])) == 6)
check("no token is refused", call("/api/cards")["statusCode"] == 401)
refused = call("/api/tools/send_email", "POST", {**TOKEN, "content-type": "application/json"},
               json.dumps({"args": {"to": "x"}}))
check("send_email is refused", refused["statusCode"] == 403, refused)
check("PortMax runner served", call("/v1/runner.js")["statusCode"] == 200)
login = call("/index.php")
check("mock portal login page", login["statusCode"] == 200 and "pm-login" in login["body"], login["statusCode"])
print("smoke test passed")
