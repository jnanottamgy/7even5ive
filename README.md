# 7even5ive

**Everything at your fingertips, using MCP.** One agent for a student's college life: it turns
WhatsApp class groups, college mail, Google Classroom and the college portal into deadlines,
materials, attendance warnings and real opportunities, and serves them to the student's phone
and to their own Claude or ChatGPT over MCP, behind one gateway with one set of rules.

> wHACKiest 2026 · Track 1: *Make MCP Matter. Less Magic, More Utility.*
> Team: Jnanottam GY · Kartik · Mohammed Zaid

**The design is this README and [`docs/decisions.md`](docs/decisions.md).** The PDFs and older
diagrams in the repository are earlier snapshots and are superseded wherever they disagree.

## Run it

```bash
cd core
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt    # Windows; bin/ elsewhere
python -m seventy5.demo        # a morning's messages end to end, then the web app on :8000
python -m pytest -q
```

No accounts needed: every external service has a stand-in, and without keys the demo replays
recorded Jev and LLM answers (it prints which mode ran). Keys go in `core/.env`, which git ignores.

## The problem

A student's semester is spread across apps that never talk: deadlines buried under memes in
WhatsApp groups, notes scattered across groups, Drive links and Classroom, a college inbox where
real internships hide among paid offers and fake "placement cell" mail, and a portal that shows
raw attendance numbers and never warns you before you're barred.

## What 7even5ive does

| | |
|---|---|
| **In** | The student forwards to our WhatsApp bot, which pushes a signed event to 7even5ive. College mail (read-only), Google Classroom and the portal (through PortMax) are connected once. Voice notes come only through the bot. |
| **Understand** | A cascade: Classroom's own due date → **Jev** → **LLM**. Jev ticks boxes (what is it, which subject, is the mail spam or fake, is it relevant); the LLM reads dates and titles, or decides when Jev is unsure. Code checks every value against the student's real data before anything is written. |
| **Library** | Every material filed by subject (5 subjects + Miscellaneous), one tap away. |
| **Out** | "Due this week" on the phone; attendance with the exact classes to attend or skip; opportunities that fit the student's branch, year and interests; opt-in reminders and an opt-in urgent call. |
| **Your own AI** | 7even5ive is an MCP server: plug it into Claude, ChatGPT, Claude Code or any MCP client. |

It organises and presents; it does **not** plan study schedules. It never notifies a student about
a deadline they just forwarded themselves.

## What it does, and what it never does

| Does for you | Needs your tap | Never (the tools don't exist) |
|---|---|---|
| Files deadlines, exams, materials, events and notices | Adding a deadline to Google Calendar (one-time approval token) | Sending mail (Gmail is read-only) |
| Filters spam and fake placement mail | | Submitting assignments or forms |
| Shows attendance: "attend the next 2 DBMS classes" | | Writing to the college portal |
| Answers your AI's questions about your semester | | Paying fees, deleting your data |

## Architecture

```
Triggers            Ingress               Queue        Workers              Gateway              Tools / data
WhatsApp bot  ──>  bot-webhook λ ──┐
Gmail push    ──>  gmail-webhook λ ┼──>  SQS + DLQ ──> cascade λ ─┐                          Gmail · Classroom (read)
Classroom     ──>  (via Gmail)     │                  approve λ   ├─> AgentCore Gateway ──>  Google Calendar
EventBridge   ──>  portal-check λ ─┘                  briefing λ  │   auth · interceptor     WhatsApp bot API / MCP
  (every morning)                                     notify λ  ──┘   Cedar · Identity ·     agent tools (DB)
Phone · Claude · ChatGPT · ElevenLabs agent ─────────────────────────> observability          PortMax (portal)
                                                                                             Neon Postgres · Bedrock
```

Full components and flows: [`docs/architecture.md`](docs/architecture.md). The gateway's rules:
[`docs/policy.md`](docs/policy.md). The bot's event format: [`docs/bot-events.md`](docs/bot-events.md).

## Stack

| | |
|---|---|
| **AWS** | Lambda workers, SQS with a dead-letter queue, API Gateway, EventBridge (morning portal check, reminders), AgentCore Gateway (inbound auth, interceptor Lambda, Cedar, Identity vault, observability), Bedrock (Claude Haiku 5.5), S3 + CloudFront (files, web app), SSM (keys), CloudWatch. Nothing runs while nobody is using it. |
| **Database** | Neon Postgres. No VPC, so the Lambdas need no NAT gateway. |
| **Jev** | TypeSafe's decision model via OpenRouter: about $0.00003 a call, output free. |
| **ElevenLabs** | Morning briefing (TTS), the voice agent and the urgent call (an MCP client like any other), Scribe for voice notes. |

## PortMax: any college portal

College portals have no API. **PortMax** records a portal being used once and builds a connector
that gives every college the same five read-only, replay-verified tools (`get_attendance`,
`get_timetable`, `get_marks`, `get_results`, `get_profile`) plus `get_attendance_plan`, the bunk
math in exact fractions. 7even5ive reads PortMax's saved answers; it has no attendance maths of its
own. Plan: [`docs/portmax.md`](docs/portmax.md).

## Repository map

| Path | What it is |
|---|---|
| [`core/`](core) | 7even5ive itself: ingress, cascade, gateway, tools, MCP server, web app |
| [`portmax/`](portmax) | The portal connector and bunk math |
| [`docs/decisions.md`](docs/decisions.md) | Decision log: the source of truth when anything disagrees |
| [`docs/architecture.md`](docs/architecture.md) | Components and flows |
| [`docs/policy.md`](docs/policy.md) | The control model enforced at the gateway |
| [`docs/business.md`](docs/business.md) | Pricing, market |
| `ppt/` · `video/` · `brand/` · `diagrams/` | Deck, film, brand kit, diagrams |

All demo data is invented. We never sell student data, and Gmail data is never used for ads.
