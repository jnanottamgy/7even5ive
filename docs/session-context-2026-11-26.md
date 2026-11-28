# Session context — 2026-11-26: getting 7even5ive into the MSRIT portal

A complete record of one long working session: what was broken, what was built, what was proven
on a real phone, and what is still open. Written so a new session (or person) can pick up with no
other context.

---

## 1. Outcome in one paragraph

The 7even5ive ("75") Android app can now **log into the MSRIT parents portal
(`parents.msrit.edu`, Contineo) from an Android phone, stay logged in, and fetch every data page**
(dashboard, attendance, CIE marks, timetable, results). This was proven twice on a real
Galaxy Note10+ (Android 12, System WebView 157) with live logs read over adb. It works by making
the app's WebView look and behave like an iPhone's, end to end. The remaining work is the MSRIT
**connector** (parsing those pages into 75's data), not access. All code is on `kartik` and the
main branch `claude/busy-pasteur-lake3c` (both at `4c7667a`).

---

## 2. Repository and environment facts

- Repo: `jnanottamgy/7even5ive` (GitHub). Working branch `kartik`; main branch
  `claude/busy-pasteur-lake3c` (fast-forwarded to `kartik` at the end of the session).
- Layout: `android/` (Kotlin/Compose app, package `com.sevenfive.app`), `core/` (Python backend,
  `seventy5/`, tests in `core/tests`), `deploy/`, `docs/`.
- CI: `.github/workflows/android.yml` (build + unit tests) and `release-apk.yml` (builds
  `assembleDemo assembleDebug`, publishes to the `apk-latest` pre-release). Both trigger on pushes
  to `kartik` and the main branch under `android/**`.
- APK to install: **`app-demo.apk`** (optimised release-type build signed with the committed debug
  key; installs as an update over debug). Download:
  `https://github.com/jnanottamgy/7even5ive/releases/download/apk-latest/app-demo.apk`
- **Local build now works** on the dev PC (set up this session):
  - JDK: Temurin 17 at `C:\Program Files\Eclipse Adoptium\jdk-17.0.21.10002-hotspot`
    (`JAVA_HOME` set for the user).
  - Android SDK: `%LOCALAPPDATA%\Android\Sdk` (cmdline-tools latest, `platforms;android-36`,
    `build-tools;36.0.0`, `platform-tools`), licenses accepted; `ANDROID_HOME` set;
    `android/local.properties` has `sdk.dir`.
  - Java needs IPv4 forced or Gradle's wrapper download times out:
    `GRADLE_OPTS=-Djava.net.preferIPv4Stack=true`.
  - Build: `cd android && ./gradlew.bat assembleDemo` → `app/build/outputs/apk/demo/app-demo.apk`
    (~40–70 s warm).
  - Install/log over USB: `adb install -r …app-demo.apk`;
    `adb logcat -v time -s SevenFivePortal:I AndroidRuntime:E`.
- Python tests: `core\.venv\Scripts\python.exe -m pytest -q` (58 pass).
- Known local noise: `android/gradlew.bat` shows modified — **line endings only**; never commit it.

---

## 3. Chronology

### 3.1 Background question (no code)
Why a site accepts an iOS WebView but not an Android one: Android WebView self-identifies (`; wv`
and `Version/4.0` in the UA, `X-Requested-With`, `Sec-CH-UA` "Android WebView" brands, missing
`window.chrome`); WKWebView looks like Safari. Wrote `docs/webview-hardening.md` with the standard
hardening steps.

### 3.2 Repaired a broken working tree
The uncommitted work (bot library link, Files screen, deadline sync) had been written by an earlier
session **against stale copies** of files, silently deleting newer committed code:
`config.py` (~44 settings), `db.py` (notifications, devices, mark-done, jobs), `api.py` (devices,
settings, calls), `gateway.py`, `tools.py`, `demo.py`, `test_core.py`, `SevenFiveRoot.kt` (Portal
Check screen, transitions). Fixed by finding each file's original base commit and doing a 3-way
merge (`git merge-file`, after normalising CRLF) onto HEAD, keeping both sides. Core tests went
from 50 failing to **58 passing**. Committed as `651ab73`.

### 3.3 Android compile fixes (via CI, before local builds existed)
`FilesScreen.kt` also targeted the old UI: removed `TabScaffold(subtitle = …)` (`8e87376`) and
replaced the removed `ScreenPadding` with the scaffold's padding (`c4ebc8d`).

### 3.4 Portal access — the iterations
Each step below was driven by evidence (screenshots, then on-device logs).

| # | Change | Result |
|---|---|---|
| 1 | iPhone identity: Safari UA + `navigator.platform/vendor/maxTouchPoints`, no `window.chrome`; same-site + reCAPTCHA navigation allowed; `WebChromeClient` for alert/confirm | Got further, still bounced |
| 2 | Form POSTs sent by OkHttp with Safari headers (JS submit hook → bridge), response loaded back | Bounced: 303 back to login |
| 3 | Wait for `CookieManager.setCookie` callbacks before next load; diagnostics line | Still bounced |
| 4 | Submit hook moved to `window` (bubble) so page handlers run first; http→https action upgrade | Still bounced |
| 5 | **All same-site GETs** also through OkHttp with iPhone headers (`shouldInterceptRequest`) | Still bounced |
| 6 | Status panel, live checks, `PortalLog` → adb | **Diagnosis possible** |
| 7 | Own **cookie jar** (`PortalCookieJar`) — log showed the post-login GET sent *0 cookies* | Session cookie now sent, but portal **deleted** it on next GET |
| 8 | **Safari-style `Referer`** on page loads after a form post | **Logged in and stayed in** ✅ |
| 9 | Background sync WebView put on the same path; data-page test | **All 5 data pages fetched logged-in** ✅ |

---

## 4. How the MSRIT portal works (learned this session)

- Contineo on **Joomla 1.5** (`option=com_user`). Base `https://parents.msrit.edu/newparents/`,
  login posts to `index.php`. IPv4 only (`103.16.200.65`).
- Session cookie: `5bd4aa82278a9392700cda732bf3f9eb` (secure, host-only, path `/`, session).
  A second cookie `186ccbde26587d0190473e7c51934c1a` appears only when the portal **logs a
  session out** (both get deleted).
- **Login is two steps:**
  1. `form#login-form`, 17 fields in a real browser: `username`, `dd`, `mm`, `yyyy`, `passwd`
     (`putdate()` builds `YYYY-MM-DD`), `remember`, `cs_cap` (5-char image code), `option`,
     `task`, `return` ×2, a CSRF token (32-hex name, value `1`), `cs_n`, `cs_env`, a
     random-named anti-tamper field, `g-recaptcha-response`, `captcha-response`. Answer: **200**
     with a second page (~10 KB).
  2. Second form, 9 fields: `idType`, `enteredid`, `remember`, `option`, `task`, `username`,
     `passwd`, `return`, token. Answer: **303 → index.php** and the session cookie is
     **replaced** (= login success).
- **Detectors in the page:**
  - `cs_env`: flags `fiw` (flutter_inappwebview), `wv` (`; wv)` in UA), `hc` (HeadlessChrome),
    `wd` (webdriver), `wvb` (`userAgentData.brands` containing WebView). Must read `ok`.
  - Anti-tamper field (random name, e.g. `c5a32a964a9`): value `u<trusted taps>.<flags>`; flags
    `ua`/`wd`/`uad`/`val` if those are **own properties** of `navigator`/the field, `chr` if
    `window.chrome.loadTimes` isn't native, `fn` if `getOwnPropertyDescriptor` is patched. Hence
    all spoofing is done on `Navigator.prototype`, never on the instance.
  - Invisible **reCAPTCHA v3** (`grecaptcha.execute()` on load → `captcha-response`).
  - Image security code regenerates on every login-page fetch.
- **Session binding (why it took 8 tries):** the portal kills a session if requests on it don't
  look like one consistent browser. Specifically observed: (a) a request with no session cookie
  → new session → login page; (b) the first page load after login **without a `Referer`** →
  both cookies deleted (logout). Android WebView `loadUrl()` sends no Referer; Safari does.
- **Data pages** (all `index.php?option=com_studentdashboard&controller=studentdashboard&task=…`
  unless noted) — on-device result, logged in, 200:

  | Page | task | Size | Markers found |
  |---|---|---|---|
  | Dashboard | `dashboard` | 38 KB | 2 `.cn-attend` badges, **2 billboard `columns` arrays** (attendance % per subject + counts) |
  | Attendance | `attendencelist` (sic) | 23 KB | 2 tables, only 2 `.cn-attend-list` rows (per-class log likely needs a subject selected) |
  | CIE marks | `ciedetails` | 31 KB | 3 tables (marks may load via a further XHR — check) |
  | Timetable | `timetable` | 32 KB | 5 tables |
  | Results | `option=com_history&controller=history&task=getResult` | 41 KB | **SGPA ×4, CGPA** |

  See also `docs/msrit-connector-notes.md` (earlier reconnaissance).

---

## 5. What the app does now (architecture)

All in `android/app/src/main/java/com/sevenfive/app/portal/` unless noted.

- **`PortalEngine.kt`**
  - `PortalIdentity { IPHONE, ANDROID_CHROME }`, `PortalSettings.identity` (process-wide,
    default IPHONE).
  - `IOS_USER_AGENT` = Safari on iOS (`iPhone OS 18_6 … Version/26.0 … Safari/604.1`).
  - `hardenPortalWebView(identity)`: UA by identity, third-party cookies on, no
    `X-Requested-With`, doc-start scripts: hide `userAgentData` (prototype) and, for iPhone,
    `platform='iPhone'`, `vendor='Apple Computer, Inc.'`, `maxTouchPoints=5`, delete
    `window.chrome`.
- **`IosFormSubmitter.kt`** (the iPhone network path; attached with
  `WebView.sendPortalFormsAsIphone(host, report)` which returns the submitter or null)
  - JS hook (`INTERCEPT_JS`, portal origins only): on `window` submit (bubble, skipped if the page
    cancelled it) and patched `HTMLFormElement.prototype.submit`, serialises string fields of POST
    forms and calls the bridge. GET forms and file forms go through the WebView.
  - `post()` → OkHttp POST with Safari headers (`Accept`, `Accept-Language`, `Origin`, `Referer`,
    `Sec-Fetch-*`), cookies from the jar; redirect → `loadUrl(next)`, page →
    `loadDataWithBaseURL`.
  - `interceptGet()` (from `shouldInterceptRequest`): every same-site GET via OkHttp with Safari
    headers; main-frame redirects become a tiny `location.replace` page (WebResourceResponse
    can't carry 3xx); main-frame loads get `Referer = lastPage` (the page a form was sent from, or
    the last page shown).
  - Emits `SubmitReport` (status, redirect, ms, field names/empty, reCAPTCHA token presence,
    cookies sent/set as kept/replaced/new) — names only, never values.
- **`PortalCookieJar.kt`**: OkHttp `CookieJar`; seeds once from `CookieManager`, applies
  Set-Cookie immediately (fixes the async `setCookie` race), mirrors every cookie back to
  `CookieManager`, logs domain/path/flags.
- **`PortalLog.kt`**: ring buffer (600 lines) + logcat tag **`SevenFivePortal`**; Copy / Share /
  Clear on the test screen. Logs host+path, status, timing, cookie *names*, field *names*, hook
  decisions, page events, page console, check changes. Never values or query strings.
- **Wired into:** `ui/screens/PortalCheckScreen.kt` (test), `ui/screens/PortalScreen.kt` (real
  login), `portal/ForegroundSync.kt` (background sync WebView).
- **Portal test screen** (`PortalCheckScreen.kt`): verdict tick (green past login / red sent back
  or error / yellow waiting); live checks every 2 s (UA, userAgentData, platform, vendor, no
  window.chrome, webdriver, no flutter bridge, `cs_env`=ok, anti-tamper flags + tap count,
  reCAPTCHA script/token, hook installed, pages fetched as iPhone, login sent, the 7 required
  login fields present and filled, session cookie, still logged in); rows for browser toggle,
  page, sent/fields/field names/cookies, portal message; **"Test data pages"** button (fetches
  the 5 pages in-session, reports structure only); log buttons.
- `docs/webview-hardening.md` — general Android WebView hardening notes.

---

## 6. Commits this session (on `kartik`, now also main)

```
651ab73 Add the bot library link and Files screen, merged onto current code
8e87376 Files screen: drop the TabScaffold subtitle the redesign removed
c4ebc8d Files screen: use the scaffold's padding, not the removed ScreenPadding
fa4a8a9 Portal WebView: look like an iPhone, and let later steps through
7d2aca1 Portal: send the portal's form POSTs with iPhone headers
309c2ac Portal iPhone submit: wait for cookies before loading, and show the answer
e794a42 Restore gradlew.bat line endings
0a08e26 Portal test: show why a login bounces
275d85f Portal test: a status panel with a pass/fail tick
6e0a4db Portal iPhone mode: fetch the portal's pages with iPhone headers too
e414cef Portal test: live checks and a step-by-step log
97bb885 Portal iPhone path: own cookie jar and a Safari-style Referer
92a4130 Background sync on the iPhone path; data-page test on the portal test
4c7667a Ignore the local APK copy
```

---

## 7. Open work (in priority order)

1. **MSRIT connector** (PortMax side: `portmax.connector("msrit")` fetch plan + parsers). Needs
   real page HTML to write parsers against — the user was asked whether to capture the five
   pages to the PC (local only, never uploaded); **not yet answered**.
   - Attendance %: dashboard billboard `columns` arrays (subject codes like `24CS51`).
   - Results: SGPA/CGPA from text.
   - Attendance detail: `attendencelist` returned only 2 log rows — find the per-subject request.
   - CIE marks: check whether values are in the HTML or need the per-subject XHR.
2. **Verify background sync end-to-end** — code is on the iPhone path (`ForegroundSync`) but can't
   run until the connector exists.
3. **Session lifetime** — unknown; re-login needs the student (image code + reCAPTCHA), so 75 must
   prompt for login when the session ends. Session cookie is non-persistent.
4. **Hardening gaps**: TLS fingerprint is OkHttp's, not Safari's; non-form XHR **POSTs** from the
   page still go out natively; reCAPTCHA logs `requestStorageAccess: Permission denied` (harmless
   so far).
5. **Policy risk**: the portal deliberately blocks third-party apps; 75 passes by posing as an
   iPhone. Fine for the developer's own account by their choice; before other students, consider
   MSRIT/Contineo permission or an official export — detection can change at any time.

---

## 8. Debug runbook

1. Phone: Developer options → USB debugging on → plug in → Allow (Samsung driver already present;
   if only "Galaxy Note10+ / MTP" shows in Device Manager, debugging isn't on).
2. `adb devices` should list `RF8M81BS9MY  device` (SM-N975F).
3. Build + install: see §2. Launch: `adb shell am start -n com.sevenfive.app/.MainActivity`.
4. Stream: `adb logcat -v time -T 1 -s SevenFivePortal:I AndroidRuntime:E > portal.log`.
5. In the app: Settings → Portal test → Reload → log in (both steps) → panel's
   "Test data pages". Healthy log signature:
   - `POST … fields(17)` → `POST answer 200 … page`
   - `POST … fields(9)` → `jar: set 5bd4… ` → `POST answer 303 … replaced`
   - `GET PAGE headers: … Referer=…/index.php, cookies=1` → `GET PAGE …index.php -> 303` (no
     deletions) → `-> 200`
   - `js: data {"page":…,"status":200,…,"login":false,…}` ×5 → `js: data test done`
   - Failure signatures: `cookies-sent 0 (NONE)` after login (jar problem); `jar: deleted 5bd4…`
     + `186cc…` (portal logged the session out — find the header that differs); `FAIL` lines in
     `checks:` (a detector sees the WebView).

---

## 9. Privacy rules followed (keep them)

- Logs and UI show names, counts, statuses, hosts and paths only — never field values, cookie
  values, query strings, marks or attendance figures.
- The user's credentials were never entered by the assistant; the user logged in on the phone.
- Page HTML with personal data is not captured without the user's explicit yes (pending).
