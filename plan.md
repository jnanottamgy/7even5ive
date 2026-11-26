# 7even5ive prototype: the full build plan and running log

This file is the working memory for the "build everything" push that started on 26 Nov 2026.
Read it first after any context reset. Keep it current: tick items as they land, add to the
log at the bottom, and record every default chosen on the team's behalf under "Decisions taken".

## The brief (from Jnanottam, 26 Nov 2026)

- Build everything the prototype needs, in one go, on the **current prototype** (the one web
  service in `core/seventy5/cloud.py` plus the Android app), **not** the final architecture
  (no Lambda, SQS, Supabase or AgentCore work).
- Every outside account gets a stand-in, so everything runs offline; the team hands over keys
  at the end (list below). Never ask for keys mid-build.
- Cover all bases, no room for errors: tests for every rule, practical and precise.
- If a real doubt comes up, stop and ask. Undecided team questions take my recommendation and
  are written down below so Kartik can change them.
- The WhatsApp bot (Kartik's SHELF repo, `academic-assistant`) stays untouched: 7even5ive gets
  a "forward a message" tester that sends the exact signed events SHELF will send (answered
  26 Nov).

## Ground rules for this repository

- Branch `claude/busy-pasteur-lake3c` only; push there; no pull requests unless asked.
- Commit as `git -c user.name=jnanottamgy -c user.email=jnanottamgy@users.noreply.github.com`,
  message ending with the two attribution lines (Co-Authored-By Claude, Claude-Session).
  (From 27 Nov, Claude sessions in the cloud environment commit as `Claude
  <noreply@anthropic.com>` instead: its hook requires that so GitHub shows them Verified.)
- Never commit: `.env`, keys, tokens, `core/data/`, databases, raw HAR captures, the MP4s,
  `android/local.properties`.
- Never automate a real portal login, solve CAPTCHAs, spoof the WebView or rotate IPs; never
  probe MSRIT's portal (decision 22).
- Logs carry ids and counts only, never message, mail or note text, phone numbers or tokens.
- Notifications are only the student's opt-in reminders and the opt-in urgent call
  (decision 41). The briefing and attendance warnings live in the app, never in a notification.

## How to run and test

| What | Command |
| --- | --- |
| Core tests | `cd core && .venv/bin/python -m pytest -q` (create the venv once: `uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements.txt`) |
| Mail filter tests | `cd mailfilter && uv run pytest -q` |
| PortMax tests | `cd portmax && uv run pytest -q` |
| Online server locally | `cd core && .venv/bin/python -m seventy5.cloud` (port 8000) |
| Android APK | `cd android && ./gradlew assembleDebug` (SDK at `/opt/android-sdk`, installed by the environment's setup script) |
| Android unit tests | `cd android && ./gradlew testDebugUnitTest` |

## What the prototype is (one service, one app)

```
Android app ──Bearer token──> one web service (cloud.py), routed by path:
                                /api/*, /bot/*  core: cards, tools, approvals, notifications,
                                                calls, briefing, Google connect, dev tester
                                /v1/*           PortMax phone API (portal settings, pages)
                                /mcp            MCP over HTTP for Claude / ChatGPT / Claude Code
                                /dev            development page (+ "forward a message")
                                everything else the mock college portal (WebView login)
            background loop inside the service: reminders + calls every 30 s, mail at
            1 PM and 9 PM, Classroom with each mail check
```

State is SQLite. On Render's free plan the disk is wiped on every restart and the demo morning
is reseeded, so a connected Google account has to be connected again after a restart.

## Build plan

Status: `[ ]` to do, `[~]` in progress, `[x]` done and tested, `[-]` decided not to build.

### Phase 1: foundation in the core
- [x] 1.1 Database: one lock around every statement and transaction (the background loop and
      request threads share one SQLite connection); `_ensure_columns` migrations for new
      columns on old databases.
- [x] 1.2 Background loop (`scheduler.py`) started by `cloud.py` and `demo.py`: every job
      guarded, ids-only logs, stops cleanly.
- [x] 1.3 Notification outbox: `notifications` table, `OutboxSender`, `GET /api/notifications`,
      device registration `POST /api/devices` for FCM tokens; reminders fire through it.
- [x] 1.4 `mark_done` / `reopen` tools (For you, undo); reminders and calls skip done items.
- [x] 1.5 A moved due date moves its pending reminders by the same amount.

- [x] 1.6 The serverless demo (Lambda) has no lifespan, so no background loop: add a
      once-a-minute EventBridge schedule that runs the reminders job there (found 26 Nov).

### Phase 2: the urgent call (ElevenLabs)
- [x] 2.1 `calls.py`: Caller protocol; ElevenLabs + Twilio caller; ElevenLabs + SIP/Exotel
      caller; `LogCaller` stand-in. Script template filled by code, titles cleaned.
- [x] 2.2 Rules: opt-in with recorded consent; reminders get `channel` push|call; quiet hours
      (22:00-08:00 default, per student); at most 2 calls a day, 1 per item; item still open and
      not past due; anything refused becomes one push.
- [x] 2.3 `POST /api/calls/webhook`: ElevenLabs signature check, outcome recorded; missed,
      voicemail or failed -> one push, never a second call.
- [x] 2.4 Agent as code: prompt, first message, 90 s cap, voicemail detection, pushed by
      `python -m seventy5.calls setup-agent`; test call endpoint.
- [x] 2.5 Tests: quiet hours, caps, done item, missed -> push, overlapping runs, bad signature,
      nasty title.

### Phase 3: the morning briefing
- [x] 3.1 `briefing.py`: template from today's data (due today and tomorrow, today's classes,
      attendance at risk, new mail cards, reminders today); no model writes it.
- [x] 3.2 ElevenLabs TTS, generated on first tap and cached per student and day; stand-in: none
      (the app reads the text with Android's own text-to-speech).
- [x] 3.3 `GET /api/briefing`, `GET /api/briefing/audio`; MCP tool `briefing`.

### Phase 4: college mail in the prototype (the mail filter)
- [x] 4.1 Core installs `../mailfilter`; Dockerfile too.
- [x] 4.2 `mail.py` bridge: offline demo mailbox (dates relative to today, scripted judge) or
      real Gmail with the student's Google token + Claude on Bedrock.
- [x] 4.3 Cards copied into core items (`ext_key`, link, organisation, role, category,
      mail link); updated in place; reminders follow a moved deadline.
- [x] 4.4 Checks at 1 PM and 9 PM India time + "check now" (5-minute cooldown).
- [x] 4.5 `/api/cards` opportunities carry the new fields; "N mails left out".

### Phase 5: Google account (one server-side sign-in)
- [x] 5.1 `google.py`: web-server OAuth with PKCE and a one-time connect code (no student token
      in any URL); scopes Gmail read-only, Calendar events, Classroom read; refresh token
      encrypted at rest; disconnect revokes and deletes.
- [x] 5.2 Calendar: real event insert with the fixed per-item id when connected (409 -> update);
      stand-in table otherwise.
- [x] 5.3 Classroom: courses + coursework with a future due date -> events into the cascade;
      a changed due date updates the card in place.

### Phase 6: MCP for the student's own AI, on the online server
- [x] 6.1 `/mcp` mounted in `cloud.py`, Bearer token per request, every call through the gateway.
- [x] 6.2 Tools added: `briefing`, `mark_done`, `reopen`, `timetable_today`, `check_mail_now`.

### Phase 7: the WhatsApp tester
- [-] 7.1 `POST /api/dev/forward`: builds and signs exactly the event SHELF will send and runs
      it through `/bot/webhook`'s own code path; `/dev` page gets a form. Covered by the demo
      tour's `/demo/forward/{quiz,notes,stranger,forged}` (cloud.py), which signs exactly the
      bot's events through the real webhook; no second tester was built.

### Phase 8: the Android app
- [x] 8.1 Notifications: channels, Android 13 permission, foreground pull, WorkManager pull
      every 15 min, optional FCM wake-up (initialised from build settings only when present).
- [x] 8.2 Reminders: "Call me" options with a one-time consent screen; channel shown.
- [x] 8.3 Settings: Google account, calls (consent, quiet hours, test call), notifications,
      background portal keep-alive, demo tester.
- [x] 8.4 Home: briefing card (server audio or on-device speech), today's classes, mark done
      with undo.
- [x] 8.5 Inbox: mail cards (category, organisation, role, dates, Open form, Open in Gmail),
      Check now, "N left out".
- [x] 8.6 Background portal keep-alive every 30 minutes (measured idle timeout 45-61 min),
      WebView in a worker, toggle, no notification on lapse.
- [x] 8.7 Unit tests for the new parsing; APK builds.

### Phase 9: configuration and docs
- [x] 9.1 `.env.example` with every key; startup prints which parts are live and which are
      stand-ins.
- [x] 9.2 `render.yaml` env vars (secrets `sync: false`).
- [x] 9.3 Docs: README, architecture (prototype), decisions (new entries), `docs/call.md`,
      `docs/android.md` API reference, `docs/online.md`, `docs/keys.md`.

### Phase 10: end-to-end checks
- [x] 10.1 Every test suite green; ruff/mypy where the package uses them.
- [x] 10.2 Smoke run of the online server: reminder fires -> outbox -> call stand-in ->
      webhook -> missed push; mail check; briefing; MCP call; forward tester.
- [x] 10.3 APK built from the final code.

## Decisions taken on the team's behalf (Kartik can change any)

| # | Decision | Why |
| --- | --- | --- |
| P1 | WhatsApp: tester inside 7even5ive; SHELF untouched (asked, 26 Nov). | SHELF is Kartik's production code. |
| P2 | College mail in the prototype = the mail filter (twice daily + check now); its cards become core items. The core's Gmail-push cascade code stays, unfed. | One table drives due list, reminders, calls, calendar and briefing. Push vs twice-daily is still Kartik's call. |
| P3 | Notifications = a server outbox the app pulls: in the foreground, every 15 min in the background, and at once when FCM is configured (the push carries no content). | Works with no Firebase account; nothing personal travels in a push. |
| P4 | Urgent call defaults: opt-in per item, 2 h before, quiet hours 22:00-08:00, max 2 a day and 1 per item, 90 s, no tools, missed -> one push. Twilio for the demo, Exotel for real students. | The approved call plan. |
| P5 | Briefing is in the app only, never a notification. | Decision 41. |
| P6 | One Google sign-in on the server (web client): Gmail read-only, Calendar events, Classroom read. | One consent; the phone never holds Google tokens. |
| P7 | Background portal keep-alive every 30 min in the app, on by default, switchable. | Measured idle timeout 45-61 min. |

| P8 | The serverless demo runs the background loop as an EventBridge tick once a minute; each tick's jobs share a 20 s budget. Keys come from Parameter Store `/7even5ive-demo/*` at every cold start. | Lambda has no always-on process; the tick also keeps the one instance warm. |
| P9 | The demo mailbox is invented mail dated from today, judged by recorded answers; the first Check now always delivers one new mail, later ones keep the 5-minute cooldown. | The mail filter's samples have fixed 2026 dates; the demo needs "Check now finds something". |
| P10 | A mail card's `due_at` is its deadline to register (kind deadline), else the exam or event day (a date with no time shows at 9 AM, as the LLM does); the event's own date is kept beside it. Mail deadlines also appear in "due this week". | One table drives the list, reminders and calls; a registration deadline is something due. |
| P11 | The mail judge uses Bedrock when `BEDROCK_MODEL_ID` is set, else the Anthropic API key. | Either key the team has works. |
| P12 | Google's own OAuth `state` is the one-time code (10 minutes, single use, PKCE). The callback page only hands the code back to the app (`sevenfive://google`), which finishes the sign-in with the student's own token, so a forwarded consent link can't attach someone else's account. Scopes: `openid email`, `gmail.readonly`, `calendar.events`, Classroom courses and own coursework read-only. A student may grant a subset; each feature checks its scope. | No student token in any URL; an independent review found the account-injection risk of finishing in the browser. |
| P13 | The voice assistant is a second ElevenLabs agent (Claude Haiku 5.5) whose tools are client tools the phone runs through `/api/tools`; signed URLs only; 5 minutes; nothing stored. | Same rules as a tap; no standing credential at ElevenLabs. |
| P14 | Calls add Exotel (now native in ElevenLabs) beside Twilio and SIP; the call agent's only tools are ElevenLabs' hang-up and voicemail detection. | An Indian caller id without a SIP trunk; voicemail never gets a message. |
| P15 | A demo reset keeps the student's setup (Google account, registered phones, call consent and quiet hours) and resets only the demo data and demo mailbox. | Reconnecting Google before every rehearsal would break the demo. |
| P16 | Firebase is started from four build settings, without google-services.json or its plugin; absent, the app pulls every 15 minutes. | The APK builds and runs with no Firebase project. |
| P17 | The briefing voice defaults to ElevenLabs' premade "George", mp3 at 64 kbps, cached per student, day and text. | Small enough for Lambda; a second tap is free. |
| P18 | The demo morning's weekdays ("due Fri") mean the next such weekday after now. | On Fridays the old rule put "Fri" just outside "due this week". |
| P19 | Every Lambda tick shares one 22 s deadline; a mail is only started with 12 s left, Classroom with 15 s; Check now answers within 20 s and the rest goes on in the background. Claude has one 9 s try per mail and one 12 s try per message (no retries). | A tick or request that overran 29 s would reset the instance and its /tmp data, the Google connection with it. |
| P20 | The invented demo morning always replays its recorded answers (`DEMO_LIVE_REPLAY=1` replays it live on a laptop); real events use the live models whenever the keys are set. | A cold start with keys would otherwise spend its 29 s and money classifying invented messages. |
| P21 | One Supabase Postgres for the core, PortMax and the mail filter, through the **transaction pooler** (port 6543): no prepared statements or pipelines, a connection idle 20 s checked with `SELECT 1` before use, SSL required. Every table gets row level security with no policies, and anon/authenticated lose their grants. The demo student is refreshed once a day and its reset touches only its rows. | Lambda reaches the internet over IPv4 only; the pooler is IPv4 and made for serverless. The publishable key ships in apps, so Supabase's Data API must see nothing. One shared database must never be wiped for a demo. |
| P22 | Accounts are Supabase Auth, email + password, confirmed with a 6-digit emailed code (codes, not links). The phone calls Supabase itself; the server checks each access token (JWKS for ES256/RS256, the legacy secret or Supabase's /user for HS256) and maps its `sub` to a student. Username (unique, lowercase), name, college, branch, year, interests and subjects live in our database. | Per-IP sign-in limits apply to each phone, not to the server; links in emails would need a web page and break in mail scanners. |
| P23 | A username sign-in goes through the server (it finds the email; same answer for an unknown name and a wrong password; 10 tries per 5 minutes per address). Personal tokens (MCP) are stored as SHA-256, shown once, and work for `/mcp` only. WhatsApp is linked by a code the student sends to the bot, whose signed webhook proves the number. | Usernames are the Instagram way; a token or a typed phone number must never let one student act as another. |
| P24 | The demo account (public token, "Try the demo") can't connect Google or WhatsApp, get a token, change its profile or be deleted; only it may use `/demo/*`. Real accounts never get invented mail (mail mode `none` until Google). Event keys are unique per student. | Everyone shares the demo student; classmates share Classroom coursework ids. |
| P25 | Deleting an account revokes Google, forgets the mail filter's and PortMax's rows, removes every row, then the Supabase login (secret key); without the secret key nothing is deleted. The phone's session is sealed by the Android Keystore; signing out also clears the portal's WebView cookies, notifications and this phone's push registration. | Google Play requires account deletion; a shared phone must not leak the last student's data. |
| P26 | The MCP connector: Claude Code and Codex sign in as the student with OAuth 2.1 (MCP's authorization spec: protected-resource and server metadata, dynamic registration, PKCE S256, our own sign-in page checking the password with Supabase). Access tokens last an hour, refresh tokens 90 days, both replaced at every refresh, kept as SHA-256, good for `/mcp` only; Settings lists and disconnects each app. The MCP SDK's handlers do the protocol checks. Personal tokens stay for apps that can only send a header. | One command and a browser sign-in on the laptop, nothing copied from the phone; the same sign-in is what claude.ai's and ChatGPT's connectors need, which a pasted token can't do. |
| P27 | The serverless stack is two functions on one address: ApiFunction (the app's API, webhooks, MCP, sign-in, the tick) scales out; DemoFunction (the catch-all: the demo's mock portal, whose logins live in memory) is kept to one instance. The tick isn't retried; the functions log JSON; a key Parameter Store can't give stops the start instead of running on stand-ins. | With everything on one pinned instance, any two overlapping requests got HTTP 500 and the 1 PM mail check blocked the app. The old function keeps its name, so a stack updated in place keeps its address. |
| P28 | The shared demo's WhatsApp number is always the invented one (DEMO_PHONE is gone); it reads only the invented library; its calls ring only DEMO_STUDENT_PHONE and its daily caps (calls, voice sessions, new briefing clips) survive a reset. On a deployed server (Lambda or Postgres) the public development secrets are refused: approvals without APPROVAL_SECRET, Connect Google without TOKEN_ENCRYPTION_KEY. | The demo token is public: tied to a real number it read that person's files and forwards and rang their phone. A forgotten key must fail closed, not quietly protect real data with a public secret. |

## Keys and accounts the team hands over at the end

The full checklist, where each goes and how to get it: [`docs/keys.md`](docs/keys.md). In short:
`APPROVAL_SECRET`, `TOKEN_ENCRYPTION_KEY`; the bot's `BOT_WEBHOOK_SECRET`, `LIBRARY_URL`,
`LIBRARY_SERVICE_TOKEN`, `DEMO_PHONE`; `ANTHROPIC_API_KEY` or `BEDROCK_MODEL_ID`; `JEV_API_KEY`;
`GOOGLE_CLIENT_ID`/`SECRET`; ElevenLabs (`ELEVENLABS_API_KEY`, the two agent ids from the setup
commands, the imported phone number's id, `CALL_PROVIDER`, the webhook secret,
`DEMO_STUDENT_PHONE`); optionally Firebase (`FCM_SERVICE_ACCOUNT_JSON` and four app settings);
Supabase (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, two
email templates and your own SMTP: [`docs/supabase.md`](docs/supabase.md)); `BOT_WHATSAPP_NUMBER`.

## Log

- 26 Nov: plan written. Android SDK installed in the environment (setup script saved); a
  debug APK of the unchanged app built. Core tests: 30 passing.
- 26 Nov: Phase 1 committed (`5122908`). The team's overnight work merged (`df21b28`: the
  serverless Lambda demo, the in-app demo tour, the app redesign, the MSRIT WebView test).
  The background loop moved into the online service's router so it survives `/demo/reset`.
  Core tests: 52. Call module (`calls.py`) written, tests not yet.
- 26 Nov: MSRIT refused the app's own WebView (teammates' test, `docs/portal-webview-test.md`);
  `docs/portmax.md` updated. Handoff for Kartik written: `docs/handoff-kartik.md`.
- 26-27 Nov (the integration push, from Jnanottam's "integrate everything"): Phases 2-10 built
  on the serverless demo. Calls finished (Exotel, voicemail hang-up, 24 tests). Briefing with
  ElevenLabs voice. Voice assistant (server: signed URLs, agent and client tools as code; app:
  WebSocket audio and tools through the gateway). College mail from the mail filter into items,
  demo mailbox, Check now. Google sign-in on the server, real Calendar, Classroom. MCP over HTTP
  at `/mcp`. Lambda: keys from Parameter Store, once-a-minute tick, Bedrock permission, new
  outputs; the zip passes its smoke test (mail, briefing, voice fallback, MCP, tick). App:
  notifications (outbox pull, WorkManager, optional Firebase), call opt-in, briefing, classes,
  Done with Undo, mail cards, Google, voice screen, background portal keep-alive, demo tour
  steps. Two independent reviews (server, app) found 16 issues; all fixed: the voice
  assistant's connect/stop races and server-initiated close, rotation ending a conversation,
  the keep-alive switch reset by a portal logout, Firebase wake-ups on Android 8-11, the
  briefing playing twice, audio effects collected mid-call, the notification row's dead end;
  Lambda time budgets (P19), a cut-off mailbox not revived on reconnect, cards hidden after
  disconnect and reconnect, the sign-in finishing in the browser (P12), Classroom tagging the
  wrong card, the phone number in the cards, the live replay on cold starts (P20). Tests:
  core 134, PortMax 100, mail filter 206; Android 45 unit tests; debug and demo APKs build; the
  Lambda zip passes its smoke test. Not run here: a phone or emulator (none in this sandbox),
  and any live account (no keys yet). Found and fixed: the demo's "due Fri" on Fridays (P18).
- 26 Nov (Supabase and real accounts, from Jnanottam's "setup supabase too / a real sign in, ig
  style"): one Supabase Postgres for everything (P21), tested through PgBouncer in transaction
  mode as Supabase's pooler runs; accounts on Supabase Auth (P22-P25): the server checks access
  tokens (JWKS, legacy secret, or Supabase), profiles with unique usernames, username sign-in,
  personal MCP tokens stored hashed, WhatsApp linked by a code through the bot, account deletion,
  the demo account's limits, row level security on every table. App: Instagram-style log in,
  sign up, email code, forgotten password, profile setup and editing; the session sealed by the
  Keystore and refreshed one at a time; Settings → Account (WhatsApp, MCP token, log out,
  delete); nothing polled while signed out; the last student's data cleared on sign-out. Found
  and fixed on the way: Classroom work shared by classmates would have filed for only one of
  them (event keys now per student); real accounts would have received the demo's invented
  mail; a demo reset or cold start would have wiped every table; Parameter Store's
  `DATABASE_URL` lost to the `/tmp` default; an empty `.env` value overrode a default; a literal
  `%` in SQL broke on Postgres. The cascade now calls Bedrock's Messages API like the mail judge
  (one model id, `anthropic.claude-haiku-5-5`).
- 26 Nov: two independent reviews of that work (server: 12 findings, app: 13) and every one
  fixed or documented. Server: the public development bot secret no longer accepts a real
  account's events or links WhatsApp (it could have taken a student's number); a demo reset
  replays on its own copy of the app instead of swapping the live models, one at a time, at most
  3 a minute, and the demo also refreshes at 5 AM; rate limits use the address our proxy saw
  (the last `X-Forwarded-For`), and a flood of keys no longer resets them; PortMax's and the mail
  filter's tables are locked down wherever they open; a failed key fetch keeps the keys already
  held; schema changes look before they lock and wait at most 5 s; a long message can't make the
  link-code check slow; the mail jobs only read students with a mailbox; a token whose `alg`
  doesn't fit its key is a 401, not a 500; a deleted account's session can't make a new profile.
  App: who is signed in changes under one lock with a generation count, so a late refresh can't
  bring back a logged-out session and a late answer is never applied to the next person; the
  clean-up on a switch never calls back into the account code (no deadlock); a sign-in finishes
  even if its screen went away; logging out first gets a token Supabase accepts; only Supabase's
  own codes end a session; the session is read and written off the main thread and a passing
  Keystore error no longer wipes it; a new reset code is checked again; the phone registers once
  the profile exists; another server's sign-in settings are never used; switching person also
  clears the portal WebView's storage and cache and the briefing's audio. Tests: core 170 on
  SQLite (+3 Postgres-only), 173 on Postgres and through the pooler; Android 68 (the account
  tests five times in a row); the Lambda zip passes its smoke test on SQLite and twice on
  Postgres through the pooler, all 23 tables locked. Not run here: a real Supabase project, a
  phone (no emulator), the screens rendered.
- 27 Nov: a deep check before real use. Five independent reviews (deployment, accounts and data,
  integrations, the Android app, and every instruction in remaining-steps.pdf against the
  vendors' current docs) found about 70 problems; each is fixed or written down in the PDF's
  "Known gaps". Server: P26–P28 above; text no column can hold (a NUL, half a character) and
  numbers past 64 bits are a 400 on both engines; every tool's arguments are checked before it
  runs or an approval is spent; a link code and an OAuth code are spent by one statement; the
  demo's seed takes a Postgres advisory lock; indexes are created only when missing, under a lock
  timeout; a dropped connection is noticed within 10 s; an answered call is never relabelled
  missed; ElevenLabs records no voice and keeps conversations 30 days; Firebase wake-ups are
  sent before Lambda freezes; linking WhatsApp pulls in the bot's deadlines; the Lambda zip ships
  Python 3.12 bytecode and pinned versions. Found outside this repository: the bot's side of the
  link isn't on any of its GitHub branches (Kartik), and ChatGPT's connectors take OAuth only.
  The connector was tried with the real Claude Code and Codex against a local server: both signed
  in, and Claude Code reported Connected.
