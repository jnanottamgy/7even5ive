"""Small, strict helpers every connector's parsers use to read portal HTML.

They raise instead of returning empty values: a selector that matches nothing means the page
changed, and the caller turns that into `PortalChanged` rather than an empty attendance list.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from selectolax.lexbor import LexborHTMLParser, LexborNode

from portmax.pages import Page

Tree = LexborHTMLParser
Node = LexborNode

_SPACES = re.compile(r"\s+")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


class Missing(ValueError):
    """The page does not contain what the parser expected."""


def parse(html: str) -> Tree:
    return LexborHTMLParser(html)


def clean(text: str) -> str:
    """Collapse whitespace, including non-breaking spaces, and trim."""
    return _SPACES.sub(" ", text.replace("\xa0", " ")).strip()


def one(tree: Tree | Node, selector: str) -> Node:
    node = tree.css_first(selector)
    if node is None:
        raise Missing(f"nothing matches {selector!r}")
    return node


def text(tree: Tree | Node, selector: str) -> str:
    return clean(one(tree, selector).text(separator=" "))


def cells(row: Node) -> list[str]:
    """The text of each cell in a table row, header cells included."""
    return [clean(cell.text(separator=" ")) for cell in row.css("th, td")]


def table_rows(tree: Tree | Node, selector: str) -> list[list[str]]:
    rows = [cells(row) for row in one(tree, selector).css("tr")]
    if not rows:
        raise Missing(f"{selector!r} has no rows")
    return rows


def table_kv(tree: Tree | Node, selector: str) -> dict[str, str]:
    """A two-column table of label and value, as a dict keyed by label."""
    pairs: dict[str, str] = {}
    for row in table_rows(tree, selector):
        if len(row) >= 2:
            pairs[row[0]] = row[1]
    return pairs


def number(value: str) -> float:
    """The first number in a cell: '73.33%' -> 73.33, 'Rs 1,24,500' -> 124500."""
    match = _NUMBER.search(value.replace(",", ""))
    if match is None:
        raise Missing(f"no number in {value!r}")
    return float(match.group())


def integer(value: str) -> int:
    result = number(value)
    if not result.is_integer():
        raise Missing(f"{value!r} is not a whole number")
    return int(result)


def only(pages: Sequence[Page]) -> Page:
    if len(pages) != 1:
        raise Missing(f"expected one page, got {len(pages)}")
    return pages[0]
