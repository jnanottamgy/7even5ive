package com.sevenfive.app.data

import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.put

/** 7even5ive core (port 8000): cards, approvals, and the gateway's tools. */
class CoreApi(private val http: Http, val baseUrl: () -> String) {

    suspend fun cards(): Cards = AppJson.decodeFromString(http.get("${baseUrl()}/api/cards"))

    /** Runs one approval, once. A second tap answers 403 "approval already used". */
    suspend fun approve(token: String) {
        val body = buildJsonObject { put("token", token) }
        http.post("${baseUrl()}/api/approve", body.toString())
    }

    suspend fun tool(name: String, args: JsonObject = JsonObject(emptyMap())): ToolResponse {
        val body = buildJsonObject { put("args", args) }
        return AppJson.decodeFromString(http.post("${baseUrl()}/api/tools/$name", body.toString()))
    }

    /** [channel] push (a notification) or call (the opt-in urgent call). */
    suspend fun setReminder(itemId: Int, beforeMinutes: Int, channel: String = "push"): SetReminderResult {
        val out = tool("set_reminder", buildJsonObject {
            put("item_id", itemId)
            put("before_minutes", beforeMinutes)
            put("channel", channel)
        })
        return out.result?.let { AppJson.decodeFromJsonElement<SetReminderResult>(it) } ?: SetReminderResult()
    }

    suspend fun markDone(itemId: Int) {
        tool("mark_done", buildJsonObject { put("item_id", itemId) })
    }

    suspend fun reopen(itemId: Int) {
        tool("reopen", buildJsonObject { put("item_id", itemId) })
    }

    /**
     * One tool for the voice assistant, through the same gateway as every tap: the raw answer as
     * JSON text, which the agent reads. A refusal throws [ApiException] with the gateway's reason.
     */
    suspend fun toolText(name: String, args: JsonObject): String {
        val body = buildJsonObject { put("args", args) }
        return http.post("${baseUrl()}/api/tools/$name", body.toString())
    }

    // --- settings, the urgent call ---------------------------------------------------------------
    suspend fun settings(): AppSettings = AppJson.decodeFromString(http.get("${baseUrl()}/api/settings"))

    suspend fun setCalls(enabled: Boolean? = null, quietStart: String? = null, quietEnd: String? = null): CallSettings {
        val body = buildJsonObject {
            if (enabled != null) put("enabled", enabled)
            if (quietStart != null) put("quiet_start", quietStart)
            if (quietEnd != null) put("quiet_end", quietEnd)
        }
        return AppJson.decodeFromString(http.post("${baseUrl()}/api/settings/calls", body.toString()))
    }

    suspend fun callHistory(): CallHistory = AppJson.decodeFromString(http.get("${baseUrl()}/api/calls"))

    suspend fun testCall(): CallOutcome = AppJson.decodeFromString(http.post("${baseUrl()}/api/calls/test", "{}"))

    // --- briefing and voice ------------------------------------------------------------------------
    suspend fun briefing(): Briefing = AppJson.decodeFromString(http.get("${baseUrl()}/api/briefing"))

    /** ElevenLabs' mp3 of today's briefing. 503 (with the reason) when the server has no voice. */
    suspend fun briefingAudio(): ByteArray = http.getBytes("${baseUrl()}/api/briefing/audio")

    suspend fun voiceSession(): VoiceSession = AppJson.decodeFromString(http.get("${baseUrl()}/api/voice/session"))

    // --- the outbox and wake-ups ------------------------------------------------------------------
    suspend fun notifications(after: Int): Outbox =
        AppJson.decodeFromString(http.get("${baseUrl()}/api/notifications?after=$after"))

    suspend fun registerDevice(token: String) {
        http.post("${baseUrl()}/api/devices", buildJsonObject {
            put("token", token)
            put("platform", "android")
        }.toString())
    }

    // --- Google and college mail -------------------------------------------------------------------
    suspend fun googleStart(): GoogleStart = AppJson.decodeFromString(http.post("${baseUrl()}/api/google/start", "{}"))

    /** Back from Google: the app, with its own token, hands over the code (google.py). */
    suspend fun googleFinish(code: String, state: String): GoogleFinish {
        val body = buildJsonObject {
            put("code", code)
            put("state", state)
        }
        return AppJson.decodeFromString(http.post("${baseUrl()}/api/google/finish", body.toString()))
    }

    suspend fun googleDisconnect(): GoogleDisconnect =
        AppJson.decodeFromString(http.post("${baseUrl()}/api/google/disconnect", "{}"))

    /** "Check now": 429 with the reason when the last check was under five minutes ago. */
    suspend fun checkMail(): MailCheckResult = AppJson.decodeFromString(http.post("${baseUrl()}/api/mail/check", "{}"))

    suspend fun cancelReminder(reminderId: Int) {
        tool("cancel_reminder", buildJsonObject { put("reminder_id", reminderId) })
    }

    /** Demo server only: a WhatsApp event sent through the real signed webhook (cloud.py). */
    suspend fun demoForward(kind: String): DemoForward =
        AppJson.decodeFromString(http.post("${baseUrl()}/demo/forward/$kind", "{}"))

    /** Demo server only: back to the demo morning, with a fresh mock portal. */
    suspend fun demoReset() {
        http.post("${baseUrl()}/demo/reset", "{}")
    }

    // --- accounts (the sign-in itself is Supabase's: SupabaseAuth) ------------------------------
    /** How this server's students sign in. No token needed. */
    suspend fun authConfig(): AuthConfig =
        AppJson.decodeFromString(http.get("${baseUrl()}/api/auth/config", auth = false))

    suspend fun usernameCheck(username: String): UsernameCheck {
        val q = java.net.URLEncoder.encode(username, "UTF-8")
        return AppJson.decodeFromString(http.get("${baseUrl()}/api/auth/username?u=$q", auth = false))
    }

    /** A username sign-in: the server answers with Supabase's own session JSON. */
    suspend fun loginWithUsername(username: String, password: String): String {
        val body = buildJsonObject {
            put("login", username)
            put("password", password)
        }
        return http.post("${baseUrl()}/api/auth/login", body.toString(), auth = false)
    }

    suspend fun me(): Me = AppJson.decodeFromString(http.get("${baseUrl()}/api/me"))

    suspend fun saveProfile(form: ProfileForm): Me =
        AppJson.decodeFromString(http.post("${baseUrl()}/api/me", form.toJson().toString()))

    /** Every row, the mail read, the portal answers, then the login itself. */
    suspend fun deleteAccount() {
        http.post("${baseUrl()}/api/me/delete", buildJsonObject { put("confirm", "DELETE") }.toString())
    }

    suspend fun newPersonalToken(): PersonalToken =
        AppJson.decodeFromString(http.post("${baseUrl()}/api/me/token", "{}"))

    suspend fun deletePersonalToken() {
        http.post("${baseUrl()}/api/me/token/delete", "{}")
    }

    suspend fun linkWhatsApp(): WhatsAppLink = AppJson.decodeFromString(http.post("${baseUrl()}/api/me/whatsapp", "{}"))

    suspend fun unlinkWhatsApp(): Me = AppJson.decodeFromString(http.post("${baseUrl()}/api/me/whatsapp/delete", "{}"))

    /** This phone stops being woken for the student signing out, as them ([bearer]). */
    suspend fun removeDeviceAs(bearer: String, token: String) {
        http.postAs("${baseUrl()}/api/devices/remove", buildJsonObject { put("token", token) }.toString(), bearer)
    }

    /** The status a request with no token gets (the gateway's 401). */
    suspend fun statusWithoutToken(): Int = try {
        http.get("${baseUrl()}/api/cards", auth = false)
        200
    } catch (e: ApiException) {
        e.status
    }

    /** How long the server takes to answer its health check, in milliseconds. */
    suspend fun healthMillis(): Long {
        val start = System.nanoTime()
        http.get("${baseUrl()}/api/health", auth = false)
        return (System.nanoTime() - start) / 1_000_000
    }
}
