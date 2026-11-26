# MSRIT fixtures — what to capture

The `msrit` connector's parsers (`../parsers.py`) are **provisional**: written from
`docs/msrit-connector-notes.md` before any real logged-in page was seen. To finish and verify
them (`portmax forge verify`), drop one **sanitised** HTML capture of each page here, named by
step, and a matching `index.json` (see `../../mockcollege/fixtures/index.json` for the shape).

Capture on a real logged-in phone session — never by probing the portal from a server. Either
save the page HTML yourself from a logged-in session, or use the planned **Settings → Test a
college portal → Export page HTML** helper (writes these files with the profile fields redacted).
Either way, eyeball each file before committing.

| File | Page (step) | Path fetched |
|---|---|---|
| `dashboard-0.html` | `dashboard` | `/newparents/index.php?option=com_studentdashboard&controller=studentdashboard&task=dashboard` |
| `attendance-0.html` | `attendance` | `…&task=attendencelist` |
| `timetable-0.html` | `timetable` | `…&task=timetable` |
| `results-0.html` | `results` | `/newparents/index.php?option=com_history&controller=history&task=getResult` |

## Must be scrubbed before committing (fixtures live in git)

Student name, USN, date of birth, parent/guardian phone, photo. The attendance/marks **numbers and
subject codes stay** — they are what the parsers are tested against. Replace the USN consistently
(e.g. `1XX00XX000`) so `parse_profile` still has something to match.

## Still open (see parsers.py TODOs)

- **Subject names** — not in the dashboard array; find where `attendencelist` carries them.
- **attendencelist grouping** — how per-subject Present/Absent blocks are delimited and labelled.
- **Timetable** — period headers and cell layout are unconfirmed; `parse_timetable` raises until seen.
- **CIE marks** — load via an uncaptured XHR, so `get_marks` is not in the manifest yet. To add it,
  capture the request a subject's internal-marks view fires (DevTools → Network → Copy as cURL).
