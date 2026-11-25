# 7even5ive for Android

The prototype's only app (decisions 18, 19, 50). Kotlin + Jetpack Compose, minSdk 26.
The full brief is [`docs/android.md`](../docs/android.md).

| Tab | Shows | Actions |
|---|---|---|
| **This week** | Approvals waiting for a tap, then deadlines, exams and events due in 7 days, soonest first; cards nobody could read, muted | **Approve** · Remind me (1 day, 3 hours, 1 hour before) |
| **Attendance** | Each subject worst first: percent, classes, a bar with the 75% tick, and PortMax's exact sentence | Connect portal · Refresh · Log in again |
| **Materials** | Files by subject (5 subjects + Miscellaneous) | Filter by subject |
| **Inbox** | Opportunities from mail, best match first, and "N spam or fake mails filtered out" | |
| **Reminders** | Pending reminders, soonest first | Cancel |
| Portal login | The college portal's own page in a WebView | The student logs in themselves |

Every card shows a small `via bot / classroom / jev / jev+llm / llm` badge: what decided it.

## Run it

1. Start the three backend terminals from [`docs/android.md`](../docs/android.md) section 5
   (core on 8000 with `HOST=0.0.0.0`, PortMax API on 8002, the mock portal on 8765).
2. Open `android/` in Android Studio and run the `app` configuration, or:
   ```bash
   cd android && ./gradlew installDebug
   ```
   Or download `7even5ive-debug-apk` from the latest **Android** workflow run on GitHub.
3. **Emulator:** works as is (`10.0.2.2`). **Real phone:** same Wi-Fi as the laptop; tap the
   gear → type the laptop's IPv4 → **Fill in** → **Save and reconnect**.
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

- Push notifications for reminders (FCM): needs the backend's token-registration endpoint.
- Opening a material: the file stays with the WhatsApp bot until fetch-by-id exists.
- Refreshing the portal while the app is closed.

## Tests

```bash
cd android && ./gradlew testDebugUnitTest
```

They parse a real `/api/cards` response from the demo, check the time formatting, and check the
API client against a mock server (bearer token on every call, `{"args": ...}` for tools, the
gateway's refusal text passed through).
