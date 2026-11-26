# Online evaluation demo: run of show

5-minute pitch + 3-minute Q&A, over screen share. The demo is about **3 minutes** of it.
Everything below runs against the online demo server (one HTTPS address, see
[`online.md`](online.md)). All data is invented.

## What is on screen

| Window | Shows |
|---|---|
| Phone mirror (scrcpy or the phone's screen cast) | The Android app, pointed at the online server |
| Claude Desktop | 7even5ive connected as an MCP server |
| Terminal (small, corner) | Only for the fallback "bot" sender |
| Slide | Architecture, for the close |

## Before the call (checklist)

| # | Item | Status |
|---|---|---|
| 1 | Demo server up: `<AppUrl>/api/health` answers `{"service":"7even5ive",...}`. **Reboot it an hour before** so it starts from a clean demo morning. | Built |
| 2 | APK installed, opens on the online server, pull to refresh works | Built |
| 3 | **Claude Desktop talks to the same server as the phone.** Today the MCP server only runs on the laptop over stdio and reads the laptop's own database, so an "add to calendar" asked in Claude would never reach the phone's Approve. Needs MCP served at `<AppUrl>/mcp`. | **Not built** |
| 4 | A way to show a forward arriving: either the WhatsApp bot posts signed events to `<AppUrl>/bot/webhook` with its decision ([`bot-events.md`](bot-events.md)), or a laptop script posts the same signed event as the bot would. Set a real `BOT_WEBHOOK_SECRET` on the server: the default is in the public repository. | **Not built** (either way) |
| 5 | Live Jev and Claude: pass `JEV_API_KEY` and `BEDROCK_MODEL_ID` to the server's container. Without them the server replays recorded answers; say so if asked. | Your call |
| 6 | Backup screen recording of the whole run, in case the network drops | To record |

## Run of show

**0:00 Hook (20 s).** "This is my phone on a Tuesday." Show the problem slide: 62 messages in the
class group, a PDF in another, Classroom, 99+ mails, a portal that never warns.
"Everything you need is somewhere. 7even5ive puts it at your fingertips, using MCP."

**0:20 The morning (40 s).** Open the app. *Due this week*: DBMS Assignment 3 (Fri), IISc
hackathon (Sat), OS mini project (Classroom), DCN CIE-2 (Mon).
Point at the small route tags: "This one the WhatsApp bot had already filed, so no model ran.
This one came from Classroom with its own date. This one, Jev and Claude read."
Open *From your inbox*: "Two mails filtered: one pretending to be the placement cell, one
selling a paid internship. The real hackathon stayed, matched to a 3rd-year CSE student."

**1:00 Attendance (35 s).** Tap *Connect portal*. The college's own login page opens inside
the app; log in by hand (CAPTCHA `PM42X`). Attendance appears:
"DBMS 73.33%: attend the next 2 classes in a row, starting Thu, to get back to 75%."
"We never see the password and never solve the CAPTCHA. The student logs in; the app keeps
the session; only the answers reach our server. The sentence is arithmetic, not a model."

**1:35 A new forward (30 s).** Forward "DS lab record due Monday 10 am" to the bot (or run the
sender). Pull to refresh: the card appears. "The bot pushes a signed event; nothing polls.
A replayed or forged request is rejected before it costs anything."

**2:05 Your own AI (55 s).** In Claude Desktop:
1. "What's due this week?" → Claude lists the same cards through the `due_this_week` tool.
2. "Remind me an hour before the DBMS assignment." → `set_reminder`; it appears in the
   app's Reminders.
3. "Add it to my Google Calendar." → Claude says it needs approval. The phone shows
   *Add to Google Calendar?* → tap **Approve** → done. Tap again: "approval already used".
4. "Email my professor that I'll submit late." → there is no send tool; Gmail is read-only.

**3:00 The safety story (20 s).** "Every call, from Claude, the voice agent or this app,
passes one gateway: deny by default, a write can only use what 7even5ive filed itself, and an
approval works once for that exact action. The rules sit outside the model, so a forwarded
message telling it to misbehave can't widen them." Show the gateway log in the app.

**3:20 Close (10 s).** Architecture slide. Hand back to the pitch.

## If something breaks

| Breaks | Do |
|---|---|
| Server slow or down | Play the backup recording from that step; keep talking |
| Portal login fails | Skip to "Your own AI"; attendance is already on the slide |
| Forward doesn't arrive | Pull to refresh once; then move on and show the existing cards |
| Claude doesn't call the tool | Ask again with the tool's name: "use due_this_week" |
| Approval missing on the phone | Pull to refresh; approvals expire after 15 minutes |

## Likely questions

- **Why Jev and an LLM?** Jev ticks boxes for about $0.00003 a call; the LLM only reads dates
  and titles, or decides when Jev is unsure. Messages the bot already filed skip both.
- **What stops prompt injection?** No send, pay, submit or delete tools exist; writes need
  provenance and a one-time token. Nothing depends on the model refusing.
- **Is the portal scraping legal?** The student logs in themselves inside the app; GET-only
  fetch plans; no CAPTCHA solving or evasion; real students only with the college's written
  permission.
- **Does data stay in India?** Servers and database are in Mumbai. The LLM call and Jev are
  not India-only; we say so on the privacy page.
- **What runs on AWS?** Today the demo server is EC2 + CloudFront in Mumbai. The production
  design is Lambda, SQS with a dead-letter queue, Bedrock and AgentCore Gateway, with
  Supabase in Mumbai ([`deploy.md`](deploy.md)).
