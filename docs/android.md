# The Android app: everything needed to build it

This is the whole brief for building the 7even5ive Android app. It is the prototype's **only**
app. You should not need to read anything else, but the links say where each piece lives.

Contract changes (any field, endpoint or rule below) go through Kartik first, because the
backend, the MCP server and the WhatsApp bot all depend on the same contracts.

---

## 1. What 7even5ive is, in one paragraph

A student's semester is scattered across WhatsApp groups, college mail, Google Classroom and
the college portal. 7even5ive pulls all of it into one place: deadlines and exams ("due this
week"), study materials by subject, attendance with the exact number of classes to attend or
skip, and real opportunities from college mail with spam and fake "placement cell" mail
removed. The student's own AI (Claude Code, Codex) can ask about it over MCP. Every tool call,
from the AI or from this app, goes through one gateway with one set of rules.

## 2. What the app does

| Screen | Shows | Actions |
|---|---|---|
| **Due this week** (home) | Deadlines, exams and events due in the next 7 days, soonest first | "Remind me" on a card |
| **Attendance** | Per subject: percent, classes attended/held, and one sentence such as "attend the next 2 classes in a row, starting Thu 26 Nov, to get back to 75%". Worst subject first. | "Connect portal" / "Refresh" |
| **Materials** | Notes, slides, manuals, papers by subject | Filter by subject |
| **From your inbox** | Internships, events and notices from mail, most relevant first, plus "N spam or fake mails filtered out" | — |
| **Approvals** | Requests from the student's AI that write outside 7even5ive (today: add a deadline to Google Calendar) | **Approve** |
| **Reminders** | Pending reminders, soonest first | Cancel |
| **Portal login** | The college portal's own login page in a WebView | The student logs in themselves |

What the app does **not** do: plan study time, send mail, write to the portal, pay anything,
or notify about a deadline the student just forwarded. Notifications are only reminders the
student asked for.

## 3. Decisions that bind the app

| | |
|---|---|
| Platform | Android only. Recommended: **Kotlin + Jetpack Compose**, minSdk 26. The portal login (WebView) and the background refresh (WorkManager) are native Android features. |
| Sign-in | **None in the prototype.** One demo student; every request carries a fixed token (section 5). |
| Live updates | Poll `GET /api/cards` every 5–10 s while the app is in the foreground. No WebSocket. |
| Portal | The student logs in **inside the app** (the portal's own page in a WebView), CAPTCHA included. We never store the password, never automate the login and never solve CAPTCHAs. The app holds the session; the server never sees cookies. |
| Portal refresh | A full refresh every `refresh_minutes` (3 hours); one light keep-alive page every `keepalive_minutes`. |
| Privacy | Never log message text, mail text or the token. Demo data is invented. |

## 4. How the app sits in the system

```
Android app ──Bearer token──> 7even5ive core API   (cards, approve, tools)      port 8000
            ──Bearer token──> PortMax API          (portal settings, page upload) port 8002
            ──WebView───────> the college portal   (student logs in; mock: port 8765)
```

The app never calls Google, the WhatsApp bot, Jev or the LLM directly; the backend does.

## 5. Running the backend for the phone

**The easy way:** double-click `start-demo.bat` in the repository root (macOS/Linux:
`./start-demo.sh`). It sets up Python on the first run, finds the laptop's IP, starts all three
servers below in one window, sets `PORTMAX_PORTAL_ORIGINS` itself, and restarts PortMax when the
IP changes (a hotspot restart). The app finds the laptop on its Wi-Fi or hotspot by itself
(`GET /api/health` on the phone's /24), so nobody types an address. Settings → **Find the
laptop** searches on demand; typing an address still works as a fallback.

The three terminals below are what it runs, for when you need them separately.

Everything runs on a laptop; the phone must be on the **same Wi-Fi**. Use the laptop's LAN IP
(`ipconfig` → IPv4, e.g. `192.168.1.20`). On the Android emulator use `10.0.2.2` instead.

From the repository root, in PowerShell, three terminals:

```powershell
# 1. 7even5ive core: replays a morning's demo messages, then serves the API
cd core
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
$env:HOST="0.0.0.0"; $env:PORTMAX_DATABASE_URL="sqlite:///D:/Projects/7even5ive/core/data/portmax.db"
.venv\Scripts\python -m seventy5.demo
```

```powershell
# 2. PortMax API (portal settings + page upload), same token, same portal database.
#    PORTMAX_PORTAL_ORIGINS: where the phone reaches the mock portal (the laptop's LAN IP).
#    Uploads are refused unless every page came from that one address.
cd core
$env:PORTMAX_DEV_TOKENS="demo-student-token:demo"; $env:PORTMAX_DATABASE_URL="sqlite:///D:/Projects/7even5ive/core/data/portmax.db"
$env:PORTMAX_PORTAL_ORIGINS="mockcollege=http://192.168.1.20:8765"   # your laptop's IPv4
.venv\Scripts\portmax api --host 0.0.0.0 --port 8002
```

```powershell
# 3. The mock college portal the WebView logs in to
cd core
.venv\Scripts\portmax mock serve --host 0.0.0.0 --port 8765 --fixed-captcha
```

Both APIs share `PORTMAX_DATABASE_URL`, so attendance the phone uploads to PortMax shows up in
7even5ive's cards. Change the path to wherever the repository is; create `core\data` first.

`PORTMAX_PORTAL_ORIGINS` must be the address the phone opens the portal at: the laptop's LAN IP
on a phone, `http://10.0.2.2:8765` on the emulator. Without it PortMax expects
`http://127.0.0.1:8765` and refuses the upload with "dashboard: not from http://127.0.0.1:8765".

**Every request** to both APIs carries:

```
Authorization: Bearer demo-student-token
```

Local HTTP needs cleartext allowed for the laptop's IP in debug builds
(`res/xml/network_security_config.xml` with a `<domain-config cleartextTrafficPermitted="true">`).
Once the backend is on AWS, the core base URL becomes the deployed `ApiUrl` (HTTPS).

**Mock portal login** (invented student): USN `1MC24CS042`, date of birth 14-08-2005,
CAPTCHA `PM42X` (with `--fixed-captcha`), then parent's phone last digits `2345`.

## 6. Core API reference

Base: `http://<laptop-ip>:8000`. Errors: `401 {"detail": "unknown caller"}` for a missing or
wrong token; `403 {"detail": "..."}` for anything the gateway refuses.

### `GET /api/cards`

Everything the screens need, in one call. Real response from the demo (lists trimmed to one):

```json
{
  "student": { "id": 1, "name": "Demo Student", "branch": "CSE", "year": 3,
               "interests": "hackathons, backend, AI", "wa_phone": "919900000001",
               "portal_id": "demo", "mcp_token": null },
  "due_this_week": [
    { "id": 1, "kind": "deadline", "subject": "Database Management Systems",
      "title": "DBMS Assignment 3", "due_at": "2026-11-27T23:59+05:30",
      "status": "filed", "source": "whatsapp", "route": "bot" }
  ],
  "attendance": {
    "connected": true, "stale": false, "fetched_at": "2026-11-25T18:49:25.800171+00:00",
    "subjects": [
      { "subject_code": "CS52", "subject_name": "Database Management Systems",
        "attended": 22, "held": 30, "percent": 73.33, "minimum_percent": 75.0,
        "status": "short", "can_skip_now": 0, "must_attend": 2,
        "next_classes": ["2026-11-26", "2026-11-30"],
        "semester": { "planned": 52, "remaining": 22, "can_skip_rest_of_semester": 5,
                      "best_final_percent": 84.62 },
        "message": "CS52 73.33%: attend the next 2 classes in a row, starting Thu 26 Nov, to get back to 75%." }
    ]
  },
  "materials": [
    { "id": 2, "kind": "material", "subject": "Database Management Systems",
      "title": "DBMS_Unit3_notes.pdf", "due_at": null, "status": "filed",
      "source": "whatsapp", "route": "bot" }
  ],
  "opportunities": [
    { "id": 7, "kind": "event", "subject": "Miscellaneous", "title": "IISc open hackathon",
      "due_at": "2026-11-28T10:00+05:30", "status": "filed", "source": "gmail",
      "route": "jev+llm", "relevance": 0.88 }
  ],
  "filtered": 2,
  "needs_review": [],
  "approvals": [
    { "action": "add_to_calendar", "args": { "item_id": 1 }, "token": "eyJhIjoiYWRkX3RvX2NhbGVu..." }
  ],
  "calendar": [],
  "reminders": [
    { "reminder_id": 1, "fires_at": "2026-11-27T22:59+05:30", "title": "DBMS Assignment 3",
      "subject": "Database Management Systems", "due_at": "2026-11-27T23:59+05:30" }
  ],
  "audit": [
    { "id": 3, "student_id": 1, "tool": "set_reminder", "decision": "allow",
      "reason": "policy", "at": "2026-11-25T18:49+05:30" }
  ]
}
```

Field notes:
- Times are ISO 8601 in IST (`+05:30`), except `attendance.fetched_at` (UTC). Parse with
  `OffsetDateTime`.
- `kind`: `deadline | exam | material | event | notice`. `route` says what decided the card
  (`bot | classroom | jev | jev+llm | llm`); show it small, judges like seeing it.
- `attendance.connected = false` (and `subjects: []`) means the portal has never been
  refreshed: show "Connect your portal". `stale = true` means older than a day: show the age.
- `attendance.subjects[].status`: `safe | at_risk | short | unrecoverable`. Show `message`
  as it is; no model wrote it, and it is exact.
- `needs_review`: cards nobody could read; show them muted with the title.
- `materials` titles are file names. Opening a file is not built yet (the file stays with
  the WhatsApp bot and will be fetched by id).

### `POST /api/approve`

```json
{ "token": "<approvals[i].token, exactly as received>" }
```
→ `200 {"status": "ok", "result": {"calendar_event": "75…", "title": "...", "starts_at": "..."}}`

A token works **once**, for that one action and those exact arguments. `403` reasons you may
see: `approval already used`, `approval expired` (15 minutes), `malformed approval`.

### `POST /api/tools/{tool}`

The same gateway an MCP client uses; body `{"args": {...}}`.

| Tool | args | `result` |
|---|---|---|
| `set_reminder` | `item_id`, `before_minutes` (default 1440), `channel` (`push` or `call`) | `{"reminder_id", "fires_at", "title", "channel"}` |
| `list_reminders` | — | list like `cards.reminders` (with `item_id`, `channel`) |
| `cancel_reminder` | `reminder_id` | `{"cancelled": true}` |
| `mark_done` · `reopen` | `item_id` | `{"item_id", "status"}` (Done with Undo) |
| `briefing` · `timetable_today` · `check_mail_now` | — | as the endpoints below |
| `due_this_week` · `materials` (`subject` optional) · `attendance` · `opportunities` | | same shapes as in `/api/cards` |

Response: `{"status": "ok", "result": ...}`. A reminder can only be set on a filed, dated card
whose reminder time is still in the future; otherwise `403` with the reason.
`add_to_calendar` returns `{"status": "approval_needed"}` instead: the request then appears in
`approvals` for the student to tap. Once approved it also writes the student's real Google
Calendar when they connected Google (`result.google.ok`).

### Added for the integration (26–27 Nov)

`/api/cards` also carries `classes_today` (`[{start, end, subject_code, subject, room}]`, India
time) and `mail` (the mailbox: `mode` demo|gmail, `address`, `checked_at`, `next_check_at`,
`check_now_after` while cooling down, `left_out`). College-mail cards (`route: "mail"`) in
`opportunities` and `due_this_week` add `category` (placement | internship | exam_notice),
`organisation`, `role`, `link` (the form), `mail_link` (Gmail), `summary` and `event_at` (the
drive or exam itself when `due_at` is the deadline to register). Reminders add `item_id` and
`channel`.

| Endpoint | What |
|---|---|
| `GET /api/notifications?after=<id>` | The outbox: `{notifications: [{id, kind (reminder\|call), title, body, item_id, created_at}], latest_id}`. `after=-1` returns only `latest_id` (a first start). |
| `POST /api/devices` `{token, platform}` · `POST /api/devices/remove` `{token}` | Firebase wake-up tokens |
| `GET /api/settings` | `{calls: {enabled, consent_at, quiet_start, quiet_end, phone (masked), live, max_per_day, lead_minutes, max_seconds}, push: {wakeups}, google: {configured, connected, email, gmail, calendar, classroom}, voice: {assistant, briefing_audio}}` |
| `POST /api/settings/calls` `{enabled?, quiet_start?, quiet_end?}` | Consent on/off (off keeps call reminders as notifications) and quiet hours, `HH:MM` |
| `GET /api/calls` · `POST /api/calls/test` | Recent calls (ids and outcomes only) · ring now about the soonest item (`409` with the reason when calls are off or there is no number) |
| `GET /api/briefing` · `GET /api/briefing/audio` | Today: `{day, greeting, sections: [{key, title, lines}], classes, text, audio: {available}}` · ElevenLabs' mp3 (`503` with the reason when there is no voice: read `text` with TextToSpeech) |
| `GET /api/voice/session` | `{available, signed_url, dynamic_variables, tools, max_seconds}` or `{available: false, reason}` ([`voice.md`](voice.md)) |
| `POST /api/google/start` · `POST /api/google/finish` `{code, state}` · `POST /api/google/disconnect` | Google's consent page to open in the browser · the app finishes the sign-in when the browser hands back `sevenfive://google?code=…&state=…` (only the student who started it can) · revoke and forget |
| `GET /api/mail` · `POST /api/mail/check` | The mailbox status · Check now (`429` within 5 minutes of the last check) |
| `POST /mcp` | MCP over HTTP for Claude Code or Codex (`Authorization: Bearer <token>`; they sign in through `/oauth/*`, [`mcp.md`](mcp.md)) |

### Accounts (Supabase Auth, [`supabase.md`](supabase.md))

The app signs up, in and out with Supabase Auth itself (`data/Auth.kt`: `/auth/v1/signup`,
`/verify` with the emailed code, `/token` for password and refresh, `/recover`, `/user`,
`/logout`, all with the publishable key), and sends the session's access token as the Bearer
token everywhere here, PortMax and `/demo` included. The session is sealed by the Android
Keystore (`data/SessionStore.kt`) and refreshed a minute before it ends (`data/Accounts.kt`).
"Try the demo" uses the demo student's public token instead. `mail.mode` is also `none`: an
account that hasn't connected Google.

| Endpoint | What |
|---|---|
| `GET /api/auth/config` (no token) | `{enabled, supabase_url, publishable_key, username_login, delete_account, password_min_length, demo}` |
| `GET /api/auth/username?u=` (no token) | `{username, available, message}`: the rules, then whether it is taken |
| `POST /api/auth/login` `{login, password}` (no token) | A username sign-in: answers with Supabase's own session JSON. The same `400 invalid_credentials` for an unknown name and a wrong password |
| `GET /api/me` | `{onboarded, email, profile: {username, name, email, college, branch, year, interests, subjects, whatsapp (masked), personal_token: {exists, created_at}, demo}, demo}` |
| `POST /api/me` `{username?, name?, college?, branch?, year?, interests?, subjects?}` | Makes the profile (username and name required the first time), then changes it. `409 username_taken` |
| `POST /api/me/delete` `{confirm: "DELETE"}` | Every row, the mail read, portal answers, Google revoked, then the login. `503` (nothing deleted) without the secret key |
| `POST /api/me/token` · `POST /api/me/token/delete` | A personal MCP token, shown once (`{token, created_at, mcp_url}`) · revoke it |
| `POST /api/me/whatsapp` · `POST /api/me/whatsapp/delete` | `{code, expires_at, message ("LINK 75-…"), bot_number, link (wa.me)}` · unlink |

Refusals carry a `code` the app acts on: `401 session_expired` (refresh once, then log in again),
`403 profile_required` (profile setup), `403 demo_account`, `503 auth_unavailable` (try again;
never a sign-out).

## 7. Portal login and refresh (PortMax)

Base: `http://<laptop-ip>:8002`. The college for the demo is `mockcollege`.

1. `GET /v1/connectors/mockcollege` → settings for the phone:
   ```json
   { "college": "mockcollege", "name": "Mock College of Engineering",
     "connector_version": "1.0.0", "login_path": "/index.php",
     "markers": { "logged_in": "a#pm-logout", "login_page": "form#pm-login" },
     "keepalive_minutes": 16.0, "push_wakeup": false, "refresh_minutes": 180,
     "plan": { "steps": [...], "keepalive_step": "dashboard", "pace_ms": 400 } }
   ```
   Keep the whole object; pass it unchanged to the runner.
2. Open the portal in a WebView at `<portal origin><login_path>` (mock:
   `http://<laptop-ip>:8765/index.php`). JavaScript and cookies on
   (`CookieManager.setAcceptCookie(true)`). Do not change the WebView's User-Agent.
3. The student logs in. After each page load, inject the runner
   (`GET /v1/runner.js`, cache it) and check `PortMaxRunner.isLoggedIn(settings.markers)`.
4. Once logged in, run `await PortMaxRunner.run(settings)` in the page (via
   `evaluateJavascript`; it returns a Promise, so post the result back through a
   `@JavascriptInterface`). It returns a list of pages `{step, url, status, html, fetched_at}`.
   Every request is a GET from the portal's own page with the student's own session.
5. `POST /v1/pages` with `{"college": "mockcollege", "pages": [...]}` →
   `200 {"fetched_at", "saved", "failed"}`. The pages are parsed and dropped on the server;
   only the answers are kept. Then refresh `/api/cards`: attendance appears.
6. Errors: `409` `session_expired` → the login lapsed; show "Log in to your portal again"
   the next time the app opens (never a notification). `422` the portal changed; `400` unsafe
   plan or unsupported. Show the `detail`.
7. Keep-alive: every `keepalive_minutes`, `PortMaxRunner.keepAlive(settings)` (one page) and
   upload it the same way; every `refresh_minutes`, a full `run`. WorkManager's minimum
   periodic interval is 15 minutes. Running a WebView from a background worker is the hard
   part: for the prototype, refreshing on app open and while in the foreground is enough.

## 8. Reminders and notifications

- The student taps "Remind me" on a card → `set_reminder` (1 day, 3 hours, 1 hour), or
  "Call me 2 hours before" (`channel: "call"`, after the one-time consent; [`call.md`](call.md)).
- 7even5ive stores the reminder and fires it into the outbox; the app pulls the outbox every
  20 s on screen and every 15 minutes in the background (WorkManager), and at once when
  Firebase wakes it (`notify/`). The push carries no content. Android 13's permission is asked
  at the first reminder. Only reminders and a missed urgent call ever become notifications.

## 9. Approvals

When the student's AI asks to add a deadline to the calendar, the request shows up in
`approvals`. Show it at the top of the home screen: "Add to Google Calendar? *title*" with
**Approve**. Approve sends `POST /api/approve` with that token; on `200` remove it, on `403`
show the reason. Never approve automatically.

## 10. Done means

- [ ] Home shows "Due this week" from `/api/cards`, refreshed by polling.
- [ ] Attendance shows each subject's `message`, worst first; "Connect portal" when not connected.
- [ ] Portal login in the WebView against the mock portal, then `run` → `POST /v1/pages` →
      attendance appears.
- [ ] Approve works once; a second tap shows "approval already used".
- [ ] Set, list and cancel a reminder.
- [ ] Materials and inbox screens; "N spam or fake mails filtered out".
- [ ] Nothing logs message text, mail text or the token.

## Where things live

| | |
|---|---|
| Core API | `core/seventy5/api.py` |
| Gateway rules | `core/seventy5/gateway.py` |
| PortMax phone API and runner | `portmax/src/portmax/api.py`, `portmax/src/portmax/runner/portmax-runner.js` |
| Decisions | `docs/decisions.md` |
