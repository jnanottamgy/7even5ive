# Can the app log in to MSRIT? — the WebView test and its result

**Short answer: no, not without MSRIT's cooperation.** MSRIT's portal refuses any browser
that isn't real Chrome or Safari, and that includes the app's own WebView. We confirmed this by
testing, on 26 Nov 2026. This doc is the full context for the team.

## The question we set out to answer

Decision 19 says the student logs in to the portal **inside our Android app**, in a WebView.
That only works if MSRIT lets an in-app browser reach the login at all. Two separate things
could get blocked, and it mattered which:

1. **Automation** — a browser driven by code (Playwright) announces itself as automated.
2. **In-app browser** — a WebView is a normal browser embedded in an app; it is *not* automated.

The team's point (correct, and worth testing): the first MSRIT block we hit was with Playwright,
which waves an "I'm automated" flag. A plain WebView does **not** wave that flag, so maybe MSRIT
was only blocking automation, and a real in-app WebView would get through. The only way to know
was to build it and try.

## Test 1 — Forge capture (Playwright), 25 Nov

`portmax forge capture` opens a Playwright-driven Chromium to record the portal. Pointed at
`https://parents.msrit.edu/`, MSRIT refused it: **"Login not allowed. This portal cannot be used
from third-party apps."** Expected for automation, but it left the WebView question open.

## Test 2 — the app's WebView, 26 Nov

Built into the app: **Settings → Test a college portal** (`PortalCheckScreen.kt`). It opens a
portal address in a **stock Android WebView**, configured exactly like the real portal-login
screen and otherwise left as Android ships it:

- JavaScript, DOM storage, cookies, and third-party cookies on (as a normal browser).
- **User-Agent left untouched** — no disguise, no pretending to be Chrome.
- **Nothing injected, nothing read, nothing uploaded.** No runner, no JavascriptInterface. The
  student types the credentials and CAPTCHA themselves. The background refresh never uses it.
- Navigation locked to the portal's own site; the top bar shows the current host + path.

**Result:** the moment the page loaded, MSRIT redirected to `parents.msrit.edu/newparents/` and
served **"This portal cannot be used from third-party apps. Please open it in Chrome or Safari."**
— before the login form even appeared. (Screenshot in the team chat, 26 Nov ~09:28.)

## What this tells us

- A WebView is indeed different from Playwright — it doesn't wave the automation flag — so the
  team's reasoning was sound. But a WebView still identifies itself honestly: its User-Agent
  contains a `wv` marker and the app's identity, so a server can tell it is an in-app browser and
  not Chrome.
- **MSRIT's block is broader than automation: it is a Chrome/Safari allowlist.** Anything else,
  automated or not, is turned away at the door.
- Therefore the in-app login of decision 19 **cannot work against MSRIT as it stands.** This is a
  policy MSRIT enforces on purpose (their portal has said "cannot be used from third-party apps"
  since 14 Nov 2026), not a bug we can route around.

## What we will not do, and why

Getting past the block would mean **disguising the app as Chrome** (faking the User-Agent, hiding
that it is a WebView). We did not do this, and should not:

- It is **circumventing an access control the owner set deliberately.**
- **Decision 22** already forbids it: *"No evasion: no CAPTCHA solving, WebView spoofing,
  fingerprint cloaking or IP rotation."*
- **IT Act s.43** turns on the owner's permission; accessing their system in a way they have
  explicitly refused is the exposure that section is about. The risk lands on the student whose
  account is used — and MSRIT IP-bans bot-like clients, so it could break mid-demo.
- It undercuts the whole "use MCP responsibly" pitch.

## Legitimate alternatives (the student uses real Chrome, which MSRIT allows)

The clean split: the **student** reaches the portal in real Chrome (allowed), then hands their
own data to the app. The app never logs in, never fetches, never disguises itself.

| Option | How | Real data by demo day? |
|---|---|---|
| **Share a screenshot** | "Open MSRIT in Chrome" button → student screenshots their attendance page → shares it to 7even5ive → app reads the numbers → PortMax's bunk math | Yes (~1 day to build) |
| **Share a saved page/PDF** | Same, but a saved/printed page: more exact than a photo | Yes (~1 day) |
| **Type it in** | A small form: attended/held per subject | Yes, by hand (~2–3 h) |
| **Official feed** | Ask MSRIT (CSE dept / vendor) for a read-only export or API | Not by demo day; proper long-term answer |
| **Attendance mails** | If MSRIT emails shortage warnings, the mail filter can read them | Partial |

Reading a screenshot accurately wants either an Anthropic/Bedrock key (vision) or on-phone text
recognition (ML Kit, free, offline) — a decision if we go this way.

## On the branch (`claude/amazing-clarke-apeyif`, commit `de7e7d9`)

The WebView test is committed and CI-green (unit tests + APK + lint):

- `android/app/src/main/java/com/sevenfive/app/portal/PortalCheck.kt` — address + same-site rules
- `android/app/src/main/java/com/sevenfive/app/ui/screens/PortalCheckScreen.kt` — the test screen
- `android/app/src/test/java/com/sevenfive/app/PortalCheckTest.kt` — 4 unit tests
- wiring in `SettingsScreen.kt`, `SevenFiveRoot.kt`, `AppViewModel.kt`

The real portal-login flow (`PortalScreen.kt`, `PortalEngine.kt`, the runner) is unchanged and
still works end to end against the **mock** portal — which is what the demo runs on (live on AWS).

## Recommendation

1. **Demo on the mock portal**, framed honestly: *"MSRIT blocks third-party apps (verified
   26 Nov), so we built PortMax against a faithful mock and are asking MSRIT for an official
   read-only feed."*
2. If we want **real MSRIT numbers on stage**, build the **screenshot/paste** path — student
   relays their own data, nothing touches the portal.
3. **Ask MSRIT** for permission or an official feed; keep the in-app login ready for when they
   say yes.
4. **Decision 22 / `docs/portmax.md`**: record that the in-app login is blocked today, so the
   docs match reality.
