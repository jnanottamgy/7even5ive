package com.sevenfive.app.ui

import com.sevenfive.app.data.AppJson
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import java.io.File
import java.time.Duration
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit
import java.util.concurrent.CopyOnWriteArrayList

/**
 * The server's real answers, as recorded for the contract tests (src/test/resources/contract),
 * moved in time: they were recorded on a fixed demo morning (Monday 7 January 2030, 08:30 in
 * India), and every time in them is shifted by the same amount so that moment is now. What is
 * due in two days on the demo morning is due in two days on screen.
 */
internal object Recorded {
    private val dir = File(Recorded::class.java.getResource("/contract")!!.toURI())
    private val recordedAt = OffsetDateTime.parse("2030-01-07T08:30+05:30").toInstant()
    private val india = ZoneOffset.ofHoursMinutes(5, 30)
    private val stamp = Regex("""\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})""")

    val names: List<String> get() = dir.listFiles { f -> f.extension == "json" }!!.map { it.nameWithoutExtension }.sorted()

    fun exchange(name: String, now: Instant = Instant.now()): JsonObject {
        val shift = Duration.between(recordedAt, now.truncatedTo(ChronoUnit.MINUTES))
        val text = stamp.replace(File(dir, "$name.json").readText()) { m ->
            OffsetDateTime.parse(m.value).plus(shift).withOffsetSameInstant(india).toString()
        }
        return AppJson.parseToJsonElement(text).jsonObject
    }

    fun response(name: String): JsonElement = exchange(name)["response"]!!

    inline fun <reified T> model(name: String): T = AppJson.decodeFromJsonElement(response(name))
}

/**
 * A local server that answers as the real one did: each request gets the recorded answer for
 * its method and path. Where one route has several recordings (the cards before and after the
 * student did things; a library that is or isn't there), [routes] picks the one to serve.
 */
internal class RecordedServer(overrides: Map<String, String> = emptyMap()) : Dispatcher() {
    private val server = MockWebServer()
    val url: String
    val asked = CopyOnWriteArrayList<String>()
    private val routes: Map<String, String>

    init {
        // The plain recording of a route first; a variant (a refusal, the busier cards) only
        // where it is the route's one recording, or when the test asks for it.
        val variant = Regex("unavailable|refused|error|unsorted|quiet|busy|_note")
        val byRoute = mutableMapOf<String, String>()
        for (name in Recorded.names.sortedBy { variant.containsMatchIn(it) }) {
            val request = Recorded.exchange(name)["request"]!!.jsonObject
            val path = request["path"]!!.jsonPrimitive.content.substringBefore('?')
            byRoute.putIfAbsent("${request["method"]!!.jsonPrimitive.content} $path", name)
        }
        routes = byRoute + overrides
        server.dispatcher = this
        server.start()
        url = server.url("/").toString().trimEnd('/')
    }

    override fun dispatch(request: RecordedRequest): MockResponse {
        val route = "${request.method} ${request.path!!.substringBefore('?')}"
        asked += route
        val name = routes[route]
            ?: return MockResponse().setResponseCode(404).setBody("""{"detail":"Not in the recording: $route"}""")
        val recorded = Recorded.exchange(name)
        return MockResponse()
            .setResponseCode(recorded["status"]!!.jsonPrimitive.int)
            .setHeader("Content-Type", "application/json")
            .setBody(recorded["response"].toString())
    }

    fun close() = server.shutdown()
}
