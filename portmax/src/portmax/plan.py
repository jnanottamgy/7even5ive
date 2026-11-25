"""The fetch plan: which pages to read, in order, as data rather than code.

It is data because it runs in two places that share no code: on the student's Android phone (the
JavaScript runner, inside the WebView session they logged in to) and on a server (the Python
executor, for portals that allow it and for our tests). Both read the same JSON.

Read-only holds by construction: a step has no method, so every request is a GET, and every path,
including links found on a page at run time, must stay on the portal and pass `check_path`.
"""

from __future__ import annotations

import re
from typing import Self
from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from portmax.contract import ToolName
from portmax.errors import UnsafePlan

# A path token that starts with any of these is refused: these are the requests that change
# something or end the session. Matched per token, so "credits" never trips "edit".
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    "logout",
    "logoff",
    "signout",
    "save",
    "update",
    "submit",
    "delete",
    "remove",
    "pay",
    "edit",
    "change",
    "reset",
    "password",
    "register",
    "apply",
    "upload",
    "cancel",
)

_TOKEN = re.compile(r"[a-z]+|[0-9]+")
_STEP_ID = r"^[a-z][a-z0-9_]{0,31}$"


def path_tokens(path: str) -> list[str]:
    """Split a path and query into words, breaking camelCase and snake_case apart."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", path)
    return _TOKEN.findall(spaced.lower())


def check_path(path: str) -> str:
    """Return the path unchanged if it is a relative, read-only portal path; raise otherwise."""
    if not path or len(path) > 2048:
        raise UnsafePlan("empty or overlong path")
    parts = urlsplit(path)
    if parts.scheme or parts.netloc or path.startswith("//") or "\\" in path:
        raise UnsafePlan(f"not a relative portal path: {path!r}")
    for token in path_tokens(parts.path + "?" + parts.query):
        for word in FORBIDDEN_PREFIXES:
            if token.startswith(word):
                raise UnsafePlan(f"{path!r} contains {token!r}, which may change or end something")
    return path


def resolve_link(base_url: str, page_url: str, href: str) -> str:
    """Resolve a link found on a page; refuse it unless it stays on the portal and is read-only."""
    absolute = urljoin(page_url, href.strip())
    target, base = urlsplit(absolute), urlsplit(base_url)
    if (target.scheme, target.netloc) != (base.scheme, base.netloc):
        raise UnsafePlan(f"link leaves the portal: {absolute!r}")
    relative = target.path + (f"?{target.query}" if target.query else "")
    return check_path(relative)


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


class ForEach(_Model):
    """Fan out over links found on an earlier step's pages."""

    from_step: str = Field(alias="from", pattern=_STEP_ID)
    select: str = Field(min_length=1, max_length=200, description="CSS selector for the links")
    attr: str = Field(default="href", pattern=r"^[a-z-]{1,30}$")
    max_items: int = Field(default=30, ge=1, le=100)


class Step(_Model):
    id: str = Field(pattern=_STEP_ID)
    path: str | None = None
    for_each: ForEach | None = None

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.path is None) == (self.for_each is None):
            raise ValueError(f"step {self.id}: give exactly one of path or for_each")
        if self.path is not None:
            check_path(self.path)
        return self


class FetchPlan(_Model):
    version: str = Field(min_length=1, max_length=20)
    steps: list[Step] = Field(min_length=1, max_length=20)
    keepalive_step: str = Field(pattern=_STEP_ID)
    tool_steps: dict[ToolName, list[str]]

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"step id {step.id} repeats")
            if step.for_each is not None and step.for_each.from_step not in seen:
                raise ValueError(f"step {step.id} reads from a step that has not run yet")
            seen.add(step.id)
        keepalive = self.step(self.keepalive_step)
        if keepalive.path is None:
            raise ValueError("the keep-alive step must be a single fixed page")
        for tool, steps in self.tool_steps.items():
            missing = [s for s in steps if s not in seen]
            if missing:
                raise ValueError(f"{tool} needs steps that do not exist: {missing}")
        return self

    def step(self, step_id: str) -> Step:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise ValueError(f"no step {step_id}")
