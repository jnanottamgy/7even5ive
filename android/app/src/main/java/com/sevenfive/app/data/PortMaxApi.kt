package com.sevenfive.app.data

import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** PortMax (port 8002): the connector's settings, the runner script, and the page upload. */
class PortMaxApi(private val http: Http, private val baseUrl: () -> String) {
    private var runnerCache: String? = null
    private var connectorCache: Pair<String, Connector>? = null

    suspend fun connector(college: String): Connector {
        connectorCache?.let { (key, value) -> if (key == cacheKey(college)) return value }
        val raw = http.get("${baseUrl()}/v1/connectors/$college")
        val info = try {
            AppJson.decodeFromString<ConnectorInfo>(raw)
        } catch (e: IllegalArgumentException) { // SerializationException is one
            // Say what came back: settings hold no secrets, and a wrong server shows itself here.
            val start = raw.take(120).replace(Regex("\\s+"), " ")
            throw ApiException(0, "PortMax sent settings this app can't read: \"$start\" (${e.message?.take(160)})")
        }
        val connector = Connector(info, raw)
        connectorCache = cacheKey(college) to connector
        return connector
    }

    /** The runner is the same file for every college; fetched once per server. */
    suspend fun runnerJs(): String =
        runnerCache ?: http.get("${baseUrl()}/v1/runner.js", auth = false).also { runnerCache = it }

    /** The pages are parsed and dropped on the server; only the answers are kept. */
    suspend fun upload(college: String, pagesJson: String): PagesResult {
        val pages = AppJson.parseToJsonElement(pagesJson) as JsonArray
        val body = buildJsonObject {
            put("college", college)
            put("pages", pages)
        }
        return decodeAnswer(http.post("${baseUrl()}/v1/pages", body.toString()))
    }

    fun forget() {
        runnerCache = null
        connectorCache = null
    }

    private fun cacheKey(college: String) = "${baseUrl()}|$college"
}
