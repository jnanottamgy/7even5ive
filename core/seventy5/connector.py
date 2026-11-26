"""7even5ive as an MCP connector: a student connects Claude Code or Codex (or any MCP app that
signs in with OAuth, such as claude.ai's or ChatGPT's connectors) by signing in with their
7even5ive account in the browser. Nothing to copy from the phone.

    claude mcp add --transport http --scope user 7even5ive <server>/mcp   then /mcp, Authenticate
    codex mcp add 7even5ive --url <server>/mcp                            opens the browser itself

How it goes (MCP's authorization spec, OAuth 2.1):
1. /mcp without a token answers 401 and names its metadata (RFC 9728): who signs students in.
2. The app reads this server's OAuth metadata (RFC 8414) and registers itself (RFC 7591): a
   public client with no secret, redirecting to the student's own computer.
3. It opens /oauth/authorize in the browser with a PKCE challenge. The request is kept, and our
   sign-in page asks for the email or username and password, which Supabase checks.
4. A one-time code goes back to the app, which trades it (with the PKCE verifier) for an access
   token (an hour) and a refresh token (90 days); both are replaced at every refresh.
5. Every MCP request carries the access token. The gateway gives it what a personal token gets:
   the student's own tools, and add_to_calendar still waits for Approve on the phone.

Why the MCP SDK's handlers: the protocol's checks (client, redirect URI, PKCE, expiry, scope)
are theirs and tested; this file stores, looks up and draws the sign-in page.
Why our own sign-in page: Supabase has no hosted one. The password goes from here to Supabase,
as the app's username log-in does, and is never kept; neither is the session Supabase makes.
What is kept: the SHA-256 of every code and token. Tokens begin 75a_ (access) or 75r_
(refresh) and reach MCP only, never the app's API or the account. The app's Settings lists
each connected app and disconnects it; deleting the account removes them all.
Not: the demo account (it has no password; its public token still works as a header); a
redirect anywhere but https, this computer (localhost, 127.0.0.1, [::1]) or an app's own scheme.
"""

from __future__ import annotations

import html
import logging
import re
import secrets
import time
from contextvars import ContextVar
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

import anyio
from mcp.server.auth.handlers.authorize import AuthorizationHandler
from mcp.server.auth.handlers.register import RegistrationHandler
from mcp.server.auth.handlers.revoke import RevocationHandler
from mcp.server.auth.handlers.token import TokenHandler
from mcp.server.auth.middleware.client_auth import ClientAuthenticator
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.server.transport_security import DEFAULT_MAX_REQUEST_BODY_SIZE, RequestBodyLimitMiddleware
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthMetadata,
    OAuthToken,
    ProtectedResourceMetadata,
)
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route, request_response

from . import auth, clock
from .config import settings
from .db import ACCESS_PREFIX, REFRESH_PREFIX, BadInput, Database, token_hash

log = logging.getLogger(__name__)

SCOPE = "mcp"
ACCESS_SECONDS = 3600
REFRESH_SECONDS = 90 * 24 * 3600
CODE_SECONDS = 300
REQUEST_SECONDS = 600
UNUSED_CLIENT_SECONDS = 24 * 3600
NAME_MAX = 60  # how much of an app's own name the page and Settings show
PASSWORD_MAX = 1024

# Anyone may call these; each address gets this many an hour.
_registrations = auth.Limiter(20, 3600)
_authorizations = auth.Limiter(60, 3600)

# The address the app used for this request (scheme://host), set before any handler runs.
ORIGIN: ContextVar[str] = ContextVar("CONNECTOR_ORIGIN", default="")


def base_url(scope: dict[str, Any]) -> str:
    """This service's address as the caller sees it: PUBLIC_URL when the host gives one, else
    the address the request arrived at (API Gateway's own; it routes only its own host)."""
    from .cloud import origin_of

    return (settings.public_url or origin_of(scope) or "").rstrip("/")


def mcp_url(base: str) -> str:
    return f"{base}/mcp"


def resource_metadata_url(base: str) -> str:
    return f"{base}/.well-known/oauth-protected-resource/mcp"


# --- where an app may be sent back to ----------------------------------------------------------
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*$")
REFUSED_SCHEMES = {"http", "https", "javascript", "data", "file", "vbscript", "about", "blob",
                   "ftp", "ws", "wss", "mailto", "tel", "intent"}


def redirect_allowed(uri: str) -> bool:
    """https anywhere, http only to this computer, or an app's own scheme (RFC 8252). Never a
    fragment, never a scheme a browser would run or open as a page."""
    try:
        parsed = urlparse(uri)
        host = parsed.hostname or ""
    except ValueError:
        return False
    if parsed.fragment or not parsed.scheme:
        return False
    scheme = parsed.scheme.lower()
    if scheme == "https":
        return bool(host)
    if scheme == "http":
        return host in LOOPBACK
    return bool(_SCHEME.match(scheme)) and scheme not in REFUSED_SCHEMES


def redirect_label(uri: str) -> str:
    """Where the browser goes after Allow, as the sign-in page tells the student."""
    parsed = urlparse(uri)
    if parsed.scheme == "http" and (parsed.hostname or "") in LOOPBACK:
        return f"this computer ({parsed.netloc})"
    if parsed.scheme == "https":
        return parsed.netloc
    return f"the app that opened this page ({parsed.scheme}:)"


def app_name(client: OAuthClientInformationFull | None) -> str:
    """The name the app gave itself (it can say anything; the page says so)."""
    raw = (client.client_name if client is not None else None) or "An AI app"
    return " ".join(str(raw).split())[:NAME_MAX] or "An AI app"


def _now() -> int:
    return int(time.time())


async def _run(fn: Callable[..., Any], *args: Any) -> Any:
    return await anyio.to_thread.run_sync(lambda: fn(*args))


# --- OAuth, kept in this service's database ---------------------------------------------------
class Provider:
    """The MCP SDK's OAuthAuthorizationServerProvider over this service's database."""

    def __init__(self, db: Callable[[], Database]) -> None:
        self.db = db  # a function: a demo reset swaps the database object

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if not client_id or len(client_id) > 100:
            return None
        info = await _run(self.db().oauth_client, client_id)
        return OAuthClientInformationFull.model_validate_json(info) if info else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in client_info.redirect_uris or []]
        if not uris or len(uris) > 10 or not all(redirect_allowed(u) for u in uris):
            raise RegistrationError(
                "invalid_redirect_uri",
                "Redirect URIs must be https, this computer (http://localhost, 127.0.0.1 or "
                "[::1]), or an app's own scheme, with no #fragment.")
        now = _now()
        await _run(self.db().add_oauth_client, client_info.client_id,
                   client_info.model_dump_json(exclude_none=True), now,
                   now - UNUSED_CLIENT_SECONDS)
        log.info("mcp app registered", extra={"client": client_info.client_id})

    async def authorize(self, client: OAuthClientInformationFull,
                        params: AuthorizationParams) -> str:
        base = ORIGIN.get()
        if params.resource and params.resource.rstrip("/") not in (mcp_url(base), base):
            raise AuthorizeError("invalid_target", f"This server's MCP address is {mcp_url(base)}.")
        request_id = secrets.token_urlsafe(24)
        now = _now()
        await _run(self.db().add_oauth_request, request_id, client.client_id,
                   params.model_dump_json(), now + REQUEST_SECONDS, now)
        return f"{base}/oauth/login?{urlencode({'request': request_id})}"

    async def load_authorization_code(self, client: OAuthClientInformationFull,
                                      authorization_code: str) -> AuthorizationCode | None:
        row = await _run(self.db().oauth_code, token_hash(authorization_code))
        if row is None or row["client_id"] != client.client_id:
            return None
        params = AuthorizationParams.model_validate_json(row["params"])
        return AuthorizationCode(
            code=authorization_code, scopes=params.scopes or [SCOPE],
            expires_at=float(row["expires_at"]), client_id=client.client_id,
            code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource, subject=str(row["student_id"]))

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        access, refresh, tokens = _new_tokens()
        grant = tokens | {"client_name": app_name(client),
                          "scopes": " ".join(authorization_code.scopes),
                          "resource": authorization_code.resource,
                          "created_at": clock.iso(clock.now())}
        made = await _run(self.db().grant_from_code, token_hash(authorization_code.code),
                          client.client_id, grant)
        if made is None:
            raise TokenError("invalid_grant", "This sign-in code was already used. Sign in again.")
        log.info("mcp app connected", extra={"grant": made})
        return _answer(access, refresh, authorization_code.scopes)

    async def load_refresh_token(self, client: OAuthClientInformationFull,
                                 refresh_token: str) -> RefreshToken | None:
        if not refresh_token.startswith(REFRESH_PREFIX):
            return None
        row = await _run(self.db().oauth_grant, "refresh", token_hash(refresh_token), _now())
        if row is None or row["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, client_id=client.client_id,
                            scopes=str(row["scopes"]).split(),
                            expires_at=int(row["refresh_expires_at"]), resource=row["resource"],
                            subject=str(row["student_id"]))

    async def exchange_refresh_token(self, client: OAuthClientInformationFull,
                                     refresh_token: RefreshToken,
                                     scopes: list[str]) -> OAuthToken:
        used = token_hash(refresh_token.token)
        row = await _run(self.db().oauth_grant, "refresh", used, _now())
        access, refresh, tokens = _new_tokens()
        if row is None or not await _run(self.db().rotate_grant, int(row["id"]), used, tokens):
            raise TokenError("invalid_grant", "This refresh token was already used. Sign in again.")
        return _answer(access, refresh, scopes or refresh_token.scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        if not token.startswith(ACCESS_PREFIX):
            return None
        row = await _run(self.db().oauth_grant, "access", token_hash(token), _now())
        if row is None:
            return None
        return AccessToken(token=token, client_id=str(row["client_id"]),
                           scopes=str(row["scopes"]).split(),
                           expires_at=int(row["access_expires_at"]), resource=row["resource"],
                           subject=str(row["student_id"]))

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await _run(self.db().revoke_grant, token_hash(token.token))


def _new_tokens() -> tuple[str, str, dict[str, Any]]:
    access = ACCESS_PREFIX + secrets.token_urlsafe(32)
    refresh = REFRESH_PREFIX + secrets.token_urlsafe(32)
    now = _now()
    return access, refresh, {"access_hash": token_hash(access),
                             "access_expires_at": now + ACCESS_SECONDS,
                             "refresh_hash": token_hash(refresh),
                             "refresh_expires_at": now + REFRESH_SECONDS}


def _answer(access: str, refresh: str, scopes: list[str]) -> OAuthToken:
    return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_SECONDS,
                      refresh_token=refresh, scope=" ".join(scopes) or SCOPE)


# --- checking the student's password ---------------------------------------------------------
WRONG = "Wrong email, username or password."


def check_password(db: Database, login: str, password: str, ip: str) -> tuple[int | None, str]:
    """(student id, "") when Supabase accepts the password, else (None, what to tell them).
    Same answer for an unknown username and a wrong password. Counts against the same limits
    as the app's username log-in."""
    login = login.strip().lower().removeprefix("@")
    if not login or not password or len(login) > auth.LOGIN_MAX_CHARS or len(password) > PASSWORD_MAX:
        return None, WRONG
    if not auth.LOGIN_BY_IP.allow(ip) or not auth.LOGIN_BY_NAME.allow(login):
        return None, "Too many tries. Wait a few minutes and try again."
    if "@" in login:
        email = login
    else:
        row = db.student_by_username(login)
        email = str(row["email"]) if row is not None and row["email"] else ""
        if not email:
            return None, WRONG
    try:
        reply = auth.password_login(email, password, ip)
    except auth.AuthError:
        return None, "Couldn't reach the sign-in service. Try again."
    if reply.status_code != 200:
        try:
            code = str(reply.json().get("error_code") or "")
        except ValueError:
            code = ""
        if code == "email_not_confirmed":
            return None, "Confirm your email first: finish signing up in the 7even5ive app."
        if reply.status_code == 429:
            return None, "Too many sign-ins right now. Try again in a few minutes."
        if reply.status_code >= 500:
            return None, "The sign-in service isn't answering. Try again."
        return None, WRONG
    try:
        session = str(reply.json()["access_token"])
        identity = auth.verify(session)
    except (ValueError, KeyError, TypeError, auth.AuthError):
        return None, "Couldn't check your sign-in right now. Try again."
    auth.end_session(session)
    row = db.student_by_auth(identity.user_id)
    if row is None:
        return None, "Finish setting up your account in the 7even5ive app first, then try again."
    return int(row["id"]), ""


# --- the pages -------------------------------------------------------------------------------
PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Frame-Options": "DENY",
    # No scripts, no frames, no outside anything. (No form-action: the browser must follow our
    # redirect after Allow to the app on the student's computer.)
    "Content-Security-Policy": ("default-src 'none'; style-src 'unsafe-inline'; img-src 'none';"
                                " frame-ancestors 'none'; base-uri 'none'"),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}

STYLE = """
:root { color-scheme: light dark; --bg: #f6f5f2; --card: #ffffff; --ink: #1d1b18;
  --muted: #6b665f; --line: #e2ded7; --accent: #e8590c; --error: #b42318; }
@media (prefers-color-scheme: dark) { :root { --bg: #121110; --card: #1c1a18; --ink: #f2efe9;
  --muted: #a39d94; --line: #34302b; --accent: #ff7a2f; --error: #ff8a80; } }
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 440px; margin: 40px auto; padding: 28px 24px; background: var(--card);
  border: 1px solid var(--line); border-radius: 16px; }
@media (max-width: 480px) { main { margin: 0; border: 0; border-radius: 0; min-height: 100vh; } }
.brand { color: var(--accent); font-weight: 700; letter-spacing: .02em; margin: 0 0 12px; }
h1 { font-size: 22px; line-height: 1.3; margin: 0 0 12px; overflow-wrap: anywhere; }
ul { padding-left: 20px; margin: 8px 0 16px; } li { margin: 4px 0; }
.muted { color: var(--muted); font-size: 14px; }
.error { color: var(--error); font-weight: 600; }
label { display: block; font-size: 14px; font-weight: 600; margin: 14px 0 0; }
input { display: block; width: 100%; margin-top: 6px; padding: 11px 12px; font: inherit;
  color: var(--ink); background: var(--bg); border: 1px solid var(--line); border-radius: 10px; }
button { width: 100%; margin-top: 18px; padding: 12px; font: inherit; font-weight: 600;
  border-radius: 10px; border: 0; background: var(--accent); color: #fff; cursor: pointer; }
button.secondary { margin-top: 10px; background: transparent; color: var(--ink);
  border: 1px solid var(--line); }
"""


def page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
           "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
           f"<title>{html.escape(title)} · 7even5ive</title><style>{STYLE}</style></head>"
           f"<body><main><p class=\"brand\">7even5ive</p>{body}</main></body></html>")
    return HTMLResponse(doc, status_code=status, headers=PAGE_HEADERS)


def expired_page() -> HTMLResponse:
    return page("Sign-in expired", "<h1>This sign-in link has expired</h1><p>Start again from "
                "Claude Code or Codex (in Claude Code: /mcp, then Authenticate).</p>", 400)


def unavailable_page() -> HTMLResponse:
    return page("Not set up", "<h1>Accounts aren't set up on this server yet</h1><p>Try again "
                "once your team has finished setting up 7even5ive.</p>", 503)


def signin_page(request_id: str, client: OAuthClientInformationFull | None, redirect_uri: str,
                login: str = "", error: str = "", status: int = 200) -> HTMLResponse:
    problem = f'<p class="error" role="alert">{html.escape(error)}</p>' if error else ""
    body = f"""
<h1>Connect &ldquo;{html.escape(app_name(client))}&rdquo; to your 7even5ive</h1>
<p>An app calling itself that wants to use your account. It will be able to:</p>
<ul>
<li>read your deadlines, exams, timetable, attendance, study materials and college mail cards</li>
<li>set and cancel reminders, and mark things done</li>
<li>ask to add things to Google Calendar: each one waits for you to tap Approve on your phone</li>
</ul>
<p class="muted">After you allow it, your browser goes back to
{html.escape(redirect_label(redirect_uri))}. Allow only an app you started yourself, just now.</p>
{problem}
<form method="post" action="/oauth/login">
<input type="hidden" name="request" value="{html.escape(request_id)}">
<label>Email or username<input name="login" autocomplete="username" autocapitalize="none"
 spellcheck="false" maxlength="{auth.LOGIN_MAX_CHARS}" value="{html.escape(login)}" required
 autofocus></label>
<label>Password<input type="password" name="password" autocomplete="current-password"
 maxlength="{PASSWORD_MAX}" required></label>
<button type="submit" name="decision" value="allow">Sign in and allow</button>
<button type="submit" name="decision" value="cancel" formnovalidate class="secondary">Cancel</button>
</form>
<p class="muted">Forgot your password? Reset it in the 7even5ive app. You can disconnect this
app any time in the app's Settings.</p>"""
    return page("Connect an AI app", body, status)


# --- the ASGI app: metadata, OAuth endpoints, the sign-in page ---------------------------------
def oauth_app(app: Callable[[], Any]) -> Callable[..., Any]:
    """The connector's endpoints, routed here by cloud.Router: /.well-known/oauth-* and
    /oauth/*. `app()` is the current core App (a demo reset swaps it)."""
    provider = Provider(lambda: app().db)
    client_auth = ClientAuthenticator(provider)
    authorize = AuthorizationHandler(provider)
    token = TokenHandler(provider, client_auth)
    register = RegistrationHandler(provider, options=ClientRegistrationOptions(
        enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]))
    revoke = RevocationHandler(provider, client_auth)

    def caller(request: Request) -> str:
        return auth.client_ip(request.headers, request.client.host if request.client else None)

    def limited(handler: Callable[[Request], Any], limiter: auth.Limiter) -> Callable[..., Any]:
        async def endpoint(request: Request) -> Response:
            if not limiter.allow(caller(request)):
                return JSONResponse({"error": "temporarily_unavailable",
                                     "error_description": "Too many requests from this address."
                                                          " Try again later."}, status_code=429)
            return await handler(request)
        return endpoint

    def for_apps(endpoint: Callable[[Request], Any], methods: list[str]) -> Any:
        # Like the SDK's own routes: callable from a browser-based MCP app, body size capped.
        return CORSMiddleware(RequestBodyLimitMiddleware(request_response(endpoint),
                                                         DEFAULT_MAX_REQUEST_BODY_SIZE),
                              allow_origins=["*"], allow_methods=methods,
                              allow_headers=["authorization", "content-type",
                                             "mcp-protocol-version"])

    async def protected_resource(_: Request) -> Response:
        base = ORIGIN.get()
        meta = ProtectedResourceMetadata(resource=mcp_url(base), authorization_servers=[base],
                                         scopes_supported=[SCOPE], resource_name="7even5ive")
        return JSONResponse(meta.model_dump(mode="json", exclude_none=True))

    async def server_metadata(_: Request) -> Response:
        base = ORIGIN.get()
        methods = ["none", "client_secret_post", "client_secret_basic"]
        meta = OAuthMetadata(
            issuer=base, authorization_endpoint=f"{base}/oauth/authorize",
            token_endpoint=f"{base}/oauth/token", registration_endpoint=f"{base}/oauth/register",
            revocation_endpoint=f"{base}/oauth/revoke", scopes_supported=[SCOPE],
            response_types_supported=["code"],
            grant_types_supported=["authorization_code", "refresh_token"],
            token_endpoint_auth_methods_supported=methods,
            revocation_endpoint_auth_methods_supported=methods,
            code_challenge_methods_supported=["S256"])
        return JSONResponse(meta.model_dump(mode="json", exclude_none=True))

    async def login_page(request: Request) -> Response:
        request_id = request.query_params.get("request", "")[:64]
        found = await _run(provider.db().oauth_request, request_id, _now())
        if found is None:
            return expired_page()
        if not auth.configured():
            return unavailable_page()
        client = await provider.get_client(str(found["client_id"]))
        params = AuthorizationParams.model_validate_json(found["params"])
        return signin_page(request_id, client, str(params.redirect_uri))

    async def login_submit(request: Request) -> Response:
        form = await request.form()
        request_id = str(form.get("request") or "")[:64]
        login = str(form.get("login") or "")[:auth.LOGIN_MAX_CHARS + 1]
        password = str(form.get("password") or "")[:PASSWORD_MAX + 1]
        db = provider.db()
        now = _now()
        try:
            found = await _run(db.oauth_request, request_id, now)
        except BadInput:
            found = None
        if found is None:
            return expired_page()
        params = AuthorizationParams.model_validate_json(found["params"])
        redirect_uri = str(params.redirect_uri)
        if str(form.get("decision") or "") == "cancel":
            if await _run(db.end_oauth_request, request_id, now) is None:
                return expired_page()
            return RedirectResponse(construct_redirect_uri(
                redirect_uri, error="access_denied",
                error_description="The student cancelled.", state=params.state), status_code=302)
        if not auth.configured():
            return unavailable_page()
        client = await provider.get_client(str(found["client_id"]))
        try:
            sid, problem = await anyio.to_thread.run_sync(
                lambda: check_password(db, login, password, caller(request)))
        except BadInput:
            sid, problem = None, WRONG
        if sid is None:
            return signin_page(request_id, client, redirect_uri, login=login[:auth.LOGIN_MAX_CHARS],
                               error=problem, status=400)
        if await _run(db.end_oauth_request, request_id, now) is None:
            return expired_page()  # used a moment ago, in another tab
        code = secrets.token_urlsafe(32)
        await _run(db.add_oauth_code, token_hash(code), str(found["client_id"]), sid,
                   str(found["params"]), now + CODE_SECONDS, now)
        await _run(db.audit, sid, "mcp_connect", "allow", "signed in", clock.iso(clock.now()))
        return RedirectResponse(construct_redirect_uri(redirect_uri, code=code, state=params.state),
                                status_code=302)

    get = ["GET", "OPTIONS"]
    post = ["POST", "OPTIONS"]
    routes = [
        Route("/.well-known/oauth-protected-resource", for_apps(protected_resource, get),
              methods=get),
        Route("/.well-known/oauth-protected-resource/mcp", for_apps(protected_resource, get),
              methods=get),
        Route("/.well-known/oauth-authorization-server", for_apps(server_metadata, get),
              methods=get),
        Route("/oauth/authorize", limited(authorize.handle, _authorizations),
              methods=["GET", "POST"]),
        Route("/oauth/token", for_apps(token.handle, post), methods=post),
        Route("/oauth/register", for_apps(limited(register.handle, _registrations), post),
              methods=post),
        Route("/oauth/revoke", for_apps(revoke.handle, post), methods=post),
        Route("/oauth/login", login_page, methods=["GET"]),
        Route("/oauth/login", login_submit, methods=["POST"]),
    ]
    router = Starlette(routes=routes)

    async def asgi(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        ORIGIN.set(base_url(scope))
        await router(scope, receive, send)

    return asgi
