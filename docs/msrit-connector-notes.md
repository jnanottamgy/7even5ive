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

## Why this needs a HAR capture, not curl guessing

The dashboard renders per-subject attendance/marks into **UIKit modals via XHR**. Plain curl of
the task endpoints returns the page shell and some tables, but the per-subject figures and their
parameters (subject id, semester) are populated by JavaScript. The PortMax forge is built for
exactly this: `portmax forge capture` records the real XHRs while a student clicks through, then
`sanitize → engineer → verify` builds the connector from that recording.

## Next steps

1. Run `portmax forge capture` against `parents.msrit.edu` (student logs in, opens attendance
   and internal marks for a couple of courses, timetable, results), producing a sanitized HAR.
2. Build `connectors/msrit/` (manifest, fetch_plan, parsers) from the capture; model on
   `connectors/mockcollege/` (it was patterned on Contineo).
3. The connector's home is the **PortMax source repo** (`../portmax/src/portmax/connectors/`),
   not this repo — `core/.build/portmax` is a gitignored build copy.
4. App wiring: set `college = msrit` and decouple the portal URL from the core/PortMax host so
   the WebView opens `parents.msrit.edu` while uploads still go to the cloud.
