package com.sevenfive.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * A failed call. [detail] is the server's own `detail`, shown to the student as it is
 * ("approval already used"). [code] is the machine code: PortMax's (`session_expired`) or the
 * core's (`profile_required`, `demo_account`, ...).
 */
class ApiException(val status: Int, val detail: String, val code: String? = null) : Exception(detail)

private val JSON_TYPE = "application/json; charset=utf-8".toMediaType()

/**
 * The one HTTP door. Deliberately no logging interceptor: requests carry the token and
 * responses carry message and mail text, and neither may reach logcat.
 *
 * The token comes from [tokens] for each request (the signed-in session, refreshed as needed,
 * or the demo's). When the server refuses it, [TokenSource.rejected] may hand over a fresh one
 * and the request is sent once more; never more than once.
 */
class Http(private val tokens: TokenSource) {
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        // A free online server sleeps when idle and takes up to a minute to wake: wait for it.
        .readTimeout(70, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    suspend fun get(url: String, auth: Boolean = true): String = text(url, null, auth)

    suspend fun post(url: String, json: String, auth: Boolean = true): String = text(url, json, auth)

    /** As exactly [bearer], once: no token source, no refresh, no retry. For the one last call
     * made for someone who is leaving ([Accounts.onSwitch]). */
    suspend fun postAs(url: String, json: String, bearer: String): String = send(url, json, bearer) { it.string() }

    /** A binary answer (the briefing's mp3). Same errors as [get]. */
    suspend fun getBytes(url: String): ByteArray = exchange(url, null, true) { it.bytes() }

    private suspend fun text(url: String, json: String?, auth: Boolean): String =
        exchange(url, json, auth) { it.string() }

    private suspend fun <T> exchange(
        url: String,
        json: String?,
        auth: Boolean,
        read: (okhttp3.ResponseBody) -> T,
    ): T {
        val first = if (auth) tokens.token() ?: throw ApiException(401, "Log in first.", "signed_out") else null
        return try {
            send(url, json, first, read)
        } catch (e: ApiException) {
            if (first == null || (e.status != 401 && e.status != 403)) throw e
            val again = tokens.rejected(first, e.status, e.code)
            if (again == null || again == first) throw e
            send(url, json, again, read)
        }
    }

    private suspend fun <T> send(url: String, json: String?, token: String?, read: (okhttp3.ResponseBody) -> T): T =
        withContext(Dispatchers.IO) {
            val builder = try {
                Request.Builder().url(url)
            } catch (e: IllegalArgumentException) {
                throw ApiException(0, "Bad server address: $url")
            }
            if (token != null) builder.header("Authorization", "Bearer $token")
            if (json != null) builder.post(json.toRequestBody(JSON_TYPE))
            val request = builder.build()
            try {
                client.newCall(request).execute().use { response ->
                    val body = response.body
                    if (!response.isSuccessful) throw errorFrom(response.code, body?.string().orEmpty())
                    if (body == null) throw ApiException(response.code, "Empty answer from the server")
                    read(body)
                }
            } catch (e: IOException) {
                throw ApiException(0, "Can't reach ${request.url.host}:${request.url.port}")
            }
        }

    private fun errorFrom(status: Int, body: String): ApiException {
        val parsed = runCatching { AppJson.parseToJsonElement(body) as JsonObject }.getOrNull()
        val detail = parsed?.get("detail")?.let { runCatching { it.jsonPrimitive.content }.getOrNull() }
        val code = parsed?.get("code")?.let { runCatching { it.jsonPrimitive.content }.getOrNull() }
        return ApiException(status, detail ?: "HTTP $status", code)
    }
}
