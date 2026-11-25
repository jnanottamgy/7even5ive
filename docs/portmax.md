# PortMax

**Status: planned, not built (25 Nov 2026).** The live, commented version of this plan is the
"PortMax: Build Plan" doc (named Portal Forge until 25 Nov); this file is its copy in the repository. Where they disagree, the
newer one wins and both get fixed.

## Conclusion

PortMax is a factory that turns a college portal into **five read-only tools** with the same
shape for every college. We forge each college's connector once, with
[reverse-api-engineer](https://github.com/kalil0321/reverse-api-engineer) (RAE) used as a pinned
library under our own prompts, safety rules and tests.

At run time the student **logs in once inside our Android app** (the portal's own page in a
WebView, CAPTCHA and all), and the app **keeps that login alive** by requesting one light portal
page at the longest interval the portal allows. Each keep-alive also refreshes attendance. Data is
saved with its time, so the 7 AM briefing never waits on a login. The output is a fixed contract,
so the work does not wait on the final architecture.

## The five tools

| Tool | Returns (one row per item) | Used for |
| --- | --- | --- |
| `get_attendance` | subject code, name, attended, held, percentage, as-of | Bunk math, the attendance warning |
| `get_timetable` | day, start, end, subject code, room | Briefing, "can I skip tomorrow" |
| `get_marks` | subject code, component (CIE-1, CIE-2, quiz, lab), scored, maximum | Target CGPA |
| `get_results` | semester, subject, credits, grade, grade points, SGPA, CGPA | Target CGPA |
| `get_profile` | USN, branch, semester, section (no name, DOB or photo) | Matching subjects |

A connector is a **fetch plan** (the read-only pages to request, in order, and what each step reads
from the one before) plus **parsers** (pure functions, HTML or JSON to our models). Every result
carries `fetched_at` and the connector version. Failures are named: `SessionExpired`,
`PortalUnavailable`, `PortalChanged`, `NotSupported`.

Per college, Forge outputs `manifest.yaml`, `connector.py`, `parsers.py`, `raw_openapi.json`
(reference only), `fixtures/` and `golden/`. Three small adapters can wrap any connector. **Chosen (25 Nov): the
Lambda adapter behind AgentCore Gateway** for the product, so every tool call passes the gateway's
checks. The MCP server (FastMCP) is for development and the stage demo; the HTTP/OpenAPI service is
built only if the app ever needs its own API.

## Forge time: once per college, by our team

1. **Capture.** A team member logs in on their own account and visits every page we need; Forge
   records the portal's traffic (HAR), a screenshot of each page and the values on screen.
2. **Sanitise.** Before any model or shared disk sees it: drop the login request body, replace
   cookies, tokens and auth headers with placeholders, redact USN, name, DOB, phone and email,
   strip assets and third-party hosts. The raw HAR is deleted. (Our own ~100-line scrubber; no
   maintained Python one exists.)
3. **Engineer.** RAE as a library writes `connector.py` and `parsers.py` against the recorded
   responses; a second run in its docs mode writes `raw_openapi.json`.
4. **Review.** A person checks the code and every value against the screenshots; checked outputs
   become golden files.
5. **Verify** (CI): golden replay with the network off, contract validation with sanity rules, a
   mock-portal test that changes the data after generation, and a read-only allowlist check.
6. **Publish** a versioned connector.

### What we change in RAE

| RAE default | Our change |
| --- | --- |
| Prompt hardcodes every captured cookie and token into the client | Session is an argument, never code; a check fails any client containing a captured value |
| Manual capture keeps the login request with the password | Sanitise before anything is saved |
| Free-form client per site | The model fills our fixed `PortalConnector` interface |
| Client may send any request | Allowlist of read requests plus a code check |
| Prompt tells the model to beat bot detection (`httpcloak`) | Forbidden; a block is a stop |
| Verification is the model's own report | Deterministic replay and mock-portal tests |

## Run time: Android app login and keep-alive

1. The student taps **Connect portal**; the app opens the portal's own login page in an Android
   WebView. They fill in everything the portal asks themselves (USN, DOB, CAPTCHA, image code,
   parent's phone digits). We never automate the login or store the password.
2. When the dashboard appears, the cookies stay in the phone's secure storage and the fetch plan
   collects everything once. The app sends the pages to our server, which parses them with the
   verified parsers, keeps only the five tools' fields and discards the pages.
3. **Keep-alive:** one light page at the longest interval that keeps the login valid (set in the
   manifest from the measured idle timeout; hourly or longer if allowed). It runs on the phone only,
   from the same WebView cookies, device and network. WorkManager schedules it; if Android defers it
   while the phone is idle, a Firebase Cloud Messaging push from our server wakes the app on time.
   Our server never holds the student's cookies. Cost is effectively zero.
4. If the session ends anyway (the student or a parent logged in elsewhere: MSRIT reportedly allows
   one session per student), the next ping sees it and the app asks for one login the next time the
   student opens it. The briefing uses the last refresh and says how old it is.

Fallbacks: a browser extension reading the student's own browser session if MSRIT ever refuses
in-app logins; an official read-only feed from the college as the long-term route.

## MSRIT, the first target

Reported by open-source projects (not seen first-hand): Contineo (PHP, server-rendered HTML,
`parents.msrit.edu`), login by USN + DOB + invisible reCAPTCHA + image code + parent's phone
digits, one session per student, bot-like clients IP-banned, scripted logins refused since
14 Nov 2026 ("cannot be used from third-party apps"), no timetable in the portal, results on
`exam.msrit.edu`. From the team (25 Nov): the portal lists total classes for the semester,
attendance is updated daily with the percentage shown, and **a login inside an app works**.

## Rules

- No evasion: no CAPTCHA solving, WebView spoofing, fingerprint cloaking or IP rotation.
- No stored passwords; least data (only the five tools' fields); captures never committed.
- Read-only, at the longest ping interval the portal allows.
- Real students only after MSRIT agrees in writing (IT Act s.43 turns on the owner's permission);
  DPDP: under-18 students need verifiable parental consent.

## Build phases

1. **Contract, mock portal, MCP adapter** (~6 h). Done when Claude Code answers "what's my DBMS
   attendance" from the mock portal.
2. **Forge pipeline on the mock portal** (~8 h). Done when a fresh capture becomes a passing
   connector with no hand edits, and we know the cost of one forge.
3. **MSRIT through the app login** (~2 days). Done when attendance and CIE marks match the screen
   for one team member and the login stays alive 24 hours on pings alone.
4. **Android login, keep-alive and the Lambda adapter** (hack day). Done when a second team member
   connects in under two minutes and stays fresh for 24 hours with no second login.

## Tests before building

1. **Idle timeout** (team, today): log in on a phone, touch nothing, check at 30, 60 and 120
   minutes and overnight; each check resets the timer. This sets the ping interval.
2. **Ping reliability** (build day): leave test phones idle overnight; check the pings arrived on
   time on each team member's phone brand.

## Open

- Who asks MSRIT's CSE department for permission or an official read-only feed.
- Whether wHACKiest allows building before hack day (README says code lands on 1–2 Dec).
