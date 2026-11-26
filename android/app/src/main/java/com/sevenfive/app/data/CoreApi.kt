package com.sevenfive.app.data

import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.put

/** 7even5ive core (port 8000): cards, approvals, and the gateway's tools. */
class CoreApi(private val http: Http, private val baseUrl: () -> String) {

    suspend fun cards(): Cards = AppJson.decodeFromString(cardsJson())

    /** The cards as the server sent them, so the last good answer can be kept on disk. */
    suspend fun cardsJson(): String = http.get("${baseUrl()}/api/cards")

    /** A material's file, as kept by the server. 404: none kept for this item. */
    suspend fun file(itemId: Int): ByteArray = http.bytes("${baseUrl()}/api/files/$itemId")

    /** Ask your semester: answered from the student's data through the gateway. */
    suspend fun ask(question: String): AskAnswer {
        val body = buildJsonObject { put("question", question) }
        return AppJson.decodeFromString(http.post("${baseUrl()}/api/ask", body.toString()))
    }

    /** Something shared into the app: filed as the student said, or by the cascade. */
    suspend fun share(body: JsonObject): ShareResult =
        AppJson.decodeFromString(http.post("${baseUrl()}/api/share", body.toString()))

    /** Runs one approval, once. A second tap answers 403 "approval already used". */
    suspend fun approve(token: String) {
        val body = buildJsonObject { put("token", token) }
        http.post("${baseUrl()}/api/approve", body.toString())
    }

    suspend fun tool(name: String, args: JsonObject = JsonObject(emptyMap())): ToolResponse {
        val body = buildJsonObject { put("args", args) }
        return AppJson.decodeFromString(http.post("${baseUrl()}/api/tools/$name", body.toString()))
    }

    suspend fun setReminder(itemId: Int, beforeMinutes: Int): SetReminderResult {
        val out = tool("set_reminder", buildJsonObject {
            put("item_id", itemId)
            put("before_minutes", beforeMinutes)
        })
        return out.result?.let { AppJson.decodeFromJsonElement<SetReminderResult>(it) } ?: SetReminderResult()
    }

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
