# Decisions

The source of truth when any other document, diagram, PDF or slide disagrees. Architecture
decisions are Kartik's. Earlier entries 1–15 are replaced by 29 onwards (git history keeps them); PortMax's 16–28 stand.

## Understanding messages

| # | Decision | Why |
|---|---|---|
| 29 | **Cascade: Classroom's own due date → Jev → LLM.** Every item is either filed or sent to the LLM; there is no third outcome. | The Classroom API already knows the date (free, exact); Jev costs almost nothing; the LLM runs only where it is needed. |
| 30 | **Jev answers two questions on every message:** what it is (deadline, exam, material, event, notice, chit-chat) and which subject (the student's 5 subjects + Miscellaneous). On mail it also says whether it is spam, fake or an unviable paid offer, and how relevant it is to this student. Nothing more. | These are box-ticking questions; Jev bills input only, so they cost about $0.00003 a call. |
| 31 | **No rules, regex or fuzzy matching for intent or subject.** | Text matching misreads intent; quality matters more than the saving. |
| 32 | **The LLM reads dates and titles** (Jev cannot write text), with Jev's answers as hints when Jev was sure, or decides everything when it was not. Claude Haiku 5.5 on Bedrock, or GPT-6 Luna. | Hints shrink the prompt; a forced tool call with the student's subjects as an enum means it cannot invent a subject. |
| 33 | **Cut-offs: file at 0.8, drop (chit-chat, spam) only at 0.9;** both tuned on labelled data, expected between 0.65 and 0.9. | Silently losing a real deadline is the costly mistake. |
| 34 | **The model only proposes.** Code checks every value (kind, subject in the student's list, a readable date for dated items) before a write; a failure becomes a "needs review" card, never silence. | |

## Inputs

| # | Decision | Why |
|---|---|---|
| 35 | **The WhatsApp bot is both a trigger and a tool:** it pushes signed events (HMAC over timestamp + body, 300 s window) and serves an MCP server 7even5ive pulls from. Format: [`bot-events.md`](bot-events.md). | Event-driven, nothing polls. |
| 36 | **No share sheet.** Voice notes come only through the bot (ElevenLabs Scribe). | A share sheet would need its own pipeline, and it can't carry captions. |
| 37 | **The portal is checked once every morning** (EventBridge); only changes become events, and the briefing runs after the check. The portal comes through PortMax. | The portal has no push. |
| 38 | **Classroom arrives through its Gmail emails,** plus the Classroom API for `dueDate`. | One push channel instead of two. |
| 39 | **Gmail is read-only.** | Low risk; no draft or send tool exists. |

## Scope

| # | Decision | Why |
|---|---|---|
| 40 | **No planner.** 7even5ive organises and presents ("what's due this week"); it never plans study time. | Students can't move classes; the useful job is organising what exists. |
| 41 | **Notifications are only opt-in deadline reminders and an opt-in urgent call.** Never notify about a deadline the student just forwarded. | |
| 42 | **Attendance comes from PortMax** (`get_attendance_plan`); 7even5ive keeps no attendance maths of its own. | One implementation, exact fractions, the college's own minimum. |
| 43 | **Sold to individual students only:** free Basic, Plus, a Pro add-on, partner referrals. No college licence. | |

## Infrastructure

| # | Decision | Why |
|---|---|---|
| 44 | **AWS Lambda for compute,** with SQS + dead-letter queue between ingress and workers, API Gateway in front. | Costs nothing idle; a slow model call never holds a webhook open; a crash retries instead of losing the message. |
| 45 | **Neon Postgres for the database.** | No VPC, so no NAT gateway; real SQL; free tier covers the demo. |
| 46 | **One door for every tool call: AgentCore Gateway** (inbound auth, interceptor Lambda checking provenance and one-time approval tokens, Cedar deny-by-default, Identity vault, observability). | Prompt injection arrives in forwards; control is enforced in infrastructure, not in a prompt. |
| 47 | **Idempotency on the source's own id** (WhatsApp message id, Gmail message id), enforced by a unique key. | Gmail pushes 2–3 times per mail; redeliveries must cost one run. |
| 48 | **Logs carry ids and counts only,** never message or mail bodies. | |

## PortMax (16–28, numbered as before)

| # | Decision | Why |
|---|---|---|
| 16 | **PortMax is a factory: one portal in, five read-only tools out** (`get_attendance`, `get_timetable`, `get_marks`, `get_results`, `get_profile`), the same shape for every college. | The rest of the system never needs to know which portal it is talking to. |
| 17 | **Built on reverse-api-engineer as a pinned library, under our own prompts and checks.** Its defaults hardcode captured cookies, keep the password in captures and tell the model to beat bot detection; we replace all three. | It does the hard part (traffic to working code) and is MIT-licensed, but it is built for one developer scraping for themselves. |
| 18 | **The app is Android only; no iOS.** | Team decision. |
| 19 | **The student logs in inside our Android app** (the portal's own page in a WebView) and completes everything the portal asks, CAPTCHA included. We never automate the login or store the password. | Only the student can pass the portal's login; an in-app login lets the app hold the session. |
| 20 | **The app keeps the login alive** with one light portal page at the longest interval the portal allows, sent from the phone. Our server never holds the cookies. | |
| 21 | **The briefing never waits on a login.** Every fetch is saved with its time; a lapsed session means one login the next time the student opens the app. | |
| 22 | **No evasion:** no CAPTCHA solving, WebView spoofing, fingerprint cloaking or IP rotation. Real students only after the college agrees in writing; we ask for an official read-only feed. | The portal says it "cannot be used from third-party apps", and IT Act s.43 turns on the owner's permission. |
| 23 | **Adapter: Lambda behind AgentCore Gateway** for the product; the MCP server only for development and the demo. | Every tool call goes through the gateway's checks. |
| 24 | **Renamed Portal Forge to PortMax.** | Team decision. |
| 25 | **A connector's fetch plan is data (`fetch_plan.json`), not code.** | The same file runs in the Android WebView and on a server; GET-only by construction. |
| 26 | **A keep-alive reads one page; every `refresh_minutes` (3 hours by default, per college) it runs the whole plan.** | Least load on the portal. |
| 27 | **Bunk math is a sixth tool, `get_attendance_plan`, computed from the saved answers.** Each college's minimum lives in its manifest (75 by default). | Exact fractions, so a student at exactly the minimum is never told they are short; no model writes the sentences. |
| 28 | **The Android app is a Must.** | Decisions 19–20 put the portal login and keep-alive inside it. |
