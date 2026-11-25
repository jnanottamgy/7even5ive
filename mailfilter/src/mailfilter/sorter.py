"""The slot for Jev: a fast sorter that may drop obvious junk before Claude reads it.

Off by default (`NoSorter`). A sorter can only ever *drop* a mail, and only as "other" with
confidence at or above the threshold; it can never keep one, because a card needs Claude to
read the deadline and link out of the mail. A sorter that fails is ignored and Claude judges.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from mailfilter.contract import Kind

log = logging.getLogger("mailfilter")


@dataclass(frozen=True)
class Sorting:
    kind: Kind
    confidence: float


class Sorter(Protocol):
    name: str

    def sort(self, rendered: str) -> Sorting | None: ...


class NoSorter:
    name = "none"

    def sort(self, rendered: str) -> Sorting | None:
        return None


def drops_without_claude(sorter: Sorter, rendered: str, threshold: float) -> bool:
    try:
        sorting = sorter.sort(rendered)
    except Exception as error:  # noqa: BLE001 - a broken sorter must never lose a mail
        log.warning("sorter failed, Claude judges instead: %s", type(error).__name__)
        return False
    return sorting is not None and sorting.kind == "other" and sorting.confidence >= threshold
