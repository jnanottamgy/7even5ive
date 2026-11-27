# Decisions

The source of truth when any other document, diagram, PDF or slide disagrees. Architecture
decisions are Kartik's. Earlier entries 1–15 are replaced by 29 onwards (git history keeps them); PortMax's 16–28 stand.

## Understanding messages

| # | Decision | Why |
|---|---|---|
| 29 | **Cascade: the bot's own decision → Classroom's own due date → Jev → LLM.** Every item is either filed or sent to the LLM; there is no third outcome. | The Classroom API already knows the date (free, exact); Jev costs almost nothing; the LLM runs only where it is needed. |
| 30 | **Jev answers two questions on every message:** what it is (deadline, exam, material, event, notice, chit-chat) and which subject (the student's 5 subjects + Miscellaneous). On mail it also says whether it is spam, fake or an unviable paid offer, and how relevant it is to this student. Nothing more. | These are box-ticking questions; Jev bills input only, so they cost about $0.00003 a call. |
| 31 | **No rules, regex or fuzzy matching for intent or subject.** | Text matching misreads intent; quality matters more than the saving. |
| 32 | **The LLM reads dates and titles** (Jev cannot write text), with Jev's answers as hints when Jev was sure, or decides everything when it was not. Claude Haiku 5.5 on Bedrock, or GPT-6 Luna. | Hints shrink the prompt; a forced tool call with the student's subjects as an enum means it cannot invent a subject. |
| 33 | **Cut-offs: file at 0.8, drop (chit-chat, spam) only at 0.9;** both tuned on labelled data, expected between 0.65 and 0.9. | Silently losing a real deadline is the costly mistake. |
| 34 | **The model only proposes.** Code checks every value (kind, subject in the student's list, a readable date for dated items) before a write; a failure becomes a "needs review" card, never silence. | |

## Inputs

| # | Decision | Why |
|---|---|---|
| 35 | **The WhatsApp bot is both a trigger and a tool:** it pushes signed events (HMAC over timestamp + body, 300 s window) and serves an MCP server 7even5ive pulls files from. **When the bot has already filed a message, the event carries its decision** (kind, subject, title, date) and 7even5ive files it after a check in code, with no model call; when it was unsure, 7even5ive's own cascade decides. Format: [`bot-events.md`](bot-events.md). | The bot already classified it; doing it twice costs twice and two systems could disagree. Jev and the LLM do the work the bot never sees: mail and Classroom. |
| 36 | **No share sheet.** Voice notes come only through the bot (ElevenLabs Scribe). | A share sheet would need its own pipeline, and it can't carry captions. |
| 37 | **The portal is checked every 3 hours** (PortMax's refresh); only changes become events. The morning briefing uses the freshest saved answers and never waits on a login. | The portal has no push; attendance changes daily. |
| 38 | **Classroom arrives through its Gmail emails,** plus the Classroom API for `dueDate`. | One push channel instead of two. |
| 39 | **Gmail is read-only.** | Low risk; no draft or send tool exists. |

## Scope

| # | Decision | Why |
|---|---|---|
| 40 | **No planner.** 7even5ive organises and presents ("what's due this week"); it never plans study time. | Students can't move classes; the useful job is organising what exists. |
| 41 | **Notifications are only opt-in deadline reminders and an opt-in urgent call. 7even5ive notes the reminders and fires them** (the bot does not). Never notify about a deadline the student just forwarded. | One owner, so a student never gets the same reminder twice. |
| 42 | **Attendance comes from PortMax** (`get_attendance_plan`); 7even5ive keeps no attendance maths of its own. | One implementation, exact fractions, the college's own minimum. |
| 43 | **No business model.** 7even5ive is a hackathon entry; nothing is priced or sold. | |

## Infrastructure

| # | Decision | Why |
|---|---|---|
| 44 | **AWS Lambda for compute,** with SQS + dead-letter queue between ingress and workers, API Gateway in front. | Costs nothing idle; a slow model call never holds a webhook open; a crash retries instead of losing the message. |
| 45 | **Supabase for the database** (Postgres, row-level security, Realtime, Auth). Lambdas connect through its connection pooler. **Region: Mumbai** (`ap-south-1`), as is the AWS account. | Real SQL; Realtime pushes cards to the phone and Auth signs students in, so we build neither; no VPC, so no NAT gateway; the free tier covers the demo. |
| 46 | **One door for every tool call.** First our own gateway code (`gateway.py`) on Lambda; **AgentCore Gateway replaces it later** (inbound auth, interceptor Lambda checking provenance and one-time approval tokens, Cedar deny-by-default, Identity vault, observability). | Prompt injection arrives in forwards; control is enforced in infrastructure, not in a prompt. |
| 47 | **Idempotency on the source's own id** (WhatsApp message id, Gmail message id), enforced by a unique key. | Gmail pushes 2–3 times per mail; redeliveries must cost one run. |
| 48 | **Logs carry ids and counts only,** never message or mail bodies. | |

## Prototype

| # | Decision | Why |
|---|---|---|
| 49 | **No sign-in in the prototype.** One demo student, identified by a fixed token. | Sign-in adds nothing to what the prototype has to show. |
| 50 | **The prototype's only app is Android.** The web page in `core/` is a development view, not a product. | The Android app has to exist anyway for the portal login (decision 19). |

The prototype's integration defaults (26–27 Nov), chosen on the team's behalf and changeable:
`plan.md` P1–P18 (the serverless tick, the demo mailbox, mail cards as items, Google's scopes,
the voice assistant's client tools, Exotel calls, what a demo reset keeps).

## Mail filter (51–58: built 25 Nov in `mailfilter/`; how it fits the core is Kartik's call)

Built from an approved plan ([`mailfilter.md`](mailfilter.md)) in a session that ran alongside the
core. It overlaps the core's mail path (Gmail push into the cascade, decisions 30, 38, 47): see
the open question below before either is wired to production.

| # | Decision | Why |
|---|---|---|
| 51 | **The mail filter checks college mail twice a day, at 1 PM and 9 PM India time**, plus "check now" (5-minute cooldown). Each check reads everything since the last one; a two-hour overlap catches mail Gmail lists late, and Gmail's change history brings in mail rescued from spam or trash. | Simple and free; the 1 PM check catches a morning mail with a same-day deadline in time. |
| 52 | **Claude Haiku 5.5 on Bedrock (Mumbai) judges each mail** in a fixed JSON shape (placement, internship, exam notice or other, with quotes); **code checks every field against the mail**: copied words must be in it, a date must be one its quote names and not before the mail arrived, a link must be https and in the mail. What fails is dropped. | Same model as decision 32; quotes make an invented date or link detectable in code. |
| 53 | **A slot for Jev in front of Claude, switched off.** It may only drop a mail as "other" at 0.9 or more, never keep one. | Matches decision 33's drop cut-off; Jev cannot write the dates and links a card needs. |
| 54 | **Gmail read-only (`gmail.readonly`); demo accounts in Testing mode for the hackathon.** Real students wait for Google's verification (about 6 weeks) and yearly security assessment. | Both Gmail scopes that read mail are restricted; Testing mode allows 100 test users and a 7-day sign-in. Confirmed on Google's pages, 25 Nov. |
| 55 | **If a college's Google admin blocks the app, the fallback is a Gmail forwarding filter** to a 7even5ive address. | Needs no Google permission. |
| 56 | **Mail bodies are never stored;** a dropped mail leaves only its id, a kept one only its checked card fields. | As decision 48, applied to storage. |
| 57 | **Its own store for now.** Cards merge reminders and forwards (same form link from the same company, else the same conversation and title, else the same company and role); per field the newest news wins, and a forward counts from the date of the mail it forwards. | Built before the core's database existed; moves to Supabase if adopted. A shared placement-portal link alone must never merge two drives. |
| 58 | **Searches use exact seconds, not dates.** | Gmail reads a plain `after:` date as midnight Pacific time, which would miss or repeat India-time mail. |

### Open (mail filter)

- **Push (decision 38) or twice-daily (51)?** The prototype now uses the twice-daily mail filter
  (plan.md P2, built 27 Nov); the core's push path stays in the code, unfed. Either keep the core's Gmail push and fold the mail
  filter's checks (quotes, date reading, link checks, merging) into the cascade, or feed the
  core's ingress from the mail filter's twice-daily check and drop push. Kartik's call.
- Whether MSRIT's mail is Google Workspace, and whether its IT allows outside apps to read it.
- The team's Google Cloud OAuth client; Bedrock access to Haiku 5.5 in Mumbai for the eval.

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

**Permission update (26 Nov 2026).** The team reports that the college has granted permission to
use the app against its portal, which is the condition decision 22 set for a real portal (and the
condition IT Act s.43 turns on). On that basis an `msrit` connector and live in-app fetching are
being built. Decision 22 still stands as written: file the **written** grant (who authorised it,
scope, date) alongside this log, and keep asking for an official read-only feed as the robust
long-term route so a demo can't break if the portal's third-party block changes. The in-app login
remains the student's own, with their own credentials; the app automates no login and solves no
CAPTCHA. _To fill in: authoriser, scope, date of the written permission._
