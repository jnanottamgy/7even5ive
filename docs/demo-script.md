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
**Back** move between steps; **✕** ends the tour. The steps are the same ten as the table below.

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
| 1 | **This week** tab | One feed for the semester: WhatsApp, mail, Classroom, portal. Point at the small *via* tags. | 4 cards: DBMS Assignment 3 (*via bot*), IISc hackathon (*via jev+llm*), OS mini project (*via classroom*), DCN CIE-2 | Pull down to refresh. |
| 2 | Stay on **This week**; laptop: Enter | A classmate posts a quiz in the group; the student forwards it to our bot. | **"DAA Quiz 2 (greedy + DP)"**, *via bot*, appears within ~7 s. The laptop says it was filed with no AI call. | Pull down. If the laptop said `ok`, the card is on the server. |
| 3 | **Materials** → *Operating Systems* chip; laptop: Enter | Notes are filed by subject, one tap away. | **OS_Unit4_Deadlocks.pdf** under Operating Systems | Tap *All*, pull down. |
| 4 | (laptop only) | Only the student's own, signed messages get in. | Laptop: unknown number → nothing filed; forged signature → **401** | — |
| 5 | **Inbox** tab | College mail minus the scams. | "**2 spam or fake mails filtered out**", IISc hackathon **88% match** | — |
| 6 | **Attendance** → **Refresh** → log in: USN `1MC24CS042`, DOB **14/08/2005**, code `PM42X`, **Next**, digits `2345`, **Log in** | Exact bunk math from the student's own portal session; we never see the password. Mention it's our test portal (MSRIT blocks apps). | Worst subject first (DBMS 73.33%: "attend the next 2 classes…"), then **Updated just now** | If the portal asks to log in again, do it; if it errors, show the existing attendance and move on. |
| 7 | **This week**; laptop: Enter → **Approve** on the card → tap **Approved** again | Your own AI (Claude/ChatGPT over MCP) can ask; only you can approve a write. | **"Add to Google Calendar? DAA Quiz 2…"** at the top → *Added to Google Calendar* → second tap: **"approval already used"** | Pull down to see the card. |
| 8 | (laptop only) | No prompt can make it send mail: the tool doesn't exist; the rules are in the gateway. | Laptop: `send_email` → **403**, no token → **401** | — |
| 9 | Quiz card → **Remind me** → *1 hour before* → **Reminders** tab → **Cancel** | Reminders only when you ask. | The reminder appears, then disappears | — |
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
