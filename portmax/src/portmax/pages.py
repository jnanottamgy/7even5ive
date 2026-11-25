"""A fetched portal page, the unit that travels from the student's phone to our server."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# A portal page is a few hundred kilobytes at most; anything bigger is not a page we asked for.
MAX_PAGE_BYTES = 2_000_000


class Page(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    step: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    url: str = Field(max_length=2048)
    status: int = Field(ge=100, le=599)
    html: str = Field(max_length=MAX_PAGE_BYTES)
    fetched_at: datetime


PagesByStep = Mapping[str, Sequence[Page]]


def by_step(pages: Iterable[Page]) -> dict[str, list[Page]]:
    grouped: dict[str, list[Page]] = defaultdict(list)
    for page in pages:
        grouped[page.step].append(page)
    return dict(grouped)
