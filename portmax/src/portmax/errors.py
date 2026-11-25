"""The only ways a PortMax call can fail. Callers branch on `code`, never on message text."""

from __future__ import annotations


class PortMaxError(Exception):
    code = "portmax_error"

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail or self.code)
        self.detail = detail


class SessionExpired(PortMaxError):
    """The portal no longer recognises the student's login; the app asks for one login."""

    code = "session_expired"


class PortalUnavailable(PortMaxError):
    """The portal did not answer, or answered with a server error."""

    code = "portal_unavailable"


class PortalChanged(PortMaxError):
    """A page no longer looks like what we verified; we refuse to guess and return nothing."""

    code = "portal_changed"


class NotSupported(PortMaxError):
    """This college's portal has no such page (MSRIT has no timetable, for example)."""

    code = "not_supported"


class NotConnected(PortMaxError):
    """The student has never connected their portal, so there is nothing saved to answer from."""

    code = "not_connected"


class UnsafePlan(PortMaxError):
    """A fetch plan or a link it followed would leave the portal or do something other than read."""

    code = "unsafe_plan"
