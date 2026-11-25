"""The mock portal's web app: PHP-style URLs, server-rendered HTML, real session rules."""

from __future__ import annotations

import random
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from portmax.contract import Weekday
from portmax.mock_portal.data import PERIODS, Course, MockState, Student, default_state

SESSION_COOKIE = "PORTALSESSID"
PRELOGIN_COOKIE = "PMPRE"
CAPTCHA_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

DASHBOARD = "index.php?option=com_studentdashboard&task=dashboard"
TIMETABLE = "index.php?option=com_timetable&task=view"
RESULTS = "index.php?option=com_results&task=view"
FEES = "index.php?option=com_fees&task=view"
LOGOUT = "index.php?option=com_users&task=logout"


@dataclass
class PortalConfig:
    idle_timeout_seconds: float = 20 * 60
    max_lifetime_seconds: float | None = None
    one_session_per_student: bool = True
    require_referer: bool = True  # a logged-in request with no portal Referer ends the session
    bind_user_agent: bool = True  # a request from a different User-Agent ends the session
    captcha: Literal["random", "fixed"] = "random"
    fixed_captcha: str = "PM42X"
    clock: Callable[[], float] = time.monotonic


@dataclass
class Session:
    usn: str
    user_agent: str
    created: float
    last_seen: float


@dataclass
class PreLogin:
    captcha: str
    usn: str | None = None  # set once step one passes


@dataclass
class MockPortal:
    state: MockState
    config: PortalConfig
    sessions: dict[str, Session] = field(default_factory=dict)
    prelogins: dict[str, PreLogin] = field(default_factory=dict)
    ended: list[str] = field(default_factory=list)  # why sessions ended, for tests to read

    def end(self, sid: str, reason: str) -> None:
        if self.sessions.pop(sid, None) is not None:
            self.ended.append(reason)

    def live_sessions(self, usn: str) -> int:
        return sum(1 for s in self.sessions.values() if s.usn == usn)


def create_app(state: MockState | None = None, config: PortalConfig | None = None) -> FastAPI:
    portal = MockPortal(state or default_state(), config or PortalConfig())
    app = FastAPI(title="Mock College Portal", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.portal = portal

    def current_session(request: Request) -> tuple[str, Session] | None:
        sid = request.cookies.get(SESSION_COOKIE, "")
        session = portal.sessions.get(sid)
        if session is None:
            return None
        now = portal.config.clock()
        cfg = portal.config
        if now - session.last_seen > cfg.idle_timeout_seconds:
            portal.end(sid, "idle")
            return None
        if (
            cfg.max_lifetime_seconds is not None
            and now - session.created > cfg.max_lifetime_seconds
        ):
            portal.end(sid, "lifetime")
            return None
        if cfg.bind_user_agent and request.headers.get("user-agent", "") != session.user_agent:
            portal.end(sid, "user-agent")
            return None
        if cfg.require_referer:
            referer = urlsplit(request.headers.get("referer", ""))
            if referer.netloc != request.url.netloc:
                portal.end(sid, "referer")
                return None
        session.last_seen = now
        return sid, session

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse("/index.php", status_code=302)

    @app.get("/captcha.svg")
    def captcha(request: Request) -> Response:
        pre = portal.prelogins.get(request.cookies.get(PRELOGIN_COOKIE, ""))
        code = pre.captcha if pre else "?????"
        return Response(_captcha_svg(code), media_type="image/svg+xml")

    @app.get("/index.php")
    def index(request: Request, option: str = "", task: str = "", code: str = "") -> Response:
        if option in ("", "com_login"):
            return login_page(request)
        if option == "com_users" and task == "logout":
            sid = request.cookies.get(SESSION_COOKIE, "")
            portal.end(sid, "logout")
            response = RedirectResponse("/index.php", status_code=302)
            response.delete_cookie(SESSION_COOKIE)
            return response
        found = current_session(request)
        if found is None:
            return RedirectResponse("/index.php?expired=1", status_code=302)
        student = portal.state.student(found[1].usn)
        if option == "com_studentdashboard" and task == "dashboard":
            return _page("Dashboard", _dashboard(student))
        if option == "com_courses" and task in ("attendance", "cie"):
            course = next((c for c in student.courses if c.code == code), None)
            if course is None:
                return _page("Not found", "<p class='pm-error'>No such course.</p>", 404)
            body = _course(course) if task == "attendance" else _cie(course)
            return _page(course.code, body)
        if option == "com_timetable" and task == "view":
            return _page("Timetable", _timetable(student))
        if option == "com_results" and task == "view":
            return _page("Results", _results(student))
        if option == "com_fees" and task == "view":
            return _page("Fees", _fees())
        return _page("Not found", "<p class='pm-error'>Page not found.</p>", 404)

    def login_page(request: Request, error: str = "", status: int = 200) -> HTMLResponse:
        if portal.config.captcha == "fixed":
            captcha_code = portal.config.fixed_captcha
        else:
            captcha_code = "".join(secrets.choice(CAPTCHA_ALPHABET) for _ in range(5))
        pre_id = secrets.token_urlsafe(16)
        portal.prelogins[pre_id] = PreLogin(captcha=captcha_code)
        if request.query_params.get("expired"):
            error = error or "Your session has ended. Please log in again."
        response = _page("Student login", _login_form(error), status)
        response.set_cookie(PRELOGIN_COOKIE, pre_id, httponly=True, samesite="lax")
        return response

    @app.post("/index.php")
    async def login(request: Request, option: str = "", task: str = "") -> Response:
        form = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
        pre_id = request.cookies.get(PRELOGIN_COOKIE, "")
        pre = portal.prelogins.get(pre_id)
        if option != "com_login" or pre is None:
            return login_page(request, "Please start again.", 400)
        if task == "step1":
            usn = form.get("username", "").strip().upper()
            password = form.get("password") or "-".join(
                form.get(k, "") for k in ("yyyy", "mm", "dd")
            )
            student = portal.state.students.get(usn)
            if form.get("captcha", "").strip().upper() != pre.captcha:
                return login_page(request, "The code you typed does not match.", 401)
            if student is None or password != student.dob.isoformat():
                return login_page(request, "USN or date of birth is wrong.", 401)
            pre.usn = usn
            return _page("Verify", _step_two_form())
        if task == "step2" and pre.usn is not None:
            student = portal.state.student(pre.usn)
            if form.get("parent_digits", "").strip() != student.parent_mobile[-4:]:
                return login_page(request, "Those digits do not match our records.", 401)
            if portal.config.one_session_per_student:
                for sid in [s for s, v in portal.sessions.items() if v.usn == student.usn]:
                    portal.end(sid, "replaced")
            now = portal.config.clock()
            sid = secrets.token_urlsafe(24)
            portal.sessions[sid] = Session(
                usn=student.usn,
                user_agent=request.headers.get("user-agent", ""),
                created=now,
                last_seen=now,
            )
            portal.prelogins.pop(pre_id, None)
            response = RedirectResponse(f"/{DASHBOARD}", status_code=303)
            response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax")
            return response
        return login_page(request, "Please start again.", 400)

    return app


# HTML. Deliberately old-school, like the portals PortMax meets: tables, PHP-style links, no API.

_STYLE = """
body{font-family:Arial,sans-serif;margin:0;background:#f3f4f8;color:#222}
header{background:#1b1f6b;color:#fff;padding:10px 16px}header b{font-size:18px}
main{padding:16px;max-width:960px;margin:auto}table{border-collapse:collapse;background:#fff;
margin:8px 0;width:100%}th,td{border:1px solid #ccd;padding:6px 8px;text-align:left;font-size:14px}
th{background:#e8eaf6}nav a{margin-right:12px}.pm-error{color:#b4232c}
.pm-last-update{color:#666;font-size:13px}form{background:#fff;padding:16px;max-width:420px}
input,select{padding:6px;margin:4px 0}
"""


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(title)} | Mock College Portal</title><style>{_STYLE}</style></head>"
        "<body><header><b>Mock College of Engineering</b> &middot; Student Portal</header>"
        f"<main>{body}</main></body></html>"
    )
    return HTMLResponse(doc, status_code=status)


def _a(href: str, text: str, cls: str = "", id_: str = "") -> str:
    attrs = f" class='{cls}'" if cls else ""
    attrs += f" id='{id_}'" if id_ else ""
    return f"<a href='{escape(href)}'{attrs}>{escape(text)}</a>"


def _login_form(error: str) -> str:
    days = "".join(f"<option>{d:02d}</option>" for d in range(1, 32))
    months = "".join(f"<option>{m:02d}</option>" for m in range(1, 13))
    years = "".join(f"<option>{y}</option>" for y in range(2010, 1990, -1))
    message = f"<p class='pm-error'>{escape(error)}</p>" if error else ""
    return f"""
<h2>Student login</h2>{message}
<form id='pm-login' method='post' action='index.php?option=com_login&amp;task=step1'
 onsubmit="this.password.value=this.yyyy.value+'-'+this.mm.value+'-'+this.dd.value">
<label>USN<br><input name='username' autocomplete='off'></label><br>
<label>Date of birth<br><select name='dd'>{days}</select><select name='mm'>{months}</select>
<select name='yyyy'>{years}</select></label><input type='hidden' name='password'><br>
<img src='captcha.svg' alt='Security code' width='150' height='50'><br>
<label>Type the code above<br><input name='captcha' autocomplete='off'></label><br>
<button type='submit'>Next</button></form>"""


def _step_two_form() -> str:
    return """
<h2>Verify it's you</h2>
<form id='pm-login-step2' method='post' action='index.php?option=com_login&amp;task=step2'>
<label>Last 4 digits of your parent's mobile number<br>
<input name='parent_digits' inputmode='numeric' maxlength='4'></label><br>
<button type='submit'>Log in</button></form>"""


def _dashboard(s: Student) -> str:
    masked = s.parent_mobile[:2] + "XXXXX" + s.parent_mobile[-3:]
    profile = "".join(
        f"<tr><th>{k}</th><td>{escape(str(v))}</td></tr>"
        for k, v in (
            ("USN", s.usn),
            ("Name", s.name),
            ("Date of birth", s.dob.strftime("%d-%m-%Y")),
            ("Branch", s.branch),
            ("Semester", s.semester),
            ("Section", s.section),
            ("Parent mobile", masked),
        )
    )
    courses = "".join(
        f"<tr><td>{c.code}</td><td>{escape(c.name)}</td><td>{c.percent:.2f}%</td>"
        f"<td>{_a(_course_link(c.code), 'View', 'pm-course')}"
        "</td></tr>"
        for c in s.courses
    )
    nav = " ".join(
        (
            _a(TIMETABLE, "Timetable"),
            _a(RESULTS, "Results"),
            _a(FEES, "Fees"),
            _a(LOGOUT, "Logout", id_="pm-logout"),
        )
    )
    return f"""
<div id='pm-student-dashboard'><nav>{nav}</nav>
<h2>Welcome, {escape(s.name)}</h2>
<table class='pm-profile'>{profile}</table>
<h3>My courses</h3>
<table class='pm-course-list'><tr><th>Code</th><th>Course</th><th>Attendance</th><th></th></tr>
{courses}</table></div>"""


def _course_link(code: str) -> str:
    return f"index.php?option=com_courses&task=attendance&code={code}"


def _course(c: Course) -> str:
    rows = (
        ("Classes planned", c.planned),
        ("Classes held", c.held),
        ("Classes attended", c.attended),
        ("Attendance", f"{c.percent:.2f}%"),
    )
    table = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    cie_link = _a(f"index.php?option=com_courses&task=cie&code={c.code}", "CIE marks", "pm-cie")
    return f"""
<nav>{_a(DASHBOARD, "Dashboard")} {_a(LOGOUT, "Logout", id_="pm-logout")}</nav>
<h3 class='pm-course-title'>{c.code} &middot; {escape(c.name)}</h3>
<table class='pm-attendance'>{table}</table>
<p class='pm-last-update'>Last updated: {c.last_updated.strftime("%d-%m-%Y")}</p>{cie_link}"""


def _cie(c: Course) -> str:
    rows = "".join(
        f"<tr><td>{escape(component)}</td><td>{maximum:g}</td><td>{scored:g}</td></tr>"
        for component, scored, maximum in c.cie
    )
    return f"""
<nav>{_a(DASHBOARD, "Dashboard")} {_a(LOGOUT, "Logout", id_="pm-logout")}</nav>
<h3 class='pm-course-title'>{c.code} &middot; {escape(c.name)}: CIE marks</h3>
<table class='pm-cie-marks'><tr><th>Component</th><th>Max</th><th>Scored</th></tr>{rows}</table>"""


def _timetable(s: Student) -> str:
    head = "".join(f"<th>{a:%H:%M} - {b:%H:%M}</th>" for a, b in PERIODS)
    cells: dict[tuple[Weekday, int], tuple[str, str]] = {
        (day, period): (code, room) for day, period, code, room in s.timetable
    }
    body = ""
    for day in list(Weekday)[:6]:
        row = "".join(
            f"<td>{cells[(day, p)][0]}<br><small>{cells[(day, p)][1]}</small></td>"
            if (day, p) in cells
            else "<td>&mdash;</td>"
            for p in range(len(PERIODS))
        )
        body += f"<tr><th>{day.value}</th>{row}</tr>"
    return f"""
<nav>{_a(DASHBOARD, "Dashboard")} {_a(LOGOUT, "Logout", id_="pm-logout")}</nav>
<h3>Class timetable</h3>
<table class='pm-timetable'><tr><th>Day</th>{head}</tr>{body}</table>"""


def _results(s: Student) -> str:
    sections = ""
    for r in s.results:
        rows = "".join(
            f"<tr><td>{code}</td><td>{credits:g}</td><td>{grade}</td><td>{points:g}</td></tr>"
            for code, credits, grade, points in r.subjects
        )
        sections += (
            f"<section class='pm-sem' data-sem='{r.semester}'><h4>Semester {r.semester}</h4>"
            "<table class='pm-results'><tr><th>Course</th><th>Credits</th><th>Grade</th>"
            f"<th>Grade points</th></tr>{rows}</table>"
            f"<p class='pm-gpa'>SGPA: {r.sgpa:.2f} &nbsp; CGPA: {r.cgpa:.2f}</p></section>"
        )
    return f"""
<nav>{_a(DASHBOARD, "Dashboard")} {_a(LOGOUT, "Logout", id_="pm-logout")}</nav>
<h3>Semester results</h3>{sections}"""


def _fees() -> str:
    return f"""
<nav>{_a(DASHBOARD, "Dashboard")} {_a(LOGOUT, "Logout", id_="pm-logout")}</nav>
<h3>Fees</h3><table class='pm-fees'><tr><th>Due</th><td>Rs 1,24,500</td></tr></table>
<form method='post' action='index.php?option=com_fees&amp;task=paynow'>
<button>Pay now</button></form>"""


def _captcha_svg(code: str) -> str:
    rng = random.Random(code)  # the same code always draws the same picture
    letters = "".join(
        f"<text x='{14 + i * 26}' y='{32 + rng.randint(-5, 5)}' font-size='26' "
        f"font-family='monospace' transform='rotate({rng.randint(-18, 18)} {20 + i * 26} 28)' "
        f"fill='#{rng.randint(0x202020, 0x606060):06x}'>{ch}</text>"
        for i, ch in enumerate(code)
    )
    noise = "".join(
        f"<line x1='{rng.randint(0, 150)}' y1='{rng.randint(0, 50)}' x2='{rng.randint(0, 150)}' "
        f"y2='{rng.randint(0, 50)}' stroke='#9aa' stroke-width='1.5'/>"
        for _ in range(7)
    )
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' width='150' height='50'>"
        f"<rect width='150' height='50' fill='#eef'/>{noise}{letters}</svg>"
    )
