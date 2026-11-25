"""Named failures. A detail is a short code or word: never mail content, never an address."""

from __future__ import annotations


class MailFilterError(Exception):
    code = "mailfilter_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotConnected(MailFilterError):
    """The student has not connected college mail, or has disconnected it."""

    code = "not_connected"


class NeedsReconnect(MailFilterError):
    """Google no longer accepts our access: revoked, expired (7 days in Testing) or unticked."""

    code = "needs_reconnect"


class CollegeBlocked(MailFilterError):
    """The college's Google admin does not allow this app to read mail (domainPolicy)."""

    code = "college_blocked"


class GmailUnavailable(MailFilterError):
    """Gmail or Google's sign-in service failed after retries; the next check tries again."""

    code = "gmail_unavailable"


class GmailConfigError(MailFilterError):
    """Our Google setup is wrong (API not enabled, bad client): a person has to fix it."""

    code = "gmail_config"


class JudgeUnavailable(MailFilterError):
    """Claude on Bedrock failed after retries; the next check tries again."""

    code = "judge_unavailable"


class JudgeConfigError(MailFilterError):
    """Bedrock refused our request itself (credentials, model access, request shape)."""

    code = "judge_config"


class JudgeFailed(MailFilterError):
    """Claude's answer for one mail was unusable (refusal, cut short, wrong shape)."""

    code = "judge_failed"


class MailUnreadable(MailFilterError):
    """One mail Gmail returned in a form we cannot read: that mail fails, the check goes on."""

    code = "mail_unreadable"


class CheckInProgress(MailFilterError):
    code = "check_in_progress"


class TooSoon(MailFilterError):
    """'Check now' was pressed again within the cooldown."""

    code = "too_soon"


# A whole check stops on these: carrying on would only fail the same way for every mail.
RUN_STOPPING = (
    NotConnected,
    NeedsReconnect,
    CollegeBlocked,
    GmailUnavailable,
    GmailConfigError,
    JudgeUnavailable,
    JudgeConfigError,
)
