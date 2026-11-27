# 7even5ive demo script (proof of concept)

About **6–8 minutes**. Two people is easiest: one holds the phone (mirrored to the screen if you
can), one runs the laptop. The laptop runs [`demo/run_demo.py`](../demo/run_demo.py): it prints
each step's line to say, and at the live moments it makes things happen on the server the way
the real source would (the WhatsApp bot forwarding a message, the student's AI asking for a
calendar write). Press **Enter** to move on; nothing happens until you do.

Everything shown is invented demo data running on the serverless demo (AWS Lambda + API Gateway,
[`docs/online.md`](online.md)). The college portal is our mock: MSRIT blocks third-party apps
([`portal-webview-test.md`](portal-webview-test.md)).

## Run it from the phone (no laptop)

The app has the whole demo built in: **gear → Demo tour → Start the demo tour (fresh)**. It
resets the server to the demo morning, then a guide bar docks above the tabs: each step opens
the right tab, shows the line to say, and a button makes the live moment happen (the forward,
the forgery, the AI's calendar request, the send that is refused, the server ping). **Next** and
**Back** move between steps; **✕** ends the tour. The steps are the same as the table below.

The live moments go through demo-only actions on the demo server (`/demo/*` in
`core/seventy5/cloud.py`): the server signs each WhatsApp event with the bot's secret and sends
it through the real webhook, so the secret never ships in the app. They exist only on the demo
service, never in the production API.

The laptop driver below does the same from a terminal, if you prefer that.

## Before you start (10 minutes before)

1. **Phone:** the latest APK installed, internet on (Wi-Fi or mobile data). Open 7even5ive once
   and wait for the cards: this wakes the server (the first load after a quiet spell takes a few
   seconds; after that it's instant).
2. **Laptop:** Python 3 and this repository (`git pull`). Rehearse once without pauses:
   `python demo/run_demo.py --auto`. Every line should say `ok`.
   That rehearsal adds the demo's live cards to the server. For a clean server on stage, start
   a fresh instance: AWS console → **Lambda** → the function → **Configuration** →
   **Environment variables** → **Edit** → **Save** (no change needed). The next request starts
   a new instance with the demo morning only.
3. **Settings on the phone:** gear → it says *Online server: https://fl4el8s1h4…*.
4. **The stack:** `PinToOneInstance` should be `true` (CloudFormation → the stack →
   **Parameters**). With `false`, a card the laptop creates can land on a second instance the
   phone isn't talking to.
5. Start: `python demo/run_demo.py`, open the app, press **Enter**.

## The run

| # | Phone | Say (the script prints this) | You should see | If it doesn't |
|---|---|---|---|---|
| 1 | **This week** tab | One feed for the semester: WhatsApp, mail, Classroom, portal. Point at the small *via* tags. | The morning's 4 cards: DBMS Assignment 3 (*via bot*), IISc hackathon (*via jev+llm*), OS mini project (*via classroom*), DCN CIE-2, plus college mail with a deadline this week (*via mail*) | Pull down to refresh. |
| 1b | **This week** → **Your day** → **Play** | The morning briefing, written by code from the student's own data, read aloud; never a notification. | The briefing plays (ElevenLabs, or the phone's voice without a key: the card says which) | Tap Stop and Play again. |
| 2 | Stay on **This week**; laptop: Enter | A classmate posts a quiz in the group; the student forwards it to our bot. | **"DAA Quiz 2 (greedy + DP)"**, *via bot*, appears within ~7 s. The laptop says it was filed with no AI call. | Pull down. If the laptop said `ok`, the card is on the server. |
| 3 | **Materials** → *Operating Systems* chip; laptop: Enter | Notes are filed by subject, one tap away. | **OS_Unit4_Deadlocks.pdf** under Operating Systems | Tap *All*, pull down. |
| 4 | (laptop only) | Only the student's own, signed messages get in. | Laptop: unknown number → nothing filed; forged signature → **401** | — |
| 5 | **Inbox** tab → **Check now** | College mail, read for you: placements, internships and exam notices; every date, quote and form link is checked against the mail itself; scams never get here. | Nimbus placement drive, Orbitly internship, CIE-3 notice; **Check now** adds the Zentry Labs internship; "**2 spam or fake mails filtered out**" | If it says "checked a moment ago", wait or skip. |
| 6 | **Attendance** → **Refresh** → log in: USN `1MC24CS042`, DOB **14/08/2005**, code `PM42X`, **Next**, digits `2345`, **Log in** | Exact bunk math from the student's own portal session; we never see the password. Mention it's our test portal (MSRIT blocks apps). | Worst subject first (DBMS 73.33%: "attend the next 2 classes…"), then **Updated just now** | If the portal asks to log in again, do it; if it errors, show the existing attendance and move on. |
| 7 | **This week**; laptop: Enter → **Approve** on the card → tap **Approved** again | Your own AI (Claude/ChatGPT over MCP) can ask; only you can approve a write. | **"Add to Google Calendar? DAA Quiz 2…"** at the top → *Added to Google Calendar* → second tap: **"approval already used"** | Pull down to see the card. |
| 8 | (laptop only) | No prompt can make it send mail: the tool doesn't exist; the rules are in the gateway. | Laptop: `send_email` → **403**, no token → **401** | — |
| 8b | **This week** → **Ask your semester** → "Can I skip Friday?" | Ask your semester: answered only from the student's own data, through the same gateway an AI uses over MCP. | The answer, with how it was answered and the tools it called | Without a model key the server answers by code: still fine. |
| 8c | **Attendance** → **Planner** → pick a day → tap classes | Plan a day off: each subject's ring moves to where it would end up. Grades and Timetable sit beside it. | The rings move as classes are skipped | — |
| 8d | **This week** → scroll to **AI activity** | Every request through the gateway, logged: what ran, what waited for a tap, what was refused. | The latest requests with counts | Settings → **AI activity** opens the full log. |
| 9 | Quiz card → **Remind me** → *1 hour before* → **Reminders** tab → **Cancel** | Reminders only when you ask; they arrive as a notification. | The reminder appears, then disappears | — |
| 9b | Settings → **Urgent call** → turn on (read the consent) → **Test call now** | For what really matters: ElevenLabs rings shortly before it's due; two a day at most, never at night; a missed call becomes one notification. | The phone rings (with the ElevenLabs keys set), or "Call recorded" without them | Show Settings' call list. |
| 9c | Microphone at the top → **Start talking** → "What's due this week?" | Just ask. Every fact comes from the same gateway as a tap; adding to the calendar still waits for Approve. | The assistant answers with the week's items | Without ElevenLabs keys the screen says voice isn't set up: skip. |
| 10 | (laptop) | All of it serverless on AWS: Lambda + API Gateway, nothing running when idle. | `demo complete` | — |

## Likely questions, honest answers

- **Is the data real?** The student, messages and portal are invented demo data. The pipeline
  is real: the gateway's rules, one-time approvals, the bunk math, the mail filter (which reads
  real Gmail with Google sign-in), and the AWS deployment.
- **Why not your real college portal?** MSRIT's portal refuses third-party apps, including an
  ordinary in-app browser; we tested it (26 Nov). We don't disguise the app to get past that; we
  are asking MSRIT for an official read-only feed.
- **What stops prompt injection?** There is no send or submit tool at all; a write can only use
  items 7even5ive filed itself; and each approval token is bound to one student, one action and
  those exact arguments, once.
- **What does it cost?** Nothing while idle. Lambda, API Gateway and S3 at demo traffic sit in
  the free credits.

## After the demo

The live cards from the run stay on that instance until it goes cold. To reset: step 2 of
*Before you start* (Lambda → Configuration → Environment variables → Edit → Save).
