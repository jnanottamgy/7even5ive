# Handoff for Kartik: PortMax and the 7even5ive prototype

> **Update, 27 Nov:** everything planned in section 5 is now built and wired into the app on the
> serverless demo (calls, briefing, voice assistant, college mail, Google, MCP over HTTP,
> notifications, the background keep-alive). What changed, the defaults chosen (P8–P18) and
> what is still yours to decide: `plan.md`. Keys to hand over: [`keys.md`](keys.md).

**As of 26 Nov 2026.** Code on branch `claude/busy-pasteur-lake3c`, commit `df21b28` (the
repository moved to `jnanottamgy/7even5ive`; the old address still redirects). Written by
Jnanottam's Claude sessions so you can pick up from here. Every number below was re-run today.

## In one minute

- **PortMax is built and tested** (100 tests): five read-only portal tools, bunk math, a mock
  college portal, the WebView runner, the phone API, an MCP server and the forge pipeline. The
  Android app logs in to the mock portal and shows attendance from it.
- **MSRIT is blocked for now.** On 25 Nov MSRIT refused an automated browser, but a login
  worked in Instagram's in-app browser. On 26 Nov the app's own Android WebView was refused:
  "This portal cannot be used from third-party apps. Please open it in Chrome or Safari." We do
  not disguise the app (decision 22). Choosing the MSRIT route is your call (section 3).
- **The college mail filter is built** (206 tests): Gmail read-only, checked twice a day,
  placements, internships and exam notices as cards. Push vs twice-daily is still your call.
- **Today the prototype server got a background loop**: reminders fire on their own, messages
  go to an outbox the phone pulls, Firebase can wake the phone, cards can be marked done, and
  the urgent-call groundwork is in. The full plan for finishing the prototype is `plan.md`.
- **The serverless demo (Lambda) has no background loop**, so reminders and calls do not fire
  there. It needs a once-a-minute schedule, or the demo runs on an always-on host (section 4).

## 1. PortMax: what it is

PortMax turns a college portal into five read-only tools with the same shape for every college
(`get_attendance`, `get_timetable`, `get_marks`, `get_results`, `get_profile`) plus a sixth,
`get_attendance_plan`, the bunk math: per subject, worst first, how many classes the student can
miss and stay at the college's minimum, or how many they must attend in a row to get back, in
exact fractions, with one sentence no model writes. The college's minimum lives in its manifest
(75 by default).

The student logs in **themselves** inside our app (the portal's own page in a WebView, CAPTCHA
and all). The app then runs the connector's fetch plan (GET requests only) from inside that
page with the student's own session, and uploads the pages. The server parses them, keeps only
the tools' fields and throws the pages away. The server never sees a password or a cookie.

A connector is data plus parsers: `manifest.yaml`, `fetch_plan.json` (the same file runs in the
WebView and on a server) and `parsers.py`, with fixtures and golden answers. The forge builds a
connector once per college from one recorded visit.

## 2. PortMax: what is built

| Part | Status | Where |
| --- | --- | --- |
| Contract: five tools, sanity rules, named errors (`SessionExpired`, `PortalChanged`, ...) | Built | `portmax/src/portmax/contract.py`, `errors.py` |
| Mock college portal: two-step login with CAPTCHA, one session per student, idle timeout | Built | `portmax/.../mock_portal/` |
| Fetch plan (GET-only data) and Python executor | Built | `plan.py`, `executor.py` |
| Mock college connector with fixtures and golden answers | Built, replays offline | `connectors/mockcollege/` |
| Store and ingest (pages parsed, then dropped), the five tools | Built | `store.py`, `ingest.py`, `tools.py` |
| Bunk math, `get_attendance_plan` | Built | `bunk.py`, `tools.py` |
| Phone API: `GET /v1/connectors/{college}`, `GET /v1/runner.js`, `POST /v1/pages` | Built (demo sign-in tokens) | `api.py` |
| JavaScript runner the WebView injects | Built, tested in real Chromium | `runner/portmax-runner.js` |
| MCP server (Claude Code asks "can I skip DBMS?" via `.mcp.json`) | Built | `adapters/mcp_server.py` |
| Lambda adapter and AgentCore Gateway tool schema | Built, not deployed | `adapters/lambda_handler.py`, `gateway.py` |
| Wake-ups for overdue keep-alive pings | Built with a logging stand-in | `wakeups.py` |
| Forge: capture, sanitise, fixtures, verify, accept, publish | Built, end to end on the mock | `forge/` |
| Forge: the engineer step (reverse-api-engineer with our prompt) | Wired; one live run with a model still to do | `forge/engineer.py` |
| **In the Android app:** WebView login, runner, upload, refresh on open and while open | Built (foreground only) | `android/.../portal/` |
| **In the Android app:** Settings → "Test a college portal" (a stock WebView, nothing injected) | Built 26 Nov | `PortalCheckScreen.kt` |
| End-to-end check of the app's own JavaScript against the real servers | Built | `android/e2e/portal-e2e.js` |
| MSRIT connector | Not built: blocked (section 3) | |
| Background keep-alive on Android (WorkManager + headless WebView) | Not built | |

Tests: PortMax 100 passing (`cd portmax && uv run pytest -q`). The online demo serves PortMax's
phone API at `/v1/*` and the mock portal at every other path of the same address
(`core/seventy5/cloud.py`; the same routing on Lambda in `lambda_demo.py`). Demo login: USN
`1MC24CS042`, date of birth 14-08-2005, CAPTCHA `PM42X`, then `2345`.

## 3. MSRIT: what we know, and the decision you need to make

| Date | Test | Result |
| --- | --- | --- |
| 25 Nov | Idle timeout (Zaid) | Session dies between 45 and 61 minutes idle, so the keep-alive pings every 30 minutes |
| 25 Nov | Automated browser (Playwright, the forge's capture) | Refused: "cannot be used from third-party apps" |
| 25 Nov | Instagram's in-app browser (Jnanottam) | **Login worked.** Whether this was on an iPhone or Android was never confirmed |
| 26 Nov | Our app's stock Android WebView | **Refused before the login form:** "Please open it in Chrome or Safari" |

The likely reading: MSRIT allows real Chrome and Safari only. An iPhone's in-app browser looks
much like Safari, while an Android WebView announces itself (`wv` in its User-Agent). If the
Instagram test was on an iPhone, both results agree. **Worth one 2-minute retest:** Instagram's
in-app browser on an Android phone.

What we will not do: disguise the WebView as Chrome. That is circumventing an access control the
owner set on purpose (decision 22, IT Act s.43), and MSRIT bans bot-like clients, so it could
also break mid-demo. Full write-up: `docs/portal-webview-test.md`.

Legitimate routes (the student uses real Chrome, which MSRIT allows):

1. **Share a screenshot or saved page** of the attendance screen to the app; it reads the
   numbers and PortMax's bunk math does the rest (about a day to build).
2. **Type it in**: attended and held per subject (2-3 hours).
3. **Official read-only feed**: ask MSRIT's CSE department or the portal vendor. The right
   long-term answer, and we need their written permission for real students anyway.
4. **Attendance mails**: if MSRIT emails shortage warnings, the mail filter can read them.

The demo keeps using the mock portal either way. **Your call:** which route for MSRIT, and who
asks MSRIT for permission or a feed.

## 4. Everything else built so far

**College mail filter** (`mailfilter/`, 206 tests, decisions 51-58). Reads Gmail read-only at
1 PM and 9 PM India time plus "check now"; Claude Haiku 5.5 on Bedrock (Mumbai) judges each
mail; code checks every quote, date and link Claude copies out; reminders and forwards merge
into one card. Open for you: keep the core's Gmail push path, or feed mail from this twice-daily
check (`plan.md` assumes the mail filter for the prototype, decision P2, until you say).

**The core prototype, today** (`core/`, 52 tests):

- A background loop inside the one web service: reminders every 30 seconds, daily jobs that
  remember their last run and catch up after a restart (`scheduler.py`).
- An outbox: every message for the student is a row the phone pulls
  (`GET /api/notifications`). Firebase only wakes the phone and carries no content (`fcm.py`).
- `mark_done` and `reopen` tools; reminders skip anything done, filtered or already past; a
  moved deadline moves its reminders.
- The urgent call (`calls.py`): consent, quiet hours, two a day, one per item, ElevenLabs
  caller with a stand-in, signed outcome webhook, missed call becomes one push. Written; its
  tests are next.
- A lock around the database (the loop and requests share one SQLite connection) and
  migrations for older database files.

**From the team's overnight sessions** (merged today): the serverless demo (one Lambda behind
API Gateway, `deploy/aws/7even5ive-serverless.yaml`; the app now points at it), an in-app demo
tour with a presenter script (`docs/demo-script.md`), the app's frosted-glass redesign, and the
WebView test above.

**One gap that matters for the demo:** Lambda has no always-on process, so the background loop
does not run on the serverless demo. Reminders and calls set there never fire. Fix: an
EventBridge rule every minute that runs the reminders job (the production template already has
`aws.notify_handler` for this), or run the demo on an always-on host (Render, EC2).

## 5. What is planned next (`plan.md`)

Phase 1 is done. Next, in order: the call's tests and agent setup, the morning briefing (text
plus ElevenLabs audio, in the app only), the mail filter wired into the core's cards, Google
sign-in on the server (Gmail, Calendar, Classroom), MCP on the online server, a "forward a
message" tester (SHELF stays untouched), and the Android side: notifications, call opt-in,
briefing, mark done, mail cards and the background keep-alive.

Defaults chosen on the team's behalf, all changeable (`plan.md`, P1-P7):

| # | Default |
| --- | --- |
| P1 | SHELF is not changed; 7even5ive gets a tester that sends the exact signed events in `docs/bot-events.md` |
| P2 | In the prototype, college mail comes from the mail filter; its cards become the core's cards |
| P3 | Notifications are an outbox the phone pulls (in the foreground, every 15 min, and at once when Firebase wakes it) |
| P4 | Urgent call: opt-in per item, 2 h before, quiet 22:00-08:00, max 2 a day, 90 s, no tools; Twilio for the demo, an Indian number (Exotel) for real students |
| P5 | The morning briefing lives in the app, never as a notification (decision 41) |
| P6 | One Google sign-in on the server for Gmail, Calendar and Classroom |
| P7 | Background portal keep-alive every 30 minutes, switchable |

## 6. Decisions waiting for you

1. The MSRIT route (section 3), and who asks MSRIT.
2. Mail: push or twice-daily (and whether the mail filter's checks fold into the cascade).
3. Demo hosting: serverless needs a once-a-minute schedule for reminders and calls; an
   always-on host needs nothing.
4. Wiring SHELF to send events to 7even5ive (`docs/bot-events.md` is the contract).
5. Any of P1-P7 above.

## 7. Keys and accounts the team will need (nothing is blocked on them yet)

Every service has a stand-in, so everything runs offline. For live runs: ElevenLabs (API key,
agent id, phone number id, webhook secret, voice id); a Twilio trial number with the demo phones
verified, later Exotel; a Google OAuth client of type "Web application"; a Firebase project
(app settings for Android, a service account for the server); Bedrock access to Claude Haiku 5.5
in Mumbai; a Jev key (OpenRouter); the secrets `BOT_WEBHOOK_SECRET`, `APPROVAL_SECRET`,
`TOKEN_ENCRYPTION_KEY`; and `DEMO_STUDENT_PHONE` for the live call.

## 8. How to pick up

```bash
git fetch origin claude/busy-pasteur-lake3c && git checkout claude/busy-pasteur-lake3c
cd core && uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m pytest -q             # core: 52
cd ../portmax && uv run pytest -q         # PortMax: 100
cd ../mailfilter && uv run pytest -q      # mail filter: 206
cd ../core && .venv/bin/python -m seventy5.cloud   # the whole demo on :8000
```

Read in this order: `plan.md` (the build plan and log), `docs/decisions.md`,
`docs/portmax.md`, `docs/portal-webview-test.md`, `docs/mailfilter.md`, `docs/online.md`.
