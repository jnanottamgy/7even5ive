"""What runs live and what runs on a stand-in, printed once at startup (plan 9.1).

Why: every outside account has a stand-in, so a missing key never crashes anything; it just
quietly switches a feature to its stand-in. This report makes that visible in the server's log
(CloudWatch on Lambda) so the team can see which keys landed. Names and yes/no only: never a
key's value, never a number, never an address that identifies a student.
"""

from __future__ import annotations

from .config import settings


def lines() -> list[str]:
    s = settings
    llm = ("Claude on Bedrock" if s.bedrock_model_id
           else "Claude (Anthropic API)" if s.anthropic_api_key else None)
    eleven = bool(s.elevenlabs_api_key)
    call_ready = eleven and s.elevenlabs_agent_id and s.elevenlabs_phone_number_id
    database = ("Supabase Postgres" if s.database_url.startswith(("postgres://", "postgresql://"))
                else None)
    signing_in = None
    if s.supabase_url and s.supabase_publishable_key:
        checks = ("JWKS + legacy secret" if s.supabase_jwt_secret else "JWKS (ES256/RS256)")
        signing_in = f"Supabase Auth, {checks}" + ("" if s.supabase_secret_key
                                                   else "; no secret key: accounts can't be deleted")
    rows = [
        ("Database", database, "SQLite files: data starts over when the server does"),
        ("Accounts (sign up, log in)", signing_in, "only the shared demo account"),
        ("Jev (message types, spam)", bool(s.jev_api_key), "every item goes to the LLM step"),
        ("LLM (dates, titles, mail judge)", llm, "recorded answers in the demo; real items need review"),
        ("WhatsApp bot webhook", s.bot_secret != "dev-bot-secret", "dev secret: only the demo tour can sign"),
        ("Bot's WhatsApp number (Link WhatsApp)", bool(s.bot_whatsapp_number),
         "the app shows the code to send, without a button"),
        ("Bot library (Files)", bool(s.library_url and s.library_service_token), "invented demo library"),
        ("Google sign-in (Gmail, Calendar, Classroom)",
         bool(s.google_client_id and s.google_client_secret), "demo mailbox, calendar kept in 7even5ive"),
        ("Token encryption key", bool(s.token_encryption_key), "fixed development key"),
        ("Approval token secret", s.approval_secret != "dev-approval-secret", "development secret"),
        ("ElevenLabs urgent call", f"via {s.call_provider}" if call_ready else None,
         "calls are recorded, not rung"),
        ("ElevenLabs call webhook", bool(s.elevenlabs_webhook_secret), "call outcomes refused"),
        ("ElevenLabs briefing voice", eleven, "the phone reads the briefing itself"),
        ("ElevenLabs voice assistant", eleven and bool(s.elevenlabs_assistant_agent_id),
         "the app says it isn't set up"),
        ("Real number for the demo call", bool(s.demo_student_phone), "the invented number is never dialled"),
        ("Firebase wake-ups", bool(s.fcm_service_account_json or s.fcm_service_account_file),
         "phones pull every 15 minutes"),
    ]
    out = ["integrations (live / stand-in):"]
    for name, live, fallback in rows:
        if live:
            how = f": {live}" if isinstance(live, str) else ""
            out.append(f"  live      {name}{how}")
        else:
            out.append(f"  stand-in  {name} ({fallback})")
    return out
