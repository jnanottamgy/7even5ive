package com.sevenfive.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Call
import okhttp3.EventListener
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.ResponseBody
import java.io.IOException
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.concurrent.TimeUnit
import kotlin.random.Random

/**
 * A failed call. [detail] is the server's own `detail`, shown to the student as it is
 * ("approval already used"). [code] is the machine code: PortMax's (`session_expired`) or the
 * core's (`profile_required`, `demo_account`, ...), or the app's own ([SERVER_BUSY], [BAD_ANSWER]).
 */
class ApiException(val status: Int, val detail: String, val code: String? = null) : Exception(detail) {
    /** The server was busy or failing (a 429 or 5xx without words of its own): worth asking again. */
    val busy: Boolean get() = code == SERVER_BUSY
}

/** [ApiException.code] of a 429 or 5xx that came without the server's own words (API Gateway's
 * `{"message": ...}`, a Lambda that crashed or timed out, a proxy's page). */
const val SERVER_BUSY = "server_busy"

/** [ApiException.code] of a successful answer this app couldn't read ([decodeAnswer]). */
const val BAD_ANSWER = "bad_answer"

/** What a tap that met a busy server says. */
const val BUSY_TRY_AGAIN = "Couldn't reach 7even5ive. Try again in a moment."

/** What the cards say meanwhile: they are asked for again by themselves every few seconds. */
const val BUSY_RETRYING = "7even5ive is busy. Trying again…"

/**
 * Reads a successful answer as [T]. One this app can't read (a server half-way through an
 * update, a captive portal's page, a field of an unexpected type) becomes an [ApiException] like
 * any other failure, so every caller's `catch (e: ApiException)` covers it and the app never
 * closes over it. Every answer the app decodes goes through here.
 */
inline fun <reified T> decodeAnswer(text: String): T = try {
    AppJson.decodeFromString<T>(text)
} catch (e: IllegalArgumentException) { // SerializationException is one
    throw unreadableAnswer()
}

/** [decodeAnswer] for a part of an answer already parsed (a tool's `result`). */
inline fun <reified T> decodeAnswer(element: JsonElement): T = try {
    AppJson.decodeFromJsonElement<T>(element)
} catch (e: IllegalArgumentException) {
    throw unreadableAnswer()
}

@PublishedApi
internal fun unreadableAnswer() =
    ApiException(502, "7even5ive sent an answer this app can't read. Try again, or update the app.", BAD_ANSWER)

private val JSON_TYPE = "application/json; charset=utf-8".toMediaType()

/**
 * The one HTTP door. Deliberately no logging interceptor: requests carry the token and
 * responses carry message and mail text, and neither may reach logcat.
 *
 * The token comes from [tokens] for each request (the signed-in session, refreshed as needed,
 * or the demo's). When the server refuses it, [TokenSource.rejected] may hand over a fresh one
 * and the request is sent once more; never more than once.
 *
 * A request that meets a busy server or a bad network is tried again by the rules in [Retry]:
 * reads (GET) on 429/500/502/503/504 and on network failures, anything else only when it never
 * left the phone. A failure is never a reason to sign anyone out.
 */
class Http(
    private val tokens: TokenSource,
    /** The wait between tries (tests record it instead of waiting). */
    private val pause: suspend (Long) -> Unit = { delay(it) },
    private val random: Random = Random.Default,
) {
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        // API Gateway gives up on the server after 30 seconds, so no answer comes after that. A
        // server that is still waking up (a free instance can take a minute) is met by the retry.
        .callTimeout(35, TimeUnit.SECONDS)
        // Tells each request whether it had started going out when it failed (see [Sent]).
        .eventListenerFactory { call -> call.request().tag(Sent::class.java)?.listener ?: EventListener.NONE }
        .build()

    suspend fun get(url: String, auth: Boolean = true): String = text(url, null, auth)

    suspend fun post(url: String, json: String, auth: Boolean = true): String = text(url, json, auth)

    /** As exactly [bearer], once: no token source, no refresh. For the one last call made for
     * someone who is leaving ([Accounts.onLeft]). */
    suspend fun postAs(url: String, json: String, bearer: String): String =
        sendRetrying(url, json, bearer) { it.string() }

    /** A binary answer (the briefing's mp3). Same errors as [get]. */
    suspend fun getBytes(url: String): ByteArray = exchange(url, null, true) { it.bytes() }

    private suspend fun text(url: String, json: String?, auth: Boolean): String =
        exchange(url, json, auth) { it.string() }

    private suspend fun <T> exchange(
        url: String,
        json: String?,
        auth: Boolean,
        read: (ResponseBody) -> T,
    ): T {
        val first = if (auth) tokens.token() ?: throw ApiException(401, "Log in first.", "signed_out") else null
        return try {
            sendRetrying(url, json, first, read)
        } catch (e: ApiException) {
            if (first == null || (e.status != 401 && e.status != 403)) throw e
            val again = tokens.rejected(first, e.status, e.code)
            if (again == null || again == first) throw e
            sendRetrying(url, json, again, read)
        }
    }

    /** One request, tried again while [Retry] says so. Only a GET is idempotent here: every
     * POST changes something, or might. */
    private suspend fun <T> sendRetrying(url: String, json: String?, token: String?, read: (ResponseBody) -> T): T {
        var retry = 0
        while (true) {
            val failed = try {
                return send(url, json, token, read)
            } catch (e: Failed) {
                e
            }
            retry++
            val wait = Retry.wait(retry, idempotent = json == null, failed.error.status, failed.sent, failed.retryAfterMillis, random)
                ?: throw failed.error
            pause(wait)
        }
    }

    private suspend fun <T> send(url: String, json: String?, token: String?, read: (ResponseBody) -> T): T =
        withContext(Dispatchers.IO) {
            val sent = Sent()
            val builder = try {
                Request.Builder().url(url)
            } catch (e: IllegalArgumentException) {
                throw ApiException(0, "Bad server address: $url")
            }
            builder.tag(Sent::class.java, sent)
            if (token != null) builder.header("Authorization", "Bearer $token")
            if (json != null) builder.post(json.toRequestBody(JSON_TYPE))
            val request = builder.build()
            try {
                client.newCall(request).execute().use { response ->
                    if (!response.isSuccessful) {
                        val error = errorFrom(response.code, response.body?.string().orEmpty())
                        throw Failed(error, sent = true, retryAfterMillis = Retry.afterMillis(response.header("Retry-After")))
                    }
                    read(response.body ?: throw ApiException(response.code, "Empty answer from the server"))
                }
            } catch (e: IOException) {
                throw Failed(ApiException(0, "Can't reach ${request.url.host}:${request.url.port}"), sent.started, null)
            }
        }

    private fun errorFrom(status: Int, body: String): ApiException {
        val parsed = runCatching { AppJson.parseToJsonElement(body) as JsonObject }.getOrNull()
        fun field(name: String) =
            parsed?.get(name)?.let { runCatching { it.jsonPrimitive.contentOrNull }.getOrNull() }?.takeIf { it.isNotBlank() }
        val code = field("code")
        // The core's own words (FastAPI's `detail`) say exactly what happened: shown as they are.
        field("detail")?.let { return ApiException(status, it, code) }
        // A busy or failing server says nothing useful ("Internal server error", "Service Unavailable").
        if (status == 429 || status >= 500) return ApiException(status, BUSY_TRY_AGAIN, code ?: SERVER_BUSY)
        // API Gateway's own refusals carry only `message`.
        return ApiException(status, field("message") ?: "Something went wrong (HTTP $status). Try again.", code)
    }

    /** One try that failed, with what the retry rules need. Never leaves this class. */
    private class Failed(val error: ApiException, val sent: Boolean, val retryAfterMillis: Long?) : Exception()

    /** Whether a request had started going out (its headers being written) when it failed. Before
     * that, the server can't have seen it, and sending it again is safe whatever it does. */
    private class Sent {
        @Volatile var started = false
        val listener = object : EventListener() {
            override fun requestHeadersStart(call: Call) {
                started = true
            }
        }
    }
}

/** When a failed request is sent again. Pure, so the rules are tested on their own. */
object Retry {
    /** At most this many more tries after the first. */
    const val MAX_RETRIES = 2

    /** A Retry-After longer than this is honoured by not trying again now at all. */
    const val MAX_WAIT_MILLIS = 3_000L

    /** A server that is busy, failing, or behind a gateway that gave up on it. */
    val STATUSES = setOf(429, 500, 502, 503, 504)

    private val BACKOFF_MILLIS = longArrayOf(500L, 1_500L)

    /**
     * How long to wait before retry number [retry] (1 is the first retry), or null to give up.
     * [status] 0 is a network failure (no answer); [sent] whether the request had started going
     * out. A request that is not [idempotent] (a POST) is only sent again when it never left.
     */
    fun wait(retry: Int, idempotent: Boolean, status: Int, sent: Boolean, retryAfterMillis: Long?, random: Random): Long? {
        if (retry !in 1..MAX_RETRIES) return null
        val again = when {
            status == 0 -> idempotent || !sent
            status in STATUSES -> idempotent
            else -> false
        }
        if (!again) return null
        if (retryAfterMillis != null) return retryAfterMillis.takeIf { it <= MAX_WAIT_MILLIS }
        val base = BACKOFF_MILLIS[retry - 1]
        return base + random.nextLong(-base / 4, base / 4 + 1) // about 0.5 s, then about 1.5 s
    }

    /** A Retry-After header in milliseconds: delta-seconds or an HTTP date. Null when absent or unreadable. */
    fun afterMillis(header: String?, now: Long = System.currentTimeMillis()): Long? {
        val value = header?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        value.toLongOrNull()?.let { return (it * 1000).coerceAtLeast(0) }
        val at = runCatching { ZonedDateTime.parse(value, DateTimeFormatter.RFC_1123_DATE_TIME) }.getOrNull() ?: return null
        return (at.toInstant().toEpochMilli() - now).coerceAtLeast(0)
    }
}
