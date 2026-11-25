# PortMax

**Status: being built (25 Nov 2026), code in [`portmax/`](../portmax).** The live, commented
version of this plan is the "PortMax: Build Plan" doc (named Portal Forge until 25 Nov); this file
is its copy in the repository. Where they disagree, the newer one wins and both get fixed.

## Conclusion

PortMax is a factory that turns a college portal into **five read-only tools** with the same
shape for every college. We forge each college's connector once, with
[reverse-api-engineer](https://github.com/kalil0321/reverse-api-engineer) (RAE) used as a pinned
library under our own prompts, safety rules and tests.

At run time the student **logs in once inside our Android app** (the portal's own page in a
WebView, CAPTCHA and all), and the app **keeps that login alive** by requesting one light portal
page at the longest interval the portal allows. Every few hours a ping runs the whole plan instead,
so attendance is never more than a few hours old. Data is saved with its time, so the 7 AM briefing never waits on a login. The output is a fixed contract,
so the work does not wait on the final architecture.

## The five tools

| Tool | Returns (one row per item) | Used for |
| --- | --- | --- |
| `get_attendance` | subject code, name, attended, held, percentage, as-of | Bunk math, the attendance warning |
| `get_timetable` | day, start, end, subject code, room | Briefing, "can I skip tomorrow" |
| `get_marks` | subject code, component (CIE-1, CIE-2, quiz, lab), scored, maximum | Target CGPA |
| `get_results` | semester, subject, credits, grade, grade points, SGPA, CGPA | Target CGPA |
| `get_profile` | USN, branch, semester, section (no name, DOB or photo) | Matching subjects |

**Bunk math is a sixth tool, computed on our side:** `get_attendance_plan` reads the saved
attendance (and the timetable, where the portal has one) and returns, per subject and worst first,
how many classes the student can miss and stay at the college's minimum, or how many they must
attend in a row to get back, the dates of their next classes, the outlook for the rest of the
semester, and one ready sentence no model writes. It never fetches a page, so every college gets it
the day its attendance tool works. The minimum is per college (`attendance_minimum_percent` in the
manifest, 75 by default). The math is in [`brain.md`](brain.md#4-attendance-and-bunk-math).

A connector is a **fetch plan** (the read-only pages to request, in order, and what each step reads
from the one before) plus **parsers** (pure functions, HTML or JSON to our models). Every result
carries `fetched_at` and the connector version. Failures are named: `SessionExpired`,
`PortalUnavailable`, `PortalChanged`, `NotSupported`.

Per college, the forge outputs `manifest.yaml`, `fetch_plan.json` (data, so the same file runs in
the Android WebView and on a server), `parsers.py`, `raw_openapi.json` (reference only), `fixtures/`
and `golden/`. Three small adapters can wrap any connector. **Chosen (25 Nov): the
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
3. **Engineer.** RAE as a library writes `fetch_plan.json` and `parsers.py` against the recorded
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

## Build status

Built on 25 Nov in [`portmax/`](../portmax): Python 3.12, ruff and strict mypy clean, 95 tests
passing, all against a mock college portal (`portmax mock serve`), never a real one. Phase 1 is
done: with the repository's `.mcp.json`, Claude Code answers "what's my DBMS attendance?" from the
mock, and "can I skip DBMS?" from the same data. Phase 2 is done except one live run of the engineer with a model (needs an API key or
Bedrock access).

| Part | Status | Code |
| --- | --- | --- |
| Contract: five tools, sanity rules, named errors | Built | `contract.py`, `errors.py` |
| Mock portal: two-step login with CAPTCHA, one session per student, idle timeout, Referer and User-Agent checks | Built | `mock_portal/` |
| Fetch plan (GET-only data) and Python executor | Built | `plan.py`, `executor.py` |
| Mock connector, fixtures, golden answers | Built; replays offline | `connectors/mockcollege/` |
| Store, ingest (pages parsed, then dropped), the five tools | Built | `store.py`, `ingest.py`, `tools.py` |
| Bunk math (`get_attendance_plan`): exact at the minimum, capped at the classes left, next classes in India time, semester outlook, worst first | Built; served by the Lambda, the MCP server and the gateway schema | `bunk.py`, `tools.py` |
| Lambda adapter for AgentCore Gateway, tool schema | Built; check the event shape against AWS docs before deploying | `adapters/lambda_handler.py`, `adapters/gateway.py` |
| MCP server (development, demo) | Built; Claude Code connects through `.mcp.json` | `adapters/mcp_server.py` |
| Phone API: `GET /v1/connectors/{college}`, `GET /v1/runner.js`, `POST /v1/pages` | Built; dev sign-in tokens until real sign-in | `api.py` |
| JS runner for the WebView | Built; real-Chromium tests: reads every tool, keeps the login past the idle timeout, refuses unsafe plans | `runner/portmax-runner.js` |
| Wake-ups for overdue pings | Built with a logging stand-in for Firebase | `wakeups.py` |
| Forge: capture, sanitise, fixtures, verify, accept, publish | Built; end to end on the mock in a real browser; verify catches hardcoded answers, impure parsers, leaked cookies | `forge/` |
| Forge: engineer (RAE with our prompt) | Wired; one live run with a model still to do | `forge/engineer.py` |
| MSRIT connector | Waits for the idle-timeout test and MSRIT's permission | |
| Android app: WebView login, WorkManager keep-alive, push wake-up | To build | |

## Run time: Android app login and keep-alive

1. The student taps **Connect portal**; the app opens the portal's own login page in an Android
   WebView. They fill in everything the portal asks themselves (USN, DOB, CAPTCHA, image code,
   parent's phone digits). We never automate the login or store the password.
2. When the dashboard appears, the cookies stay in the phone's secure storage and the fetch plan
   collects everything once. The app sends the pages to our server, which parses them with the
   verified parsers, keeps only the five tools' fields and discards the pages.
3. **Keep-alive:** one light page at the longest interval that keeps the login valid: the measured
   idle timeout minus a fifth (at least two minutes). For MSRIT the timeout is between 45 and 61
   minutes (measured 25 Nov), so the app pings **every 30 minutes**, 15 minutes inside the
   shortest timeout seen. Every
   `refresh_minutes` (3 hours by default) the ping runs the whole plan instead. It runs on the phone
   only, from the same WebView cookies, device and network. WorkManager schedules it, running the
   ping in a headless WebView with the login's own cookies and User-Agent; if Android defers it
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
On 25 Nov the login worked in Instagram's in-app browser (a WebView), while an automated
browser (Playwright, the forge's `capture`) was refused: "This portal cannot be used from
third-party apps." The block is aimed at automation, not at in-app logins. So the connector is
built from a **hand-recorded** visit instead: a team member logs in in normal Chrome with
DevTools open, saves the Network tab as a HAR, and runs `portmax forge sanitize --har ...`; the
rest of the pipeline is unchanged. No disguising of the automated browser, ever (decision 22).

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
4. **Android login, keep-alive and the Lambda adapter**. Done when a second team member
   connects in under two minutes and stays fresh for 24 hours with no second login.

## Tests before building

1. **Idle timeout: done 25 Nov (Zaid).** Login 14:45, alive at 15:15 (30 min idle), dead at
   16:16 (61 min idle); login 16:21, alive at 17:06 (45 min idle). Timeout is between 45 and 61
   minutes, so the ping runs every 30 minutes. Still to test: the one-session rule (a second
   login elsewhere), closing the browser, and whether a session pinged all night survives (a
   fixed maximum session length would show up only there).
2. **Ping reliability** (build day): leave test phones idle overnight; check the pings arrived on
   time on each team member's phone brand.

## Open

- Who asks MSRIT's CSE department for permission or an official read-only feed.
