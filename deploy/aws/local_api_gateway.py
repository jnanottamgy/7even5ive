"""A local stand-in for API Gateway (HTTP API, payload 2.0) in front of a Lambda container.

Tests the serverless demo before deploying it: the same zip, in AWS's Lambda base image (which
includes the Lambda runtime emulator), reached the way the phone reaches API Gateway.

    cd core && python build_lambda_zip.py
    # an image FROM amazon/aws-lambda-python:3.12 with the zip's contents in /var/task,
    # CMD ["seventy5.lambda_demo.handler"], run with: -p 9001:8080 --read-only --tmpfs /tmp
    python deploy/aws/local_api_gateway.py 8095 http://127.0.0.1:9001
    BASE=http://<this machine's IP>:8095 node android/e2e/portal-e2e.js

Each HTTP request becomes the event API Gateway would send; the function is invoked once at a
time, as the stack's one pinned instance would be; its reply becomes the HTTP response,
cookies included. Standard library only.
"""

from __future__ import annotations

import base64
import json
import sys
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

LOCK = threading.Lock()
# Straight to the local container, whatever proxy the environment sets.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
FUNCTION = ""


class Gateway(BaseHTTPRequestHandler):
    def _handle(self) -> None:
        parts = urlsplit(self.path)
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else b""
        headers: dict[str, str] = {}
        cookies: list[str] = []
        for key, value in self.headers.items():
            key = key.lower()
            if key == "cookie":
                cookies += [c.strip() for c in value.split(";") if c.strip()]
            else:
                headers[key] = f"{headers[key]},{value}" if key in headers else value
        headers.setdefault("x-forwarded-proto", "http")
        now = time.time()
        event = {
            "version": "2.0",
            "routeKey": "$default",
            "rawPath": parts.path or "/",
            "rawQueryString": parts.query,
            "cookies": cookies,
            "headers": headers,
            "requestContext": {
                "accountId": "local",
                "apiId": "local",
                "domainName": headers.get("host", "localhost"),
                "domainPrefix": "local",
                "http": {
                    "method": self.command,
                    "path": parts.path or "/",
                    "protocol": "HTTP/1.1",
                    "sourceIp": self.client_address[0],
                    "userAgent": headers.get("user-agent", ""),
                },
                "requestId": str(uuid.uuid4()),
                "routeKey": "$default",
                "stage": "$default",
                "time": time.strftime("%d/%b/%Y:%H:%M:%S +0000", time.gmtime(now)),
                "timeEpoch": int(now * 1000),
            },
            "body": base64.b64encode(body).decode(),
            "isBase64Encoded": True,
        }
        call = urllib.request.Request(FUNCTION, data=json.dumps(event).encode(), method="POST")
        with LOCK, OPENER.open(call, timeout=90) as answer:
            reply = json.loads(answer.read())
        raw = reply.get("body") or ""
        data = base64.b64decode(raw) if reply.get("isBase64Encoded") else raw.encode()
        self.send_response(int(reply.get("statusCode", 200)))
        for key, value in (reply.get("headers") or {}).items():
            if key.lower() not in ("content-length", "transfer-encoding", "connection"):
                self.send_header(key, value)
        for cookie in reply.get("cookies") or []:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _handle

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    global FUNCTION
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8095
    base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:9001"
    FUNCTION = f"{base.rstrip('/')}/2015-03-31/functions/function/invocations"
    print(f"API Gateway stand-in on :{port} -> {FUNCTION}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Gateway).serve_forever()


if __name__ == "__main__":
    main()
