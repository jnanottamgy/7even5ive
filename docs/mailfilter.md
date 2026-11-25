# College mail filter

**Status: built ahead of hack day (25 Nov 2026), code in [`mailfilter/`](../mailfilter).** The
live, commented plan is the "College Mail Filter: Build Plan" doc; this file is its copy in the
repository. Where they disagree, the newer one wins and both get fixed.

## Conclusion

The mail filter reads a student's college mail **twice a day, at 1 PM and 9 PM India time**,
keeps only **placements, internships and exam-cell notices**, and turns each into a card with its
deadline, event date, form link and a link back to the mail. Gmail access is read-only. Claude
Haiku 5.5 on Amazon Bedrock (Mumbai) proposes; code checks every field against the mail; a field
that fails is dropped, never guessed. The student fills every form themselves.

## A real-life example

Tuesday 1 December. Riya's college inbox gets a placement drive at 10:12 AM (register by Thu
3 Dec, 5 PM), a revaluation notice at 1:40 PM (till Sat 5 Dec), a webinar ad, the college
newsletter, an internship at 6:30 PM (apply by 15 Dec) and a spam mail that tries to give orders.
The 1 PM check reads the morning's mail; the 9 PM check reads the rest. Three cards are made;
the ads and the spam are left alone (the filter has no way to send anything). The 7 AM briefing
says: "New from college mail: Placement: … Last date Thu 3 Dec, 5 PM." Asked "any placement
deadlines this week?", Claude Code answers from the same cards.

## How a check works

1. Retry, by id, mail that could not be judged before; take in what Gmail's change history says
   arrived or was moved out of spam or trash (a rescued mail keeps its old date); then list the
   mail since the last check (Gmail `after:` in exact seconds: a plain date means midnight
   Pacific time), two hours of overlap for mail Gmail lists late, oldest first. The first check
   after connecting reads exactly that day, from midnight India time.
2. Skip mail already judged (by id), sent mail, drafts, spam and trash.
3. The Jev slot may drop obvious junk (only as "other", only at 90% confidence or more). Off.
4. Claude reads the sender, subject, text (cut at 15,000 characters), every link and the names of
   attachments (PDFs are never read) and answers in a fixed JSON shape.
5. Code checks: copied words must be in the mail (not the Received line); a date must be one its
   quote names, at the time it names (23:59 when none), not before the mail arrived; a form link
   must be https, carry no user name, and appear in the mail.
6. Save the outcome and, for a kept mail, the card, in one transaction. A reminder or forward of
   the same opportunity updates the card (same form link from the same company, else the same
   conversation and title, else the same company and role). Per field the newest news wins, and
   a forward counts from the date of the mail it forwards.
7. The next check starts after settled mail only: an outage, a mail Claude cannot judge (retried at
   three checks, then given up), a cap, a disconnect mid-check or two checks overlapping (a lease
   renewed before every mail) never loses a mail or judges one twice.

## Getting into Gmail (confirmed on Google's pages, 25 Nov)

| Point | What Google says | What it means for us |
| --- | --- | --- |
| Permission | `gmail.readonly` and `gmail.metadata` (headers only, no search) are both restricted | We use `gmail.readonly` |
| Real users | Verification (about 6 weeks) and a yearly security assessment (CASA) | After the hackathon |
| Testing mode | Up to 100 test users; access lapses 7 days after consent | Demo accounts sign in again weekly |
| Cost | Standard Tier never charges; 6,000 units per user per minute | A day of 50 mails is about 3,000 units |
| AI agents from 1 Feb 2027 | Must use Google's MCP servers or stay on Standard Tier limits | Recheck before launch |
| College admin | Can block outside apps, separately for under-18s | MSRIT's IT may need to allow us |

Fallback if a college blocks us: the student sets one Gmail filter that forwards placement and
exam-cell mail to a 7even5ive address.

## Cost

Gmail, the schedule and storage cost nothing at our size. Claude does: with Haiku 5.5 roughly
₹0.03 a mail, about ₹27 a month for a student who gets 30 mails a day (Anthropic's list price;
Bedrock prices separately, so confirm). The Jev slot and prompt caching bring it down further.

## Build status

Built on 25 Nov in [`mailfilter/`](../mailfilter): Python 3.12+, ruff and strict mypy clean,
206 tests passing offline, 30 invented sample mails. An independent review found 11 bugs (lost
mail at a listing cap, stale dates kept, drives merged through a shared portal link, date ranges
misread, mail rescued from spam never read, overlapping checks, a disconnect leaving data); each
is fixed and has a test that failed before the fix.

| Part | Status | Code |
| --- | --- | --- |
| Mail parsing: plain and HTML text, links behind buttons, charsets, attachment names | Built | `mime.py`, `mail.py` |
| Gmail client: list, get raw, profile; retries, Retry-After, pacing, named errors (college block, scope, expired) | Built; tested against a faithful fake of Gmail's REST API | `gmail.py` |
| Google sign-in: installed-app flow with PKCE, refresh, revoke, scope check | Built; needs the team's OAuth client to run | `tokens.py`, `wiring.py` |
| Claude judge: Haiku 5.5 on Bedrock Mumbai, structured output, refusal and error handling | Built; tested through the real SDK offline; one live eval run still to do | `judge.py` |
| Code checks and date reading | Built | `checks.py`, `dates.py` |
| Jev slot | Built, switched off | `sorter.py` |
| Store, cards, merging, the twice-daily check, check now | Built | `store.py`, `run.py`, `schedule.py` |
| `get_opportunities`, briefing lines, due-soon list | Built | `tools.py` |
| Lambda (gateway tool + scheduled check), gateway schema, MCP server | Built; check the Lambda event shape against AWS docs before deploying | `adapters/` |
| Production Google tokens in AgentCore Identity | Not wired: the check Lambda refuses until it is | |
| Live run on a demo account, and the real-model eval | Needs the Google OAuth client and Bedrock access | |

## How it relates to the core

The core (`core/seventy5/`, merged the same day) has its own mail path: Gmail push into the
cascade, where Jev rules out spam and fakes and scores relevance, then the LLM reads dates
(decisions 30, 38). The mail filter was built alongside it and differs in three ways: it checks
twice a day instead of by push; it code-checks every quote, date and link Claude copies out of a
mail; and it merges reminders and forwards into one card. Which path ships, or how the two
combine, is Kartik's call (decisions 51–58).

## Decisions

Recorded in [`decisions.md`](decisions.md), 51–58.

## Still open

- MSRIT's mail: is it Google Workspace, and will its IT allow outside apps to read it?
- Push or twice-daily, and whether the mail filter's checks fold into the core's cascade.
- Who owns the mail filter on hack day.
- The team's Google Cloud OAuth client and the demo accounts as test users.
- Bedrock access to Haiku 5.5 in `ap-south-1`, then one run of `mailfilter eval`.
