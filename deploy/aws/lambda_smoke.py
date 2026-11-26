"""Smoke test for the Lambda zip: runs its handler on API Gateway events, as Lambda would.

    cd core && python build_lambda_zip.py && cd ..
    python deploy/aws/lambda_smoke.py core/.build-lambda

Needs Python 3.12 on Linux x86_64, the platform of the zip's wheels (CI runs it there).
Checks health, the cards, the gateway's refusals, PortMax's runner and the mock portal's login
page, the account endpoints' limits on the demo account; exits non-zero on the first failure.
SMOKE_DATABASE_URL=postgresql://... runs it against Postgres (e.g. a local pooler), as on
Supabase; by default SQLite files in a temporary folder, as on Lambda without Supabase.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import Any

BUILD = sys.argv[1] if len(sys.argv) > 1 else "core/.build-lambda"
TMP = tempfile.mkdtemp()
os.environ.update(AWS_LAMBDA_FUNCTION_NAME="smoke", CACHE_DIR=f"{TMP}/cache")
if os.environ.get("SMOKE_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["SMOKE_DATABASE_URL"]  # all three share it
else:
    os.environ.update(DATABASE_URL=f"{TMP}/75.db", PORTMAX_DATABASE_URL=f"sqlite:///{TMP}/portmax.db",
                      MAILFILTER_DATABASE_URL=f"sqlite:///{TMP}/mailfilter.db")
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
check("cards with the demo morning",
      len([c for c in body.get("due_this_week", []) if c["route"] != "mail"]) == 4,
      cards["statusCode"])
check("attendance seeded", len(body.get("attendance", {}).get("subjects", [])) == 6)
check("no token is refused", call("/api/cards")["statusCode"] == 401)
refused = call("/api/tools/send_email", "POST", {**TOKEN, "content-type": "application/json"},
               json.dumps({"args": {"to": "x"}}))
check("send_email is refused", refused["statusCode"] == 403, refused)
check("PortMax runner served", call("/v1/runner.js")["statusCode"] == 200)
login = call("/index.php")
check("mock portal login page", login["statusCode"] == 200 and "pm-login" in login["body"], login["statusCode"])

# The app's demo tour: WhatsApp events through the real signed webhook, and the reset.
check("demo tour needs the student's token", call("/demo/forward/quiz", "POST")["statusCode"] == 401)
quiz = call("/demo/forward/quiz", "POST", TOKEN)
quiz_body = json.loads(quiz["body"]) if quiz["statusCode"] == 200 else {}
check("demo forward files a card via the bot",
      (quiz_body.get("filed") or {}).get("route") == "bot", quiz)
forged = json.loads(call("/demo/forward/forged", "POST", TOKEN)["body"])
check("a forged signature is refused", forged.get("webhook_status") == 401, forged)
reset = call("/demo/reset", "POST", TOKEN)
check("demo reset", reset["statusCode"] == 200, reset)
after = json.loads(call("/api/cards", headers=TOKEN)["body"])
morning = [c for c in after["due_this_week"] if c["route"] != "mail"]
check("reset restores the morning", len(morning) == 4, len(morning))

# College mail, the briefing, voice and MCP, all through the same function.
check("college mail cards in the Inbox",
      {c.get("category") for c in after["opportunities"]} >= {"placement", "internship"},
      after["opportunities"])
check("mail status on the cards", after["mail"]["mode"] == "demo", after.get("mail"))
JSON = {**TOKEN, "content-type": "application/json"}
mail_now = call("/api/mail/check", "POST", JSON, "{}")
check("check now finds the new mail", json.loads(mail_now["body"]).get("new") == 1, mail_now)
briefing = call("/api/briefing", headers=TOKEN)
check("briefing text", briefing["statusCode"] == 200 and
      json.loads(briefing["body"])["text"].startswith("Good "), briefing)
audio = call("/api/briefing/audio", headers=TOKEN)
check("no voice key: the phone reads it", audio["statusCode"] == 503, audio["statusCode"])
voice = json.loads(call("/api/voice/session", headers=TOKEN)["body"])
check("no voice key: the assistant says why", voice.get("available") is False, voice)
mcp = call("/mcp", "POST", {**JSON, "accept": "application/json, text/event-stream"},
           json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}))
tools = {t["name"] for t in json.loads(mcp["body"]).get("result", {}).get("tools", [])}
check("MCP over HTTP lists the tools", {"due_this_week", "briefing"} <= tools, mcp)
unsigned = call("/mcp", "POST", {"content-type": "application/json"}, "{}")
check("MCP needs the token", unsigned["statusCode"] == 401)

# The MCP connector (connector.py): an app is told where to sign in, registers, and is sent to
# the sign-in page (which, without Supabase, says accounts aren't set up).
www = {k.lower(): v for k, v in (unsigned.get("headers") or {}).items()}.get("www-authenticate", "")
check("MCP names where to sign in", 'resource_metadata="https://smoke.test/.well-known/'
      'oauth-protected-resource/mcp"' in www, www)
resource = json.loads(call("/.well-known/oauth-protected-resource/mcp")["body"])
check("sign-in metadata", resource.get("authorization_servers") == ["https://smoke.test"], resource)
meta = json.loads(call("/.well-known/oauth-authorization-server")["body"])
check("OAuth server metadata", meta.get("issuer") == "https://smoke.test" and
      meta.get("code_challenge_methods_supported") == ["S256"], meta)
registered = call("/oauth/register", "POST", JSON, json.dumps({
    "client_name": "smoke", "redirect_uris": ["http://127.0.0.1:9/cb"],
    "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"]}))
check("an MCP app can register", registered["statusCode"] == 201, registered)
client_id = json.loads(registered["body"])["client_id"]
started = call(f"/oauth/authorize?response_type=code&client_id={client_id}"
               "&redirect_uri=http%3A%2F%2F127.0.0.1%3A9%2Fcb&code_challenge="
               "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256&state=s")
location = {k.lower(): v for k, v in (started.get("headers") or {}).items()}.get("location", "")
check("authorize leads to the sign-in page", started["statusCode"] == 302 and
      location.startswith("https://smoke.test/oauth/login?request="), started)
page = call(location.removeprefix("https://smoke.test"))
check("without Supabase the sign-in page says so", page["statusCode"] == 503, page["statusCode"])

# Accounts: without Supabase only the demo; the demo account can't be changed or deleted.
auth_config = json.loads(call("/api/auth/config")["body"])
check("accounts off without Supabase", auth_config.get("enabled") is False and auth_config.get("demo"),
      auth_config)
me = json.loads(call("/api/me", headers=TOKEN)["body"])
check("the demo is the demo account", me.get("demo") is True and me.get("onboarded") is True, me)
for path in ("/api/me", "/api/me/token", "/api/me/delete", "/api/google/start"):
    refused = call(path, "POST", {**TOKEN, **JSON}, json.dumps({"confirm": "DELETE"}))
    check(f"demo account can't use {path}", refused["statusCode"] == 403 and
          json.loads(refused["body"]).get("code") == "demo_account", refused)
fake_session = "eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJ4In0.c2ln"
unset = call("/api/cards", headers={"authorization": f"Bearer {fake_session}"})
check("a session token without Supabase set up is a retry, not a sign-out", unset["statusCode"] == 503,
      unset)

# The once-a-minute tick that stands in for a server's background loop.
ticked = handler({"seventy5": "tick"}, None)
check("the tick runs the jobs", "reminders" in ticked.get("ran", []), ticked)
print("smoke test passed")
