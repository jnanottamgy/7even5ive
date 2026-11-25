"""The `mailfilter` command.

mailfilter demo                 fill the demo database from the 30 sample mails (offline)
mailfilter connect --student S  Google sign-in for one demo account, then a first check
mailfilter check --student S    check now (real Gmail + Claude on Bedrock)
mailfilter cards --student S    print the open cards
mailfilter briefing --student S print the 7 AM briefing lines
mailfilter disconnect --student S
mailfilter schedule             print the EventBridge cron expressions
mailfilter eval                 score Claude on the sample mails (needs Bedrock access)
mailfilter mcp                  run the MCP server (MAILFILTER_STUDENT_ID)
"""

from __future__ import annotations

import argparse
import secrets
import sys
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from mailfilter.config import Settings
from mailfilter.errors import GmailConfigError, MailFilterError
from mailfilter.run import RunResult, check_mailbox, check_now
from mailfilter.store import Store
from mailfilter.timekit import IST, moment_text, utc_now

DEMO_CONNECTED = datetime(2026, 11, 30, 0, 0, tzinfo=IST)
DEMO_CHECKED = datetime(2026, 12, 4, 1, 0, tzinfo=IST)


def _summary(result: RunResult) -> str:
    text = (
        f"read {result.listed} mails: {result.carded} new cards, {result.updated} updated, "
        f"{result.dropped} not kept, {result.skipped} skipped"
    )
    if result.retried or result.failed:
        text += f", {result.retried} to retry, {result.failed} given up"
    if result.more:
        text += " (more to read at the next check)"
    if result.error:
        text += f"; stopped: {result.error}"
    return text


def _demo(settings: Settings, student_id: str) -> int:
    from mailfilter.fake import STUDENT_ADDRESS, FakeMailbox
    from mailfilter.samples import fake_mails, golden_judge

    store = Store(settings.database_url)
    store.forget(student_id)
    store.connect(student_id, STUDENT_ADDRESS, DEMO_CONNECTED)
    mailbox = FakeMailbox(fake_mails(), max_text_chars=settings.max_text_chars)
    result = check_mailbox(
        store, mailbox, golden_judge(), student_id, settings, trigger="demo",
        now=lambda: DEMO_CHECKED,
    )  # fmt: skip
    print(f"{student_id}: {_summary(result)}")
    print(f"saved in {settings.database_url}")
    return 0


def _connect(settings: Settings, student_id: str) -> int:
    from mailfilter.judge import ClaudeJudge
    from mailfilter.tokens import authorization_url, exchange_code, pkce_pair, wait_for_redirect
    from mailfilter.wiring import gmail_mailbox, google_tokens

    if not settings.google_client_id:
        raise GmailConfigError(
            "set MAILFILTER_GOOGLE_CLIENT_ID and MAILFILTER_GOOGLE_CLIENT_SECRET"
        )
    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}"
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    url = authorization_url(settings.google_client_id, redirect_uri, state, challenge)
    print("Sign in with the demo Google account (read-only Gmail access):")
    print(url)
    webbrowser.open(url)
    try:
        code = wait_for_redirect(server, state)
    finally:
        server.server_close()
    with httpx.Client(timeout=20.0) as http:
        refresh = exchange_code(
            http, settings.google_client_id, settings.google_client_secret, code, verifier,
            redirect_uri,
        )  # fmt: skip
    tokens = google_tokens(settings)
    tokens.store.put(student_id, refresh)
    mailbox = gmail_mailbox(tokens, student_id, settings)
    store = Store(settings.database_url)
    store.connect(student_id, mailbox.email_address(), utc_now())
    print(f"{student_id}: connected. Reading today's mail...")
    result = check_now(
        store, mailbox, ClaudeJudge.from_settings(settings), student_id, settings,
        force=True, trigger="first",
    )  # fmt: skip
    print(f"{student_id}: {_summary(result)}")
    return 0


def _check(settings: Settings, student_id: str, force: bool) -> int:
    from mailfilter.judge import ClaudeJudge
    from mailfilter.wiring import gmail_mailbox, google_tokens

    store = Store(settings.database_url)
    mailbox = gmail_mailbox(google_tokens(settings), student_id, settings)
    result = check_now(
        store, mailbox, ClaudeJudge.from_settings(settings), student_id, settings, force=force
    )
    print(f"{student_id}: {_summary(result)}")
    return 0 if result.error is None else 1


def _cards(settings: Settings, student_id: str, include_past: bool) -> int:
    from mailfilter.tools import opportunities_answer

    store = Store(settings.database_url)
    answer = opportunities_answer(store, student_id, utc_now(), settings, include_past=include_past)
    checked = moment_text(answer.checked_at) if answer.checked_at else "never"
    print(f"{student_id}: {answer.connection}, last checked {checked}")
    for card in answer.data:
        link = f" {card.form_link}" if card.form_link else ""
        print(f"- {card.summary}{link}")
    if not answer.data:
        print("- no open placements, internships or exam notices")
    return 0


def _briefing(settings: Settings, student_id: str) -> int:
    from mailfilter.tools import briefing_lines

    for line in briefing_lines(Store(settings.database_url), student_id, utc_now(), settings):
        print(line)
    return 0


def _disconnect(settings: Settings, student_id: str) -> int:
    from mailfilter.wiring import disconnect, google_tokens

    revoked = disconnect(Store(settings.database_url), google_tokens(settings), student_id)
    print(
        f"{student_id}: everything deleted; Google " + ("confirmed" if revoked else "unreachable")
    )
    return 0


def _schedule(settings: Settings) -> int:
    from mailfilter.schedule import eventbridge_crons, next_check

    times = ", ".join(f"{t:%H:%M}" for t in settings.check_times)
    print(f"checks at {times} India time")
    for cron in eventbridge_crons(settings.check_times):
        print(cron)
    print(f"next: {moment_text(next_check(utc_now(), settings.check_times))}")
    return 0


def _eval(settings: Settings) -> int:
    from mailfilter.evaluate import score_all
    from mailfilter.judge import ClaudeJudge

    scores = score_all(ClaudeJudge.from_settings(settings))
    for score in scores:
        print(("PASS " if score.passed else "FAIL ") + score.key + "".join(
            f"\n     {problem}" for problem in score.problems))  # fmt: skip
    passed = sum(score.passed for score in scores)
    print(f"{passed}/{len(scores)} passed with {settings.model}")
    return 0 if passed == len(scores) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mailfilter")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "connect", "check", "cards", "briefing", "disconnect"):
        command = commands.add_parser(name)
        command.add_argument("--student", default="demo")
        if name == "check":
            command.add_argument("--force", action="store_true", help="ignore the cooldown")
        if name == "cards":
            command.add_argument("--include-past", action="store_true")
    for name in ("schedule", "eval", "mcp"):
        commands.add_parser(name)
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    try:
        if args.command == "demo":
            return _demo(settings, args.student)
        if args.command == "connect":
            return _connect(settings, args.student)
        if args.command == "check":
            return _check(settings, args.student, args.force)
        if args.command == "cards":
            return _cards(settings, args.student, args.include_past)
        if args.command == "briefing":
            return _briefing(settings, args.student)
        if args.command == "disconnect":
            return _disconnect(settings, args.student)
        if args.command == "schedule":
            return _schedule(settings)
        if args.command == "eval":
            return _eval(settings)
        from mailfilter.adapters.mcp_server import main as serve

        serve()
        return 0
    except MailFilterError as error:
        print(f"{error.code}: {error.detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
