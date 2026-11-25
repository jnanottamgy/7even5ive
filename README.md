# 7even5ive

**An MCP server that centralises your college life and organises the chaos into academic data:
deadlines, notes, attendance and placement mail.**

> wHACKiest 2026 · Track 1: *Make MCP Matter. Less Magic, More Utility.*
> Team: Jnanottam GY · Kartik · Mohammed Zaid

**Status: Round 1 blueprint, with PortMax and the mail filter built.** The ideathon round is plans
only, so this repository holds the design, the deck and the film. PortMax, the portal connector,
and the college mail filter are built ahead of hack day in [`portmax/`](portmax) and
[`mailfilter/`](mailfilter) (declare them as prior work if the rules require); the rest of the code
lands on hack day (1–2 Dec, RIT).

> **The current plan is this README and [`docs/`](docs).** Read
> [`docs/decisions.md`](docs/decisions.md) first: it records every decision and why. The PDFs in the
> repository root (`Campus_Copilot_*.pdf`) are earlier snapshots under the old name and are
> superseded wherever they disagree.

---

## The problem

An Indian student's academic life is spread across **four apps that never talk to each other**:

| Where | What lives there | What goes wrong |
|---|---|---|
| **WhatsApp** class groups | Deadlines, announcements, and the notes teachers send | Buried under hundreds of messages and memes. Notes nobody downloads expire ("this media is no longer available"). |
| **College mail** | Placement drives, internships, exam-cell notices | An inbox nobody opens. The drive form closes at 6 PM and you find out at 6:01. |
| **Google Classroom** | Assignments | One more app to check |
| **College portal** | Attendance, timetable, marks | No API, no alerts. You find out you're under 75% when you're barred. |

The night before an exam, everyone scrambles: you message friends for the notes, the syllabus,
the timetable and the circulars, and the ones who have them are busy studying. Nobody replies.

## The solution

7even5ive is **one MCP server for your college life**, personal to each student.

| Layer | What it does |
|---|---|
| **In** | You forward a message or file to 7even5ive on WhatsApp in one tap. College mail (read-only), Google Classroom and the college portal (via PortMax) are connected once. Voice notes go through ElevenLabs Scribe. |
| **Understand** | Claude on Amazon Bedrock reads each message first and picks out the subject, the deadline and the task. Code then checks every answer against the student's real data (their subjects, real dates, their saved deadlines), so nothing is guessed. We are testing **Jev**, a faster intent classifier, for the simplest messages. |
| **SHELF** | Our WhatsApp library, built for ourselves. Every PDF you forward is filed by subject (notes, question papers, circulars). Ask "dbms unit 3 notes" and you get the file in seconds. |
| **Out** | A card on your phone (Add to Calendar, logged, with undo); attendance warnings with the exact number of classes to attend; placement and exam-cell mail in your library; a 7 AM voice briefing; an urgent voice call when it matters. |
| **Your own AI** | Because it is an MCP server, you can plug it into Claude Code, Codex, Cursor, Claude, ChatGPT or any MCP client and ask about your semester. |

Every tool call, from our own workers, the voice agent or the student's own AI, goes through one
door: **Amazon Bedrock AgentCore Gateway**, with Cedar policies that deny by default. Details:
[`docs/architecture.md`](docs/architecture.md), [`docs/policy.md`](docs/policy.md).

## What it does, and what it never does

| Does for you | Needs your tap | Never (the tools don't exist) |
|---|---|---|
| Files a forwarded deadline and shows it as a card | Anything someone else would see, such as sharing a file from your SHELF with a friend | Submitting assignments or forms |
| Files notes, question papers and circulars by subject | Adding events to Google Calendar (one tap, logged, undo) | Paying fees |
| Warns when attendance is at risk: "attend the next 3 DBMS classes" | | Deleting your data |
| Keeps only placement, internship and exam-cell mail | | Writing to the college portal |
| Briefs you at 7 AM; calls you when something is urgent | | Sending mail (Gmail is read-only) |

It does **not** make plans or move classes. Classes are fixed by the college; 7even5ive organises
what you already have.

## Sponsor technology

| Sponsor | Where it is used |
|---|---|
| **AWS** | AgentCore Gateway (the one door, with Cedar policies and our Lambda interceptor), AgentCore Identity (OAuth tokens in a KMS-encrypted vault), Bedrock (Claude, India region), Lambda workers, SQS with a dead-letter queue, EventBridge (7 AM briefing), S3 (files), CloudFront (the web app). Nothing runs while nobody is using it. |
| **ElevenLabs** | Agents: the urgent outbound voice call, connected to the gateway as just another MCP client. Scribe: voice notes to text in Kannada, Hindi and English. Text-to-speech: the morning briefing. |

The data lives in **Supabase** (Postgres with row-level security, Realtime and Auth, Mumbai region).

## PortMax: connecting any college portal

College portals have no API, and every college's portal is different. **PortMax** is our layer
on the open-source [reverse-api-engineer](https://github.com/kalil0321/reverse-api-engineer) (MIT):
it records the portal being used once and builds a connector that gives every college the same five
**read-only, replay-verified** tools (`get_attendance`, `get_timetable`, `get_marks`,
`get_results`, `get_profile`), and a sixth, `get_attendance_plan`, does the bunk math from them:
per subject, how many classes the student can miss or must attend in a row, in sentences no model
writes. The student logs in once inside our Android app, CAPTCHA and all, and
the app keeps that login alive so attendance stays fresh every day. For the demo a mock portal
stands in, so the demo never depends on a real portal. Plan: [`docs/portmax.md`](docs/portmax.md).

## The college mail filter

Placement drives, internships and exam-cell notices are the mail students miss most. The **mail
filter** reads the student's college mail (read-only Gmail) at 1 PM and 9 PM India time and keeps
only those three kinds, each as a card with its deadline, event date and form link. Claude Haiku on
Amazon Bedrock (Mumbai) reads each mail; code then checks every field against the mail itself, so
a date or link the mail does not contain never reaches a card. Mail bodies are never stored. The
cards feed the 7 AM briefing and the `get_opportunities` tool. Plan:
[`docs/mailfilter.md`](docs/mailfilter.md); code: [`mailfilter/`](mailfilter).

## SHELF: why we trust this works

SHELF is the WhatsApp library we built and use in our own class, after too many midnights chasing
friends for notes. It already stores and finds the files we forward. In 7even5ive it is the
library, the storage layer. Note: SHELF files a PDF by its caption, filename and subject; it does
**not** read deadlines out of PDFs.

## Constraints we design around

- **WhatsApp:** the official API cannot read existing class groups, so the student forwards to
  7even5ive's number. Each business-initiated alert costs money (roughly ₹0.12–0.15 per utility
  message in India), so routine alerts go to the app and WhatsApp is kept for what matters.
- **Gmail read-only** is a restricted Google scope: fine for the demo (test accounts, 7-day
  sign-in), but a public launch needs Google's verification and yearly security assessment.
- **Not connected:** Instagram (no usable API for this) and Telegram (blocked in India in June 2026
  over exam leaks).
- **Privacy (DPDP Act):** consent, purpose limitation, deletion on request. The student logs in to
  the portal themselves; we never store passwords or solve CAPTCHAs. The stage demo uses a mock
  portal and a made-up student. **We never sell student data.**

## Repository map

| Path | What it is |
|---|---|
| [`docs/decisions.md`](docs/decisions.md) | Dated decision log: the source of truth when anything disagrees |
| [`docs/architecture.md`](docs/architecture.md) | Components, data flows, tech stack |
| [`docs/brain.md`](docs/brain.md) | How messages, files, mail and attendance are understood and checked |
| [`docs/policy.md`](docs/policy.md) | The control model enforced at the gateway |
| [`docs/portmax.md`](docs/portmax.md) | PortMax: the five-tool contract, the forge pipeline, the Android login and keep-alive |
| [`docs/mailfilter.md`](docs/mailfilter.md) | The college mail filter: twice-daily checks, Claude Haiku plus code checks, Gmail access rules |
| [`docs/business.md`](docs/business.md) | Pricing (also in the deck), market, go-to-market |
| [`docs/build-plan.md`](docs/build-plan.md) | Hack-day scope, owners, hour-by-hour plan |
| `ppt/` | Round 1 deck on the official template |
| `video/` | The Round 1 film: YouTube notes and its full source pipeline |
| `brand/` | Logo (SVG/PNG), app icon, YouTube thumbnail |
| `diagrams/7even5ive_Mind_Map_v2.png` | **The current workflow mind map** (PDF alongside) |
| `diagrams/` (other files) | Earlier diagrams (old name; some show the superseded rules-first design) |
