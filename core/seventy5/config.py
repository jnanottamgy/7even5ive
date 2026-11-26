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


@dataclass(frozen=True)
class Settings:
    # A file path means SQLite (local); postgresql://... means Supabase, through its pooler.
    database_url: str = os.environ.get("DATABASE_URL", str(ROOT / "data" / "75.db"))

    # Signed events from the WhatsApp bot. Dev default only; preflight refuses it in prod.
    bot_secret: str = os.environ.get("BOT_WEBHOOK_SECRET", "dev-bot-secret")
    # Why 300 s: long enough for clock drift, short enough that a captured request
    # cannot be replayed later.
    bot_max_skew_seconds: int = 300

    # One-time approval tokens for anything that writes outside 75.
    approval_secret: str = os.environ.get("APPROVAL_SECRET", "dev-approval-secret")
    approval_ttl_seconds: int = 15 * 60

    jev_api_key: str = os.environ.get("JEV_API_KEY", "")
    jev_url: str = os.environ.get("JEV_URL", "https://openrouter.ai/api/alpha/decisions")
    jev_model: str = os.environ.get("JEV_MODEL", "typesafe/jev-1.14")
    jev_timeout_seconds: float = 4.0
    # [TUNE] on labelled data. Filing needs 0.8; dropping something (chit-chat, spam) needs
    # 0.9, because silently losing a real deadline is the costly mistake.
    jev_file_confidence: float = float(os.environ.get("JEV_FILE_CONFIDENCE", "0.8"))
    jev_drop_confidence: float = float(os.environ.get("JEV_DROP_CONFIDENCE", "0.9"))

    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    llm_model: str = os.environ.get("LLM_MODEL", "claude-haiku-5-5")
    # Claude on Bedrock: set this to the model or inference-profile id from the Bedrock
    # console (credentials come from the normal AWS chain, never from this file).
    bedrock_model_id: str = os.environ.get("BEDROCK_MODEL_ID", "")
    aws_region: str = os.environ.get("AWS_REGION", "ap-south-1")

    # PortMax's saved portal answers (attendance, timetable). Same database in production.
    portmax_database_url: str = os.environ.get(
        "PORTMAX_DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'portmax.db'}".replace("\\", "/"))
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

    # ElevenLabs: the urgent call (calls.py) and the briefing's voice (briefing.py).
    elevenlabs_api_key: str = os.environ.get("ELEVENLABS_API_KEY", "")
    elevenlabs_agent_id: str = os.environ.get("ELEVENLABS_AGENT_ID", "")
    # The phone number imported into ElevenLabs (its id there, not the number itself).
    elevenlabs_phone_number_id: str = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID", "")
    # twilio (the demo) | sip (an Indian trunk, e.g. Exotel or Plivo) -- see docs/call.md.
    call_provider: str = os.environ.get("CALL_PROVIDER", "twilio")
    # Signs ElevenLabs' post-call webhook; empty refuses every webhook (never trusted unsigned).
    elevenlabs_webhook_secret: str = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "")
    elevenlabs_voice_id: str = os.environ.get("ELEVENLABS_VOICE_ID", "")
    elevenlabs_tts_model: str = os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")
    # [TUNE] The call rules (decision P4 in plan.md). Quiet hours are India time.
    call_default_lead_minutes: int = int(os.environ.get("CALL_LEAD_MINUTES", "120"))
    call_quiet_start: str = os.environ.get("CALL_QUIET_START", "22:00")
    call_quiet_end: str = os.environ.get("CALL_QUIET_END", "08:00")
    call_max_per_day: int = int(os.environ.get("CALL_MAX_PER_DAY", "2"))
    call_max_seconds: int = int(os.environ.get("CALL_MAX_SECONDS", "90"))
    # The demo student's real phone for the live call (91 + 10 digits). Never committed.
    demo_student_phone: str = os.environ.get("DEMO_STUDENT_PHONE", "")

    # Google sign-in on the server (google.py): a "Web application" OAuth client.
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    # Encrypts the stored Google refresh tokens. Empty in development: a fixed dev key is
    # used and the startup report says so.
    token_encryption_key: str = os.environ.get("TOKEN_ENCRYPTION_KEY", "")

    # College mail (mail.py, the mail filter): check times, India time.
    mail_check_times: str = os.environ.get("MAIL_CHECK_TIMES", "13:00,21:00")
    mailfilter_database_url: str = os.environ.get(
        "MAILFILTER_DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'mailfilter.db'}".replace("\\", "/"))
    # Claude on Bedrock for the mail judge (Mumbai). Same AWS credentials as BEDROCK_MODEL_ID.
    mail_model: str = os.environ.get("MAILFILTER_MODEL", "anthropic.claude-haiku-5-5")



settings = Settings()
