"""Runs a fetch plan over HTTP: server mode, the forge's live checks, and our tests.

On the phone the same plan runs in JavaScript inside the student's WebView (`runner/`); this is
its Python twin and must behave the same way: GET only, a Referer from the portal on every
request, links checked before they are followed, and the session checked on every page.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from portmax.contract import utc_now
from portmax.errors import PortalChanged, PortalUnavailable, SessionExpired, UnsafePlan
from portmax.htmlkit import parse
from portmax.manifest import Manifest, Markers
from portmax.pages import Page
from portmax.plan import FetchPlan, Step, resolve_link


class Response(Protocol):
    @property
    def url(self) -> object: ...
    @property
    def status_code(self) -> int: ...
    @property
    def text(self) -> str: ...


class Client(Protocol):
    """Any HTTP client with a cookie jar: httpx in production, the test client in tests."""

    def get(self, url: str, *, headers: Mapping[str, str], follow_redirects: bool) -> Response: ...


def check_session(page: Page, markers: Markers) -> None:
    """Raise unless the page is a logged-in portal page."""
    tree = parse(page.html)
    if tree.css_first(markers.login_page) is not None:
        raise SessionExpired(f"{page.step}: the portal showed its login page")
    if tree.css_first(markers.logged_in) is None:
        raise PortalChanged(f"{page.step}: neither a logged-in page nor the login page")


def links(page: Page, step: Step, base_url: str) -> list[str]:
    assert step.for_each is not None
    found: list[str] = []
    for node in parse(page.html).css(step.for_each.select):
        href = node.attributes.get(step.for_each.attr)
        if href:
            path = resolve_link(base_url, page.url, href)
            if path not in found:
                found.append(path)
    return found[: step.for_each.max_items]


def run_plan(
    plan: FetchPlan,
    manifest: Manifest,
    client: Client,
    *,
    landing_url: str | None = None,
    steps: list[str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Page]:
    """Fetch every page the plan names, in order, and return them; nothing is parsed here.

    `landing_url` is the page the student was on after logging in, the Referer for the first
    request. `steps` limits the run (the keep-alive runs only its own step).
    """
    base = manifest.base_url
    referer = landing_url or urljoin(base, manifest.login_path)
    fetched: dict[str, list[Page]] = {}
    pages: list[Page] = []
    first = True
    for step in plan.steps:
        if steps is not None and step.id not in steps:
            continue
        targets: list[tuple[str, str]] = []  # (path, referer)
        if step.path is not None:
            targets.append((step.path, referer))
        else:
            assert step.for_each is not None
            for source in fetched.get(step.for_each.from_step, []):
                targets.extend((path, source.url) for path in links(source, step, base))
        for path, ref in targets:
            if not first and plan.pace_ms:
                sleep(plan.pace_ms / 1000)
            first = False
            page = _get(client, base, step.id, path, ref)
            check_session(page, manifest.markers)
            fetched.setdefault(step.id, []).append(page)
            pages.append(page)
            referer = page.url
    return pages


def _get(client: Client, base: str, step_id: str, path: str, referer: str) -> Page:
    url = urljoin(base, path)
    try:
        response = client.get(url, headers={"Referer": referer}, follow_redirects=True)
    except httpx.HTTPError as error:
        raise PortalUnavailable(f"{step_id}: {type(error).__name__}") from error
    final = str(response.url)
    if urlsplit(final).netloc != urlsplit(base).netloc:
        raise UnsafePlan(f"{step_id}: the portal redirected off-site")
    if response.status_code >= 500:
        raise PortalUnavailable(f"{step_id}: HTTP {response.status_code}")
    return Page(
        step=step_id,
        url=final,
        status=response.status_code,
        html=response.text,
        fetched_at=utc_now(),
    )
