"""The morning briefing: today, in a few sentences, written by code from the student's own data.

What it says, in order: today's classes, what is due today and tomorrow, any subject where
attendance is at risk, new college mail worth a look, and the reminders the student set for
today. Every sentence is a template filled with values 7even5ive filed itself; no model writes
it, so it cannot invent a deadline or repeat something a forwarded message told it to say.

Voice: ElevenLabs reads it aloud, generated the first time the student taps play and cached per
student, day and text, so a second tap costs nothing. With no ElevenLabs key there is no audio
and the app reads the same text with Android's own text-to-speech.
Not: a notification. The briefing lives in the app (decision 41); nothing pushes it.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from . import clock, tools
from .calls import clean
from .config import settings
from .db import Database

log = logging.getLogger(__name__)

# ElevenLabs' premade "George" voice, used when ELEVENLABS_VOICE_ID is not set.
DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"
MAX_LINES = 3  # per section: a briefing is a glance, the app has the rest


class VoiceUnavailable(RuntimeError):
    """ElevenLabs could not make the audio. Said to the student as it is; the app falls back to
    the phone's own voice."""


def _time(at: datetime) -> str:
    return at.astimezone(clock.IST).strftime("%I:%M %p").lstrip("0")


def _greeting(now: datetime, name: str) -> str:
    hour = now.astimezone(clock.IST).hour
    part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    return f"Good {part}, {name}."


def _join(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _classes(db: Database, sid: int, now: datetime) -> tuple[list[dict[str, Any]], list[str]]:
    today = tools.timetable_today(db, sid, now)
    classes = today["classes"]
    if not today["connected"]:
        return classes, []
    if not classes:
        return classes, ["No classes today."]
    upcoming = [c for c in classes if c["end"] > now.astimezone(clock.IST).strftime("%H:%M")]
    first = (upcoming or classes)[0]
    count = len(classes)
    noun = "class" if count == 1 else "classes"
    if not upcoming:
        return classes, [f"Your {count} {noun} today are over."]
    lead = "starting with" if first is classes[0] else "next up is"
    return classes, [f"You have {count} {noun} today, {lead} {clean(first['subject'], 60)} at "
                     f"{_clock(first['start'])}" + (f" in {clean(first['room'], 20)}."
                                                     if first.get("room") else ".")]


def _clock(hhmm: str) -> str:
    return datetime.strptime(hhmm, "%H:%M").strftime("%I:%M %p").lstrip("0")


def _due(db: Database, sid: int, now: datetime) -> list[str]:
    local = now.astimezone(clock.IST)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_today, end_tomorrow = midnight + timedelta(days=1), midnight + timedelta(days=2)
    kinds = ("deadline", "exam", "event")
    today = db.items(sid, kinds=kinds, due_from=clock.iso(now), due_to=clock.iso(end_today))
    tomorrow = db.items(sid, kinds=kinds, due_from=clock.iso(end_today),
                        due_to=clock.iso(end_tomorrow))
    lines = []
    if today:
        parts = [f"{clean(r['title'], 60)} at {_time(datetime.fromisoformat(r['due_at']))}"
                 for r in today[:MAX_LINES]]
        more = len(today) - MAX_LINES
        lines.append("Due today: " + _join(parts) + (f", and {more} more." if more > 0 else "."))
    if tomorrow:
        parts = [clean(r["title"], 60) for r in tomorrow[:MAX_LINES]]
        more = len(tomorrow) - MAX_LINES
        lines.append("Tomorrow: " + _join(parts) + (f", and {more} more." if more > 0 else "."))
    if not lines:
        lines.append("Nothing is due today or tomorrow.")
    return lines


def _attendance(db: Database, sid: int) -> list[str]:
    plan = tools.attendance(db, sid)
    if not plan.get("connected"):
        return []
    risky = [s for s in plan["subjects"] if s["status"] in ("at_risk", "short", "unrecoverable")]
    lines = []
    for s in risky[:2]:
        # PortMax's own advice (exact fractions, the college's minimum, written by code), led
        # by the subject's name instead of its code so it reads well aloud.
        message = str(s.get("message") or "")
        advice = message.split(": ", 1)[1] if ": " in message else message
        name = clean(s.get("subject_name") or s.get("subject_code"), 60)
        lines.append(f"{name} is at {s['percent']:g}%: {advice}".rstrip())
    return lines


def _mail(db: Database, sid: int, now: datetime) -> list[str]:
    since = clock.iso(now - timedelta(days=1))
    rows = [r for r in db.items(sid, kinds=("deadline", "exam", "event", "notice"))
            if r["route"] == "mail" and r["created_at"] >= since]
    if not rows:
        return []
    names = [clean(r["organisation"] or r["title"], 50) for r in rows[:MAX_LINES]]
    noun = "mail" if len(rows) == 1 else "mails"
    return [f"New in college mail: {len(rows)} {noun} worth a look, from {_join(names)}."]


def _reminders(db: Database, sid: int, now: datetime) -> list[str]:
    local = now.astimezone(clock.IST)
    end_today = clock.iso(local.replace(hour=0, minute=0, second=0, microsecond=0)
                          + timedelta(days=1))
    today = [r for r in db.reminders(sid) if clock.iso(now) <= r["fire_at"] < end_today]
    if not today:
        return []
    parts = [f"{clean(r['title'], 50)} at {_time(datetime.fromisoformat(r['fire_at']))}"
             for r in today[:MAX_LINES]]
    return ["Your reminders today: " + _join(parts) + "."]


def build(db: Database, sid: int, now: datetime | None = None) -> dict[str, Any]:
    """Today's briefing as sections and one text to read aloud."""
    now = now or clock.now()
    student = db.student(sid)
    first = clean((student["name"] or "there").split()[0], 30)
    classes, class_lines = _classes(db, sid, now)
    sections = [
        {"key": "classes", "title": "Classes", "lines": class_lines},
        {"key": "due", "title": "Due soon", "lines": _due(db, sid, now)},
        {"key": "attendance", "title": "Attendance", "lines": _attendance(db, sid)},
        {"key": "mail", "title": "College mail", "lines": _mail(db, sid, now)},
        {"key": "reminders", "title": "Reminders", "lines": _reminders(db, sid, now)},
    ]
    sections = [s for s in sections if s["lines"]]
    greeting = _greeting(now, first)
    text = " ".join([greeting, *(line for s in sections for line in s["lines"])])
    return {
        "day": now.astimezone(clock.IST).date().isoformat(),
        "greeting": greeting,
        "sections": sections,
        "classes": classes,
        "text": text,
        "audio": {"available": voice_configured()},
    }


# --- the voice ----------------------------------------------------------------------------------
def voice_configured() -> bool:
    return bool(settings.elevenlabs_api_key)


def _cache_path(sid: int, day: date | str, text: str) -> Path:
    digest = hashlib.sha256(f"{settings.elevenlabs_voice_id}:{text}".encode()).hexdigest()[:16]
    return Path(settings.cache_dir) / "briefing" / f"{sid}-{day}-{digest}.mp3"


def speak(text: str, http: httpx.Client | None = None) -> bytes:
    """ElevenLabs text to speech: mp3 bytes. Raises VoiceUnavailable with a reason to show."""
    if not voice_configured():
        raise VoiceUnavailable("no ElevenLabs key: the phone reads it instead")
    voice = settings.elevenlabs_voice_id or DEFAULT_VOICE
    client = http or httpx.Client(timeout=25.0)
    try:
        resp = client.post(
            f"{settings.elevenlabs_api}/v1/text-to-speech/{voice}",
            params={"output_format": settings.elevenlabs_tts_format},
            json={"text": text, "model_id": settings.elevenlabs_tts_model},
            headers={"xi-api-key": settings.elevenlabs_api_key, "accept": "audio/mpeg"},
        )
    except httpx.HTTPError as err:
        log.warning("tts unreachable", extra={"error": type(err).__name__})
        raise VoiceUnavailable("the voice service can't be reached right now") from err
    if resp.status_code != 200 or not resp.content:
        log.warning("tts refused", extra={"status": resp.status_code})
        raise VoiceUnavailable("the voice service refused the briefing")
    return resp.content


def audio(db: Database, sid: int, now: datetime | None = None,
          http: httpx.Client | None = None) -> bytes:
    """Today's briefing as mp3: made on first request, then served from the cache. A changed
    briefing (a new deadline filed at noon) is a new file."""
    briefing = build(db, sid, now)
    path = _cache_path(sid, briefing["day"], briefing["text"])
    if path.exists():
        return path.read_bytes()
    sound = speak(briefing["text"], http)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Yesterday's files go: the cache only ever holds today's briefings.
        for old in path.parent.glob(f"{sid}-*.mp3"):
            if not old.name.startswith(f"{sid}-{briefing['day']}-"):
                old.unlink(missing_ok=True)
        path.write_bytes(sound)
    except OSError:
        log.warning("briefing cache not writable")
    return sound
