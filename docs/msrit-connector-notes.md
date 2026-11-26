# MSRIT (Contineo) connector — reconnaissance notes

Status: investigation on branch `kartik`. No connector shipped yet. This records what the
real `parents.msrit.edu` portal looks like so the `msrit` connector can be built against it.

## Portal

- Software: **Contineo** (Joomla-based college ERP). Vendor string in page: `contineoReg`.
- Base URL: `https://parents.msrit.edu/newparents`
- Login path: `/index.php`
- Login page markers: `form#login-form`, `.cn-landing-login`, "Forgot Password".
- Logged-in: no login form; USN present; top menu lists `com_studentdashboard`, `com_fee`,
  `com_history`, `com_placement`, `com_coursefeedback`, `com_bvbsims`.
- Second CAPTCHA: an **invisible Google reCAPTCHA v3** (site key `6LcFIuYq…`,
  `grecaptcha.execute()`) in addition to the embedded image "security code". The image code
  regenerates on **every** page fetch, so any reload of the login page desyncs a typed code.

## Two findings that shape the connector

1. **WebView User-Agent is sniffed.** A UA containing the `wv` token gets
   "This portal cannot be used from third-party apps." A plain Chrome UA passes. (Fixed in the
   app: `configureForPortal` now sets a clean Chrome UA.)
2. **The session appears bound to the User-Agent.** The same fresh cookie returns the dashboard
   under a desktop Chrome UA but the login page under an Android-mobile UA. The app's WebView
   uses one fixed UA for both login and fetching, so it is self-consistent — but only a
   desktop-UA session has been verified end-to-end so far. An on-device login must confirm a
   mobile-UA session authenticates fully. No IP binding was observed (same-IP replay worked).

## Real data endpoints (return HTML with just the session cookie)

All under `index.php?option=com_studentdashboard&controller=studentdashboard&task=…` unless noted:

| Tool            | task / option                               | Notes |
|-----------------|---------------------------------------------|-------|
| get_attendance  | `task=attendencelist` (Contineo spelling)   | per-class log tables `.cn-attend-list1/2`; summary badges `.cn-attend` |
| get_marks       | `task=ciedetails`                           | CIE / internal assessment |
| get_timetable   | `task=timetable`                            | |
| get_results     | `com_history&controller=history&task=getResult` | SGPA / CGPA |
| get_profile     | `task=dashboard` (full index)               | USN, branch, credits |

Observed subtasks also present: `getSubjects`, `calenderdisplay`, `seating`, `examfee`,
`studFee`, `placementeligibility`, `feedback`.

## Where the data actually lives (from a real logged-in capture)

The dashboard embeds its charts' data as inline **billboard.js** arrays, so most of it is
parseable from the fetched HTML without replaying XHRs:

- **Attendance** (`task=dashboard`): two `columns` arrays of `["<code>", <n>]` pairs, keyed by
  year-prefixed subject codes like `24CS51`, `24CSL56`, `24CSAEC510`. One array is the
  attendance **percentage** per subject; the other is a per-subject count (attended or
  absent — needs confirming against the detail page). Subject *names* and exact attended/held
  counts are not in this array.
- **Results** (`com_history&task=getResult`): SGPA per semester and CGPA parse directly from
  text (`SGPA 8.2`, `CGPA 8.5`, …).
- **Attendance detail** (`task=attendencelist`): per-class log tables `.cn-attend-list1/2`
  (Sl/Date/Time/Status) — counting Present/Absent rows gives exact attended/held per subject.
- **Marks** (`task=ciedetails`): `var chartData = []` is **empty** in the page; the CIE marks
  load per-subject via a further XHR. This is the one piece that still needs an XHR capture
  (the request + params the page fires when a subject's internal marks are opened).

## Next steps

1. Attendance (%) and results can be built now from the captured pages. Confirm the attended/
   held counts from `attendencelist`, and the meaning of the dashboard's second count array.
2. Capture the **marks XHR**: in the browser, open a subject's internal assessment with DevTools
   Network open and "Copy as cURL" the request that returns the marks (or run a forge HAR
   capture). That gives the endpoint + params for `get_marks`.
3. Build `connectors/msrit/` (manifest, fetch_plan, parsers) modelled on `connectors/mockcollege/`
   (it was patterned on Contineo); add fixtures + golden and run `portmax forge verify`.
4. The connector's home is the **PortMax source repo** (`../portmax/src/portmax/connectors/`),
   not this repo — `core/.build/portmax` is a gitignored build copy.
5. App wiring: set `college = msrit` and decouple the portal URL from the core/PortMax host so
   the WebView opens `parents.msrit.edu` while uploads still go to the cloud.
