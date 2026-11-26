# Connecting Claude Code or Codex (the MCP connector)

A student connects their own AI to 7even5ive with one command on their laptop, then signs in
with their 7even5ive account in the browser. Nothing is copied from the phone. The AI can then
answer "what's due this week?", read the timetable, attendance, materials and college mail cards,
set reminders and mark things done. Anything that writes outside 7even5ive (adding to Google
Calendar) still waits for the student's Approve on the phone.

`<McpUrl>` below is the stack's `McpUrl` output, `<AppUrl>/mcp`. The app shows it too:
**Settings** → **Connect Claude Code or Codex**, with Copy and Share buttons.

## Claude Code

```bash
claude mcp add --transport http --scope user 7even5ive <McpUrl>
```

Then, in Claude Code, type `/mcp`, choose **7even5ive** → **Authenticate** (or run
`claude mcp login 7even5ive` in a terminal). The browser opens 7even5ive's sign-in page: email or
username, and password → **Sign in and allow**. Back in Claude Code the tools are there; ask
"what's due this week?". `--scope user` makes it work in every project.

## Codex

```bash
codex mcp add 7even5ive --url <McpUrl>
```

Codex sees that 7even5ive signs in with OAuth and opens the browser by itself; sign in the same
way. `codex mcp list` then shows 7even5ive with OAuth. If the browser doesn't open, Codex prints
the address to open.

## Other MCP apps

- **claude.ai and ChatGPT connectors** (Settings → Connectors → add a custom connector with
  `<McpUrl>`) sign in the same way, where the plan allows custom connectors. Not tried here.
- **An app that can only send a fixed header**: in the app, **Settings** → **Connect Claude Code
  or Codex** → **Use a token instead** makes a personal token, shown once:
  `Authorization: Bearer <token>`. For example
  `claude mcp add --transport http 7even5ive <McpUrl> --header "Authorization: Bearer <token>"`.
- **The demo account** can't sign in (it has no password). For a presentation, its public token
  works as a header: `--header "Authorization: Bearer demo-student-token"`.

## Disconnecting

The app lists every connected app (**Settings** → **Connect Claude Code or Codex** → Connected
apps) with when it connected and was last used; **Disconnect** ends its access at once. Deleting
the account disconnects them all. On the laptop, `claude mcp logout 7even5ive` or
`codex mcp logout 7even5ive` forgets the sign-in there.

## How it works (core/seventy5/connector.py)

MCP's authorization spec, which is OAuth 2.1:

1. `/mcp` without a token answers `401` with
   `WWW-Authenticate: Bearer resource_metadata="<AppUrl>/.well-known/oauth-protected-resource/mcp"`.
2. The app reads that (RFC 9728), then `<AppUrl>/.well-known/oauth-authorization-server`
   (RFC 8414), and registers itself at `/oauth/register` (RFC 7591): a public client, no secret,
   redirecting to `http://localhost:<port>` or `127.0.0.1` on the student's own computer.
3. It opens `/oauth/authorize` in the browser with a PKCE challenge (S256 only). The request is
   kept for 10 minutes and the browser goes to `/oauth/login`, 7even5ive's sign-in page. The
   password goes from the server to Supabase (as the app's username log-in does), shares the
   same rate limits, and is never kept; neither is the Supabase session it makes.
4. A one-time code (5 minutes) goes back to the app, which trades it with its PKCE verifier at
   `/oauth/token` for an access token (an hour, `75a_…`) and a refresh token (90 days, `75r_…`).
   Every refresh replaces both.
5. Every MCP request carries the access token. The gateway treats it like a personal token: the
   student's own tools, MCP only. It is refused on the app's API, PortMax and the demo tour.

What is stored (all in the core's database, row level security on, like every table): the apps'
registrations, sign-in requests and codes (until used or expired), and one row per connected
app with the SHA-256 of its two tokens, never the tokens. The protocol's checks (client,
redirect URI, PKCE, expiry, scope) are the MCP Python SDK's handlers; connector.py stores, looks
up and draws the sign-in page.

Safety: only `https`, this computer's `http://localhost`, `127.0.0.1` or `[::1]`, or an app's own
scheme can be a redirect; the sign-in page names the app (as it named itself) and where the
browser goes back to, can't be framed, loads nothing from outside and isn't cached;
registrations are limited per address and dropped after a day if they never connected anyone.

## Tested

- `core/tests/test_connector.py`: metadata, registration, the sign-in page, codes used once and
  only with their verifier, refresh rotation, revocation, disconnecting in the app, deleting the
  account, tokens refused outside MCP, unsafe redirects refused, and the MCP SDK's own OAuth
  client signing in and listing the tools end to end. On SQLite, Postgres and PgBouncer.
- `deploy/aws/lambda_smoke.py`: discovery, registration and the sign-in page on the Lambda zip.
- By hand, with the real clients against a local server and a stand-in Supabase:
  `codex mcp add` detected OAuth, registered, and signed in ("Successfully logged in.");
  `claude mcp login` signed in ("Authenticated with 7even5ive") and `claude mcp get` showed
  "Connected". Not tried: claude.ai's and ChatGPT's connectors, and a real Supabase project.
