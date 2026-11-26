# 7even5ive for Android

The prototype's only app (decisions 18, 19, 50). Kotlin + Jetpack Compose, minSdk 26.
The full brief is [`docs/android.md`](../docs/android.md).

| Tab | Shows | Actions |
|---|---|---|
| **This week** | Ask your semester; three numbers at a glance; today's classes; approvals waiting for a tap; deadlines, exams and events due in 7 days, soonest first; AI activity; cards nobody could read, muted | **Approve** · Remind me (1 day, 3 hours, 1 hour before) · Add to the phone's calendar |
| **Attendance** | Each subject worst first: a ring with the 75% tick, classes, and PortMax's exact sentence; tiles for Planner, Timetable and Grades | Connect portal · Refresh · Log in again |
| **Materials** | Files by subject (5 subjects + Miscellaneous) | Filter by subject · open the file in the phone's app |
| **Inbox** | Opportunities from mail, best match first, and "N spam or fake mails filtered out" | |
| **Reminders** | Pending reminders, soonest first | Cancel |
| Portal login | The college portal's own page in a WebView | The student logs in themselves |
| Ask | Questions answered from the student's data through the gateway (`POST /api/ask`): Claude with a key on the server, offline answers without | |
| Search | Everything at once: due, materials, inbox, reminders, subjects | |
| AI activity | Every gateway decision: allowed, held for a tap, refused | |
| Bunk planner · Timetable · Grades | Skip a day and see each subject move; the week's classes; internal marks and results | |
| Share to 7even5ive | Android's share sheet: a message or a file from any app (`POST /api/share`) | Say what it is, or let 7even5ive read it |
| Widget | What's due this week and the lowest attendance, on the home screen | |
| Notifications | Reminders ring on the phone at the chosen time; an optional 8 am digest | Settings → Notifications |

Every card shows a small `via bot / classroom / jev / jev+llm / llm` badge: what decided it.

## Run it

**Online (no laptop):** once the online server is up ([`docs/online.md`](../docs/online.md))
and its address is in `android/gradle.properties` (`sevenfive.defaultServer`), just install
the APK: it opens straight onto the server.

**Laptop:**

1. On the laptop, double-click **`start-demo.bat`** in the repository root (macOS/Linux:
   `./start-demo.sh`). One window runs the core, PortMax and the mock portal, with the portal
   address set and kept current. The separate terminals are in
   [`docs/android.md`](../docs/android.md) section 5.
2. Open `android/` in Android Studio and run the `app` configuration, or:
   ```bash
   cd android && ./gradlew installDebug
   ```
   Or download **`7even5ive-apk`** (`app-demo.apk`) from the latest **Android** workflow run
   on GitHub. Use that one on a phone: it's the optimised build, so the glass and animations run
   smoothly. (`7even5ive-debug-apk` is the unoptimised debug build, for development only.)
3. **Real phone:** on the laptop's Wi-Fi, or the laptop on the phone's hotspot. The app finds
   the laptop by itself within a few seconds ("Found the laptop at …"). If it doesn't: gear →
   **Find the laptop**, or type the laptop's IPv4. **Emulator:** works as is (`10.0.2.2`).
4. Attendance → **Connect portal** → log in as the invented student: USN `1MC24CS042`, date of
   birth 14-08-2005, CAPTCHA `PM42X`, then parent's phone last digits `2345`. The app sees the
   logged-in marker, fetches the pages and attendance appears.

## How it works

```
MainActivity ── while STARTED ──> CardsRepository.pollForever()   GET /api/cards every 7 s
             └─ while STARTED ──> ForegroundSync                  hidden WebView, portal refresh
Screens ── AppViewModel ──> CoreApi      /api/cards · /api/approve · /api/tools/{tool}   :8000
                        └─> PortMaxApi   /v1/connectors/{college} · /v1/runner.js · /v1/pages   :8002
PortalScreen / ForegroundSync ──WebView──> the college portal (student's own session)   :8765
```

- **One poll, every screen.** `GET /api/cards` feeds all tabs; the last good answer stays on
  screen with a banner if the laptop goes away.
- **Portal login** (`portal/`): the WebView opens `<portal><login_path>` with JavaScript and
  cookies on and the real User-Agent. After each page load the app injects `runner.js` and asks
  `PortMaxRunner.isLoggedIn(markers)`. Once true, it starts `PortMaxRunner.run(settings)` with the
  connector settings unchanged; the Promise posts back through a `@JavascriptInterface` with a
  fresh nonce per run, then the pages go to `POST /v1/pages`. The app never fills in or submits
  the login form, and navigation is locked to the portal's origin.
- **Keeping it fresh** (`ForegroundSync`): while the app is open, a full run every
  `refresh_minutes` (and on open, unless one ran in the last 10 minutes) and one keep-alive page
  every `keepalive_minutes`. It starts from the portal's login page, which never touches the
  session, so every GET carries the portal's own Referer. A lapsed session (`session_expired` or
  409) sets "Log in to your portal again" for the next time the student looks: never a
  notification. Background refresh (app closed) is left out, as the brief allows.
- **Approvals** only run from the Approve button. An approved card stays as "Approved"; tapping it
  again shows the gateway's own "approval already used".
- **Privacy:** no logging interceptor and no `Log` calls; the token is a build constant
  (`gradle.properties`), not stored on disk; portal cookies stay in the WebView's cookie store.
  Settings → "Log out of portal on this phone" clears them.
- **Debug vs release:** debug builds allow cleartext HTTP (the laptop's IP isn't known at build
  time); release builds are HTTPS-only for the deployed `ApiUrl`.

## Not built yet

- Refreshing the portal while the app is closed.
- Server-sent push (FCM): reminders ring from alarms the phone sets from its last cards, so a
  reminder set from another device shows up once this phone has polled.

## Tests

```bash
cd android && ./gradlew testDebugUnitTest
```

They parse a real `/api/cards` response from the demo, check the time formatting, and check the
API client against a mock server (bearer token on every call, `{"args": ...}` for tools, the
gateway's refusal text passed through).

The portal glue is checked end to end against the real servers (the three terminals running),
with Chromium standing in for the WebView. It reads the start script out of `PortalEngine.kt`, so
it runs the app's own JavaScript: login detection, a full run, the upload, a keep-alive started
from the login page, and `session_expired` once the cookies are gone.

```bash
node android/e2e/portal-e2e.js
```

To check the phone's case (the portal reached at a LAN address, not 127.0.0.1), start
PortMax with `PORTMAX_PORTAL_ORIGINS=mockcollege=http://<ip>:8765` and run it with `HOST=<ip>`.
