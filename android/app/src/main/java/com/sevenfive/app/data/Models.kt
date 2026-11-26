package com.sevenfive.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive

/** Lenient on purpose: the backend is still growing, and a new field must never crash the app. */
val AppJson = Json {
    ignoreUnknownKeys = true
    coerceInputValues = true
    explicitNulls = false
    encodeDefaults = true
}

/** `GET /api/cards`: everything every screen needs, in one call. */
@Serializable
data class Cards(
    val student: Student? = null,
    @SerialName("due_this_week") val dueThisWeek: List<Item> = emptyList(),
    val attendance: Attendance = Attendance(),
    val materials: List<Item> = emptyList(),
    val opportunities: List<Item> = emptyList(),
    val filtered: Int = 0,
    @SerialName("needs_review") val needsReview: List<Item> = emptyList(),
    val approvals: List<Approval> = emptyList(),
    val reminders: List<Reminder> = emptyList(),
    /** Today's classes from the portal's timetable, in order. */
    @SerialName("classes_today") val classesToday: List<ClassSlot> = emptyList(),
    /** The college mailbox: demo or Gmail, when it was checked, how many mails were left out. */
    val mail: MailStatus = MailStatus(),
) {
    /** Approvals only carry `item_id`; the title comes from the cards we already have. */
    fun itemById(id: Int?): Item? =
        if (id == null) null
        else (dueThisWeek + opportunities + materials + needsReview).firstOrNull { it.id == id }
}

@Serializable
data class Student(
    val id: Int = 0,
    val name: String = "",
    val branch: String? = null,
    val year: Int? = null,
    val interests: String? = null,
)

/** One filed thing: a deadline, exam, material, event or notice. */
@Serializable
data class Item(
    val id: Int = 0,
    val kind: String = "",
    val subject: String? = null,
    val title: String? = null,
    @SerialName("due_at") val dueAt: String? = null,
    val status: String? = null,
    val source: String? = null,
    val route: String? = null,
    val relevance: Double? = null,
    /** College-mail cards only (route "mail"): placement, internship or exam_notice. */
    val category: String? = null,
    val organisation: String? = null,
    val role: String? = null,
    /** The form to register or apply (https, checked to be in the mail). */
    val link: String? = null,
    /** Opens the mail itself in Gmail. */
    @SerialName("mail_link") val mailLink: String? = null,
    /** One plain sentence, written by code. */
    val summary: String? = null,
    /** The drive, test or exam itself, when [dueAt] is the deadline to register. */
    @SerialName("event_at") val eventAt: String? = null,
) {
    val fromMail: Boolean get() = route == "mail"
}

@Serializable
data class Attendance(
    val connected: Boolean = false,
    val stale: Boolean = false,
    @SerialName("fetched_at") val fetchedAt: String? = null,
    val subjects: List<SubjectAttendance> = emptyList(),
)

@Serializable
data class SubjectAttendance(
    @SerialName("subject_code") val code: String = "",
    @SerialName("subject_name") val name: String = "",
    val attended: Int = 0,
    val held: Int = 0,
    val percent: Double = 0.0,
    @SerialName("minimum_percent") val minimumPercent: Double = 75.0,
    /** safe | at_risk | short | unrecoverable */
    val status: String = "safe",
    @SerialName("can_skip_now") val canSkipNow: Int = 0,
    @SerialName("must_attend") val mustAttend: Int = 0,
    @SerialName("next_classes") val nextClasses: List<String> = emptyList(),
    val semester: Semester? = null,
    /** Exact, written by code, not a model: shown as it is. */
    val message: String = "",
)

@Serializable
data class Semester(
    val planned: Int? = null,
    val remaining: Int? = null,
    @SerialName("can_skip_rest_of_semester") val canSkipRest: Int? = null,
    @SerialName("best_final_percent") val bestFinalPercent: Double? = null,
)

@Serializable
data class Approval(
    val action: String = "",
    val args: JsonObject = JsonObject(emptyMap()),
    /** Sent back to /api/approve exactly as received. Never logged. */
    val token: String = "",
) {
    val itemId: Int? get() = args["item_id"]?.jsonPrimitive?.intOrNull
}

@Serializable
data class Reminder(
    @SerialName("reminder_id") val id: Int = 0,
    @SerialName("fires_at") val firesAt: String? = null,
    val title: String? = null,
    val subject: String? = null,
    @SerialName("due_at") val dueAt: String? = null,
    @SerialName("item_id") val itemId: Int? = null,
    /** push (a notification) or call (the opt-in urgent call). */
    val channel: String = "push",
) {
    val isCall: Boolean get() = channel == "call"
}

@Serializable
data class ToolResponse(
    val status: String = "",
    val result: JsonElement? = null,
    val message: String? = null,
)

@Serializable
data class SetReminderResult(
    @SerialName("reminder_id") val id: Int = 0,
    @SerialName("fires_at") val firesAt: String? = null,
    val title: String? = null,
    val channel: String = "push",
)

/** The demo server's answer to a tour action (`POST /demo/forward/{kind}`). */
@Serializable
data class DemoForward(
    val kind: String = "",
    @SerialName("webhook_status") val webhookStatus: Int = 0,
    /** The card the event became, if it was filed. */
    val filed: Item? = null,
)

/** `POST /v1/pages` answer. */
@Serializable
data class PagesResult(
    @SerialName("fetched_at") val fetchedAt: String? = null,
    val saved: JsonElement? = null,
    val failed: JsonElement? = null,
)

/** The parts of the PortMax connector settings the app itself reads. The runner gets the raw object. */
@Serializable
data class ConnectorInfo(
    val college: String = "",
    val name: String = "",
    @SerialName("login_path") val loginPath: String = "/",
    val markers: JsonObject = JsonObject(emptyMap()),
    @SerialName("keepalive_minutes") val keepaliveMinutes: Double = 15.0,
    /** A float in PortMax's manifest: 180 or 180.0 must both read. */
    @SerialName("refresh_minutes") val refreshMinutes: Double = 180.0,
)

/** A connector's settings: the typed view plus the exact JSON to hand the runner unchanged. */
data class Connector(val info: ConnectorInfo, val raw: String)

