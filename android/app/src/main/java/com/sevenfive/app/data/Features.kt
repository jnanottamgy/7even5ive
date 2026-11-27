package com.sevenfive.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** One class from today's timetable (`classes_today`). Times are "HH:mm", India time. */
@Serializable
data class ClassSlot(
    val start: String = "",
    val end: String = "",
    @SerialName("subject_code") val subjectCode: String = "",
    val subject: String = "",
    val room: String? = null,
)

/** The college mailbox (`/api/cards` → `mail`, `GET /api/mail`). */
@Serializable
data class MailStatus(
    /** demo (invented mail: the demo account), gmail, or none (an account without Google yet). */
    val mode: String = "demo",
    val connected: Boolean = false,
    val status: String = "not_connected",
    /** The Gmail address, when it is the student's real mailbox. */
    val address: String? = null,
    @SerialName("checked_at") val checkedAt: String? = null,
    @SerialName("next_check_at") val nextCheckAt: String? = null,
    /** Set while "Check now" is cooling down: when it works again. */
    @SerialName("check_now_after") val checkNowAfter: String? = null,
    /** Mails the filter read and left out (not a placement, internship or exam notice). */
    @SerialName("left_out") val leftOut: Int = 0,
    /** Google stopped accepting the connection (7 days in Testing, or revoked): sign in again. */
    @SerialName("needs_reconnect") val needsReconnect: Boolean = false,
) {
    val isDemo: Boolean get() = mode == "demo"

    /** A real account that hasn't connected Google: nothing to read yet. */
    val needsGoogle: Boolean get() = mode == "none"
}

/** `POST /api/mail/check`. */
@Serializable
data class MailCheckResult(
    val mode: String = "demo",
    val new: Int = 0,
    val updated: Int = 0,
    @SerialName("left_out") val leftOut: Int = 0,
    val cards: Int = 0,
    val more: Boolean = false,
    val error: String? = null,
    val mail: MailStatus = MailStatus(),
)

/** `GET /api/settings`: everything Settings shows about the server side. */
@Serializable
data class AppSettings(
    val calls: CallSettings = CallSettings(),
    val push: PushInfo = PushInfo(),
    val google: GoogleStatus = GoogleStatus(),
    val voice: VoiceInfo = VoiceInfo(),
)

@Serializable
data class CallSettings(
    val enabled: Boolean = false,
    @SerialName("consent_at") val consentAt: String? = null,
    @SerialName("quiet_start") val quietStart: String = "22:00",
    @SerialName("quiet_end") val quietEnd: String = "08:00",
    /** Never the whole number: "+91 ••••• •3210", or null when there is none we may ring. */
    val phone: String? = null,
    /** False while the server has no ElevenLabs account: calls are recorded, not rung. */
    val live: Boolean = false,
    @SerialName("max_per_day") val maxPerDay: Int = 2,
    @SerialName("lead_minutes") val leadMinutes: Int = 120,
    @SerialName("max_seconds") val maxSeconds: Int = 90,
)

@Serializable
data class PushInfo(val wakeups: Boolean = false)

@Serializable
data class GoogleStatus(
    /** The server has a Google client; without one there is nothing to connect to. */
    val configured: Boolean = false,
    val connected: Boolean = false,
    val email: String? = null,
    @SerialName("connected_at") val connectedAt: String? = null,
    val gmail: Boolean = false,
    val calendar: Boolean = false,
    val classroom: Boolean = false,
    /** Linked, but Google stopped accepting it (7 days in Testing, or revoked): Settings asks
     * the student to connect again. Older servers don't send it. */
    @SerialName("needs_reconnect") val needsReconnect: Boolean = false,
)

@Serializable
data class VoiceInfo(
    val assistant: Boolean = false,
    @SerialName("briefing_audio") val briefingAudio: Boolean = false,
)

/** One urgent call (`GET /api/calls`): ids and outcomes, never a number or words. */
@Serializable
data class CallRecord(
    val id: Int = 0,
    /** placed, answered, missed, voicemail, failed or refused. */
    val status: String = "",
    val reason: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("duration_seconds") val durationSeconds: Int? = null,
    val title: String? = null,
    val subject: String? = null,
)

@Serializable
data class CallHistory(val calls: List<CallRecord> = emptyList())

/** `POST /api/calls/test`. */
@Serializable
data class CallOutcome(
    @SerialName("call_id") val callId: Int = 0,
    val status: String = "",
    val reason: String? = null,
)

/** `GET /api/briefing`: today, written by code from the student's own data. */
@Serializable
data class Briefing(
    val day: String = "",
    val greeting: String = "",
    val sections: List<BriefingSection> = emptyList(),
    val classes: List<ClassSlot> = emptyList(),
    /** The whole briefing as one text, what the voice reads. */
    val text: String = "",
    val audio: AudioInfo = AudioInfo(),
)

@Serializable
data class BriefingSection(val key: String = "", val title: String = "", val lines: List<String> = emptyList())

@Serializable
data class AudioInfo(val available: Boolean = false)

/** `GET /api/voice/session`: one conversation with the assistant. */
@Serializable
data class VoiceSession(
    val available: Boolean = false,
    val reason: String? = null,
    /** wss://… from ElevenLabs, good for one conversation. Never logged. */
    @SerialName("signed_url") val signedUrl: String? = null,
    @SerialName("dynamic_variables") val dynamicVariables: Map<String, String> = emptyMap(),
    /** The only tools the phone runs for the agent (each through the gateway). */
    val tools: List<String> = emptyList(),
    @SerialName("max_seconds") val maxSeconds: Int = 300,
)

/** `GET /api/notifications`: the outbox. */
@Serializable
data class Outbox(
    val notifications: List<OutboxMessage> = emptyList(),
    @SerialName("latest_id") val latestId: Int = 0,
)

@Serializable
data class OutboxMessage(
    val id: Int = 0,
    /** reminder or call (a call that couldn't ring became this message). */
    val kind: String = "reminder",
    val title: String = "",
    val body: String = "",
    @SerialName("item_id") val itemId: Int? = null,
    /** The reminder that fired (kind reminder): its alarm on this phone may have shown it already. */
    @SerialName("reminder_id") val reminderId: Int? = null,
    @SerialName("created_at") val createdAt: String? = null,
)

/** `POST /api/google/start`: Google's consent page, opened in the browser. */
@Serializable
data class GoogleStart(val url: String = "", @SerialName("expires_at") val expiresAt: String? = null)

@Serializable
data class GoogleDisconnect(val disconnected: Boolean = false, val google: GoogleStatus = GoogleStatus())

@Serializable
data class GoogleFinish(val connected: Boolean = false, val google: GoogleStatus = GoogleStatus())
