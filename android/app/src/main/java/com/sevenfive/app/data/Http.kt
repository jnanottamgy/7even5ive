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
 * ("approval already used"). [code] is PortMax's machine code (`session_expired`).
 */
class ApiException(val status: Int, val detail: String, val code: String? = null) : Exception(detail)

private val JSON_TYPE = "application/json; charset=utf-8".toMediaType()

/**
 * The one HTTP door. Deliberately no logging interceptor: requests carry the token and
 * responses carry message and mail text, and neither may reach logcat.
 */
class Http(private val token: String) {
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        // A free online server sleeps when idle and takes up to a minute to wake: wait for it.
        .readTimeout(70, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    suspend fun get(url: String, auth: Boolean = true): String = send(url, null, auth)

    suspend fun post(url: String, json: String): String = send(url, json, true)

    /** A file's bytes (GET, with the token). */
    suspend fun bytes(url: String): ByteArray = withContext(Dispatchers.IO) {
        val request = try {
            Request.Builder().url(url).header("Authorization", "Bearer $token").build()
        } catch (e: IllegalArgumentException) {
            throw ApiException(0, "Bad server address: $url")
        }
        try {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) throw errorFrom(response.code, response.body?.string().orEmpty())
                response.body?.bytes() ?: ByteArray(0)
            }
        } catch (e: IOException) {
            throw ApiException(0, "Can't reach ${request.url.host}:${request.url.port}")
        }
    }

    private suspend fun send(url: String, json: String?, auth: Boolean): String =
        withContext(Dispatchers.IO) {
            val builder = Request.Builder().url(url)
            if (auth) builder.header("Authorization", "Bearer $token")
            if (json != null) builder.post(json.toRequestBody(JSON_TYPE))
            val request = try {
                builder.build()
            } catch (e: IllegalArgumentException) {
                throw ApiException(0, "Bad server address: $url")
            }
            try {
                client.newCall(request).execute().use { response ->
                    val body = response.body?.string().orEmpty()
                    if (!response.isSuccessful) throw errorFrom(response.code, body)
                    body
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
