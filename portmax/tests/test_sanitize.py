from __future__ import annotations

import json
from datetime import date
from typing import Any

from portmax.forge.sanitize import REMOVED_BODY, Identity, digest, sanitize

PORTAL = "https://portal.example.edu"
COOKIE = "s3ss10nV4lue9876543"
WHO = Identity(
    usn="1MC24CS042",
    name="Asha Rao",
    dob=date(2005, 8, 14),
    phone="9845012345",
    email="asha.rao@example.com",
)


def entry(
    url: str,
    *,
    method: str = "GET",
    mime: str = "text/html",
    body: str = "",
    request_headers: list[dict[str, str]] | None = None,
    response_headers: list[dict[str, str]] | None = None,
    post: str | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {"method": method, "url": url, "headers": request_headers or []}
    if post is not None:
        request["postData"] = {"mimeType": "application/x-www-form-urlencoded", "text": post}
    return {
        "request": request,
        "response": {
            "status": 200,
            "headers": response_headers or [],
            "content": {"mimeType": mime, "text": body},
        },
    }


def recording() -> dict[str, Any]:
    cookie = [{"name": "Cookie", "value": f"PORTALSESSID={COOKIE}"}]
    dashboard = (
        "<table class='pm-profile'><tr><th>USN</th><td>1MC24CS042</td></tr>"
        "<tr><th>Name</th><td>Asha Rao</td></tr><tr><th>Date of birth</th><td>14-08-2005</td></tr>"
        "<tr><th>Parent mobile</th><td>98XXXXX345</td></tr>"
        "<tr><th>Email</th><td>asha.rao@example.com</td></tr></table>"
        f"<a href='/attendance?sid={COOKIE}'>Attendance</a> CS52 held 30"
    )
    return {
        "log": {
            "entries": [
                entry(f"{PORTAL}/index.php", body="<form id='login'></form>"),
                entry(f"{PORTAL}/captcha.svg", mime="image/svg+xml", body="<svg/>"),
                entry("https://fonts.example.net/font.woff2", mime="font/woff2"),
                entry(
                    f"{PORTAL}/index.php?option=com_login&task=step1",
                    method="POST",
                    post="username=1MC24CS042&password=2005-08-14&captcha=PM42X&parent_digits=2345",
                    response_headers=[
                        {"name": "Set-Cookie", "value": f"PORTALSESSID={COOKIE}; HttpOnly; Path=/"}
                    ],
                ),
                entry(
                    f"{PORTAL}/index.php?task=dashboard&sid={COOKIE}",
                    body=dashboard,
                    request_headers=cookie,
                ),
            ]
        }
    }


def test_nothing_secret_or_personal_survives() -> None:
    clean, _ = sanitize(recording(), WHO)
    text = json.dumps(clean)
    for secret in (
        COOKIE,
        "1MC24CS042",
        "Asha",
        "Rao",
        "14-08-2005",
        "2005-08-14",
        "98XXXXX345",
        "asha.rao@example.com",
        "PM42X",
        "parent_digits=2345",
    ):
        assert secret not in text, secret


def test_assets_other_sites_and_request_bodies_are_dropped() -> None:
    clean, report = sanitize(recording(), WHO)
    urls = [e["request"]["url"] for e in clean["log"]["entries"]]
    assert not any("captcha.svg" in u or "fonts.example.net" in u for u in urls)
    assert (report.dropped_assets, report.dropped_offsite, report.bodies_removed) == (1, 1, 1)
    login = next(e for e in clean["log"]["entries"] if e["request"]["method"] == "POST")
    assert login["request"]["postData"]["text"] == REMOVED_BODY


def test_stand_ins_are_consistent_so_requests_still_chain() -> None:
    clean, _ = sanitize(recording(), WHO)
    entries = clean["log"]["entries"]
    set_cookie = entries[1]["response"]["headers"][0]["value"]
    sent_cookie = entries[2]["request"]["headers"][0]["value"]
    assert set_cookie.startswith("PORTALSESSID=<cookie:1>") and "HttpOnly" in set_cookie
    assert sent_cookie == "PORTALSESSID=<cookie:1>"
    assert "CS52 held 30" in entries[2]["response"]["content"]["text"]  # data is untouched


def test_the_report_keeps_hashes_never_values() -> None:
    _, report = sanitize(recording(), WHO)
    exported = json.dumps(report.as_json())
    assert COOKIE not in exported and "1MC24CS042" not in exported
    assert {digest(COOKIE), digest("1MC24CS042"), digest("2345")} <= report.secret_hashes
