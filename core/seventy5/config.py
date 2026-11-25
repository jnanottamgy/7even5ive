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
    db_path: str = os.environ.get("DB_PATH", str(ROOT / "data" / "75.db"))

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


settings = Settings()
