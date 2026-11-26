"""Settings, read once from the environment.

Why: every external service has a stand-in, so the whole loop runs on a laptop with no
accounts; a missing key switches to the stand-in instead of crashing.
Not: a settings framework (pydantic-settings) -- a dozen plain values do not need one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    # Why: one tiny loader instead of a python-dotenv dependency. Real env vars win.
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.split(" #")[0].strip())


ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(ROOT / ".env")

# The bot webhook's development secret: in this repository, so anyone can sign with it. While it
# is in use the webhook accepts events for the demo student only, and WhatsApp can't be linked.
DEV_BOT_SECRET = "dev-bot-secret"
# The approval tokens' development secret: also public. On a deployed server it is refused.
DEV_APPROVAL_SECRET = "dev-approval-secret"


def deployed() -> bool:
    """A real deployment: on AWS Lambda, or keeping data in Postgres (Supabase). Real students'
    data, so a public development secret must never protect anything there."""
    url = os.environ.get("DATABASE_URL") or ""
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME")) or url.startswith(
        ("postgres://", "postgresql://", "postgresql+psycopg://"))

_DATABASE_URL = (os.environ.get("DATABASE_URL") or str(ROOT / "data" / "75.db"))
# On Supabase all three share one database (their tables have distinct names); locally each
# has its own SQLite file. An explicit PORTMAX_/MAILFILTER_DATABASE_URL always wins.
_SHARED = (_DATABASE_URL if _DATABASE_URL.startswith(
    ("postgres://", "postgresql://", "postgresql+psycopg://")) else "")


@dataclass(frozen=True)
class Settings:
    # A file path means SQLite (local); postgresql://... means Supabase, through its pooler.
    database_url: str = _DATABASE_URL

    # Supabase Auth: the app signs in there itself and sends its access token here, which this
    # service checks (auth.py). The URL and publishable key are not secret (the app gets them
    # from /api/auth/config). The secret key only deletes accounts and checks usernames' logins.
    supabase_url: str = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_publishable_key: str = (os.environ.get("SUPABASE_PUBLISHABLE_KEY")
                                     or os.environ.get("SUPABASE_ANON_KEY", ""))
    supabase_secret_key: str = (os.environ.get("SUPABASE_SECRET_KEY")
                                or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))
    # Only for a project still signing with the legacy shared secret (HS256). Projects on JWT
    # signing keys (ES256/RS256) need nothing: their public keys come from the JWKS endpoint.
    supabase_jwt_secret: str = os.environ.get("SUPABASE_JWT_SECRET", "")
    # The WhatsApp number of the bot (91 + 10 digits), for the app's "Link WhatsApp" button.
    bot_whatsapp_number: str = "".join(
        ch for ch in os.environ.get("BOT_WHATSAPP_NUMBER", "") if ch.isdigit())

    # Signed events from the WhatsApp bot. With the dev default, only the demo's (api.py).
    bot_secret: str = (os.environ.get("BOT_WEBHOOK_SECRET") or DEV_BOT_SECRET)
    # Why 300 s: long enough for clock drift, short enough that a captured request
    # cannot be replayed later.
    bot_max_skew_seconds: int = 300

    # One-time approval tokens for anything that writes outside 75.
    # With the dev default on a deployed server, approvals are refused (gateway.py).
    approval_secret: str = (os.environ.get("APPROVAL_SECRET") or DEV_APPROVAL_SECRET)
    approval_ttl_seconds: int = 15 * 60

    jev_api_key: str = os.environ.get("JEV_API_KEY", "")
    jev_url: str = (os.environ.get("JEV_URL") or "https://openrouter.ai/api/alpha/decisions")
    jev_model: str = (os.environ.get("JEV_MODEL") or "typesafe/jev-1.14")
    jev_timeout_seconds: float = 4.0
    # [TUNE] on labelled data. Filing needs 0.8; dropping something (chit-chat, spam) needs
    # 0.9, because silently losing a real deadline is the costly mistake.
    jev_file_confidence: float = float((os.environ.get("JEV_FILE_CONFIDENCE") or "0.8"))
    jev_drop_confidence: float = float((os.environ.get("JEV_DROP_CONFIDENCE") or "0.9"))

    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    llm_model: str = (os.environ.get("LLM_MODEL") or "claude-haiku-5-5")
    # Claude on Bedrock: set this to the model or inference-profile id from the Bedrock
    # console (credentials come from the normal AWS chain, never from this file).
    bedrock_model_id: str = os.environ.get("BEDROCK_MODEL_ID", "")
    aws_region: str = (os.environ.get("AWS_REGION") or "ap-south-1")
    # Where Bedrock is called. Defaults to the region the code runs in; set it when the model
    # is enabled in another region (the serverless demo runs in Sydney, Haiku may be in Mumbai).
    bedrock_region: str = (os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION")
                           or "ap-south-1")
    # Generated files kept for a while (the briefing's audio). Lambda can only write /tmp.
    cache_dir: str = (os.environ.get("CACHE_DIR") or str(ROOT / "data" / "cache"))

    # PortMax's saved portal answers (attendance, timetable). Same database in production.
    portmax_database_url: str = os.environ.get("PORTMAX_DATABASE_URL") or _SHARED or (
        f"sqlite:///{ROOT / 'data' / 'portmax.db'}".replace("\\", "/"))
    timezone: str = "Asia/Kolkata"
    # The WhatsApp bot's library. Both set: Files reads the real library and upcoming
    # deadlines are backfilled from it. Either empty: an invented demo library stands in.
    library_url: str = os.environ.get("LIBRARY_URL", "").rstrip("/")
    library_service_token: str = os.environ.get("LIBRARY_SERVICE_TOKEN", "")
    # Set on AWS only: the SQS queue between ingress and the cascade Lambda.
    queue_url: str = os.environ.get("QUEUE_URL", "")
    # The service's own public address (https://...), for Google's sign-in redirect and the
    # call webhook. Render sets RENDER_EXTERNAL_URL itself.
    public_url: str = (os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL")
                       or "").rstrip("/")

    # Firebase Cloud Messaging, only to wake the phone (fcm.py). The service account's JSON,
    # inline or as a file path. Empty: no wake-ups; the phone still pulls every 15 minutes.
    fcm_service_account_json: str = os.environ.get("FCM_SERVICE_ACCOUNT_JSON", "")
    fcm_service_account_file: str = os.environ.get("FCM_SERVICE_ACCOUNT_FILE", "")

    # ElevenLabs: the urgent call (calls.py), the briefing's voice (briefing.py) and the in-app
    # voice assistant (voice.py).
    elevenlabs_api_key: str = os.environ.get("ELEVENLABS_API_KEY", "")
    # The API's address. The default serves everywhere; ElevenLabs' India data residency is
    # https://api.in.residency.elevenlabs.io (only for a workspace created there).
    elevenlabs_api: str = (os.environ.get("ELEVENLABS_API") or "https://api.elevenlabs.io").rstrip("/")
    elevenlabs_agent_id: str = os.environ.get("ELEVENLABS_AGENT_ID", "")
    # The in-app voice assistant: a second agent, with tools the phone runs through the gateway.
    elevenlabs_assistant_agent_id: str = os.environ.get("ELEVENLABS_ASSISTANT_AGENT_ID", "")
    # The model both agents think with (ElevenLabs runs it; no key of ours involved).
    elevenlabs_agent_llm: str = (os.environ.get("ELEVENLABS_AGENT_LLM") or "claude-haiku-5-5")
    # How long one conversation with the assistant may last.
    voice_max_seconds: int = int((os.environ.get("VOICE_MAX_SECONDS") or "300"))
    # The phone number imported into ElevenLabs (its id there, not the number itself).
    elevenlabs_phone_number_id: str = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID", "")
    # twilio (the demo) | exotel (an Indian number, imported natively) | sip (any SIP trunk,
    # e.g. Plivo) -- see docs/call.md.
    call_provider: str = (os.environ.get("CALL_PROVIDER") or "twilio")
    # Signs ElevenLabs' post-call webhook; empty refuses every webhook (never trusted unsigned).
    elevenlabs_webhook_secret: str = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "")
    elevenlabs_voice_id: str = os.environ.get("ELEVENLABS_VOICE_ID", "")
    elevenlabs_tts_model: str = (os.environ.get("ELEVENLABS_TTS_MODEL") or "eleven_flash_v2_5")
    # 64 kbps mp3: a minute of briefing is about half a megabyte, well inside Lambda's limits.
    elevenlabs_tts_format: str = (os.environ.get("ELEVENLABS_TTS_FORMAT") or "mp3_44100_64")
    # [TUNE] The call rules (decision P4 in plan.md). Quiet hours are India time.
    call_default_lead_minutes: int = int((os.environ.get("CALL_LEAD_MINUTES") or "120"))
    call_quiet_start: str = (os.environ.get("CALL_QUIET_START") or "22:00")
    call_quiet_end: str = (os.environ.get("CALL_QUIET_END") or "08:00")
    call_max_per_day: int = int((os.environ.get("CALL_MAX_PER_DAY") or "2"))
    call_max_seconds: int = int((os.environ.get("CALL_MAX_SECONDS") or "90"))
    # The demo student's real phone for the live call (91 + 10 digits). Never committed.
    demo_student_phone: str = os.environ.get("DEMO_STUDENT_PHONE", "")

    # Google sign-in on the server (google.py): a "Web application" OAuth client.
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    # Encrypts the stored Google refresh tokens. Empty in development: a fixed dev key is
    # used and the startup report says so.
    token_encryption_key: str = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
    # Classroom with each mail check (and once on connecting): on unless switched off.
    classroom_enabled: bool = (os.environ.get("CLASSROOM_ENABLED") or "1") not in ("0", "false", "")

    # College mail (mail.py, the mail filter): check times, India time.
    mail_check_times: str = (os.environ.get("MAIL_CHECK_TIMES") or "13:00,21:00")
    mailfilter_database_url: str = os.environ.get("MAILFILTER_DATABASE_URL") or _SHARED or (
        f"sqlite:///{ROOT / 'data' / 'mailfilter.db'}".replace("\\", "/"))
    # Claude on Bedrock for the mail judge (Mumbai). Same AWS credentials as BEDROCK_MODEL_ID.
    mail_model: str = (os.environ.get("MAILFILTER_MODEL") or "anthropic.claude-haiku-5-5")



settings = Settings()
