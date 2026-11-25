package com.sevenfive.app.data

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.put

/** 7even5ive core (port 8000): cards, approvals, and the gateway's tools. */
class CoreApi(private val http: Http, private val baseUrl: () -> String) {

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
}
