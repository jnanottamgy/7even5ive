# Voice: the assistant and the briefing (ElevenLabs)

Two voices, both optional, both behind the same gateway as every tap in the app.

## The voice assistant

The microphone button at the top of every tab opens **Ask 7even5ive**: the student talks, an
ElevenLabs agent answers.

```
App ── GET /api/voice/session (student token) ──> 7even5ive ── our ElevenLabs key ──> signed URL
App ══ WebSocket (signed URL) ═════════════════════════════════════════════════════> ElevenLabs agent
       mic audio up (16-bit PCM)              agent's voice down, transcripts, pings
       ◄── client_tool_call "due_this_week" ──
App ── POST /api/tools/due_this_week (student token) ──> gateway ──> answer
       ── client_tool_result ──────────────────────────────────────────────────────>
```

- **Our key never reaches the phone.** The server asks ElevenLabs for a signed URL good for one
  conversation; the agent accepts signed URLs only (`enable_auth`).
- **Every fact comes from a tool, and every tool runs through the gateway** on the student's own
  token: the same policy, provenance checks and audit as a tap or an MCP call. `add_to_calendar`
  still only asks; the student taps Approve. There is no tool that sends, submits or pays.
- **Tools** ([`voice.py`](../core/seventy5/voice.py)): `due_this_week`, `timetable_today`,
  `attendance`, `briefing`, `materials`, `opportunities`, `list_reminders`, `set_reminder`,
  `cancel_reminder`, `mark_done`, `reopen`, `add_to_calendar`. The phone runs only names the
  server listed for that conversation.
- **Nothing said is stored** by 7even5ive; the transcript lives on the phone while the screen
  is open. Five minutes at most per conversation (`VOICE_MAX_SECONDS`).
- **At ElevenLabs** the agent records no voice and each conversation is kept 30 days, then
  deleted (`calls.PRIVACY`; ElevenLabs' own default is to record and keep for ever). Re-run
  `setup-assistant` once to apply it to an agent made before.
- **Model**: Claude Haiku 5.5, run by ElevenLabs (`ELEVENLABS_AGENT_LLM`).
- **Audio**: the app plays whatever PCM rate the agent announces and records at the rate it asks
  for, in a call-style session so the phone's echo canceller works on the speaker. If the
  student talks over the agent, its audio stops at once.

**Set up**: `ELEVENLABS_API_KEY` in Parameter Store, then on a laptop with the key in
`core/.env`: `cd core && .venv/bin/python -m seventy5.voice setup-assistant` → the printed id
goes in `ELEVENLABS_ASSISTANT_AGENT_ID`. It creates (or updates by name) the twelve client tools
and the agent. `show-assistant` prints the configuration sent.

## The morning briefing

Today in a few sentences, written by code from the student's own data
([`briefing.py`](../core/seventy5/briefing.py)): today's classes, what is due today and
tomorrow, subjects where attendance is at risk (PortMax's exact advice), new college mail and
today's reminders. No model writes it, so it cannot invent a deadline or repeat something a
forward told it to say.

- **Home** → **Your day** → **Play**. With an ElevenLabs key the server makes an mp3
  (`GET /api/briefing/audio`) on the first tap and caches it per student, day and text; a
  changed briefing is a new file. Without a key the phone reads the same text with its own
  text-to-speech, and the card says which voice is reading.
- **In the app only**, never a notification (decision 41). Claude and the voice assistant can
  ask for it too (`briefing` tool).
- **Voice**: `ELEVENLABS_VOICE_ID` (default: ElevenLabs' premade "George"), model
  `ELEVENLABS_TTS_MODEL` (`eleven_flash_v2_5`), format `mp3_44100_64` (about half a megabyte a
  minute, well within Lambda's response limit).
