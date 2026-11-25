"""Putting the pieces together for one student: tokens, mailbox, and disconnecting.

The mailbox takes any `token(fresh: bool) -> str` function, so production swaps the file
store used here for AgentCore Identity without touching the Gmail client.
"""

from __future__ import annotations

import time

import httpx

from mailfilter.config import Settings
from mailfilter.gmail import GmailMailbox
from mailfilter.store import Store
from mailfilter.tokens import FileRefreshTokenStore, GoogleTokens


def google_tokens(settings: Settings, http: httpx.Client | None = None) -> GoogleTokens:
    return GoogleTokens(
        settings.google_client_id,
        settings.google_client_secret,
        FileRefreshTokenStore(settings.token_file),
        http or httpx.Client(timeout=20.0),
        time.time,
    )


def gmail_mailbox(
    tokens: GoogleTokens, student_id: str, settings: Settings, http: httpx.Client | None = None
) -> GmailMailbox:
    def token(fresh: bool) -> str:
        return tokens.access_token(student_id, force_refresh=fresh)

    return GmailMailbox(token, http or httpx.Client(timeout=30.0), settings.max_text_chars)


def disconnect(store: Store, tokens: GoogleTokens, student_id: str) -> bool:
    """Revoke Google's grant, then delete the token and everything the filter holds. The local
    deletion happens even when Google cannot be reached; the return says whether it confirmed."""
    revoked = tokens.revoke(student_id)
    tokens.store.delete(student_id)
    store.forget(student_id)
    return revoked
