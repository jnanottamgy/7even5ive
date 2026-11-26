package com.sevenfive.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

/** `GET /api/auth/config`: how this server's students sign in. Nothing in it is secret. */
@Serializable
data class AuthConfig(
    val enabled: Boolean = false,
    @SerialName("supabase_url") val supabaseUrl: String? = null,
    /** Supabase's publishable key: made to ship in apps; row level security guards the data. */
    @SerialName("publishable_key") val publishableKey: String? = null,
    @SerialName("username_login") val usernameLogin: Boolean = false,
    @SerialName("delete_account") val deleteAccount: Boolean = false,
    @SerialName("password_min_length") val passwordMinLength: Int = 8,
    val demo: Boolean = true,
) {
    val usable: Boolean get() = enabled && !supabaseUrl.isNullOrBlank() && !publishableKey.isNullOrBlank()
}

/**
 * A signed-in session: kept encrypted on the phone (SessionStore), never logged. [project] and
 * [key] say which Supabase project issued it, so it is always refreshed there.
 */
@Serializable
data class Session(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    /** When the access token expires, in epoch seconds. */
    @SerialName("expires_at") val expiresAt: Long,
    @SerialName("user_id") val userId: String,
    val email: String? = null,
    val project: String,
    val key: String,
)

@Serializable
data class TokenInfo(val exists: Boolean = false, @SerialName("created_at") val createdAt: String? = null)

/** The student's profile (`/api/me`): never the whole phone number, never a token. */
@Serializable
data class Profile(
    val username: String? = null,
    val name: String? = null,
    val email: String? = null,
    val college: String? = null,
    val branch: String? = null,
    val year: Int? = null,
    val interests: String? = null,
    val subjects: List<String> = emptyList(),
    /** "+91 ••••• •3210" once WhatsApp is linked. */
    val whatsapp: String? = null,
    @SerialName("personal_token") val personalToken: TokenInfo = TokenInfo(),
    val demo: Boolean = false,
)

@Serializable
data class Me(
    val onboarded: Boolean = false,
    val email: String? = null,
    val profile: Profile? = null,
    val demo: Boolean = false,
)

@Serializable
data class UsernameCheck(val username: String = "", val available: Boolean = false, val message: String? = null)

/** A new personal token for an MCP client: shown once, never stored by the app. */
@Serializable
data class PersonalToken(
    val token: String = "",
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("mcp_url") val mcpUrl: String = "",
)

/** `GET /api/me/connections`: the MCP address, and the AI apps signed in to it (the demo has none). */
@Serializable
data class McpConnections(
    @SerialName("mcp_url") val mcpUrl: String = "",
    val connections: List<McpConnection> = emptyList(),
)

/** One AI app (Claude Code, Codex) the student signed in to with OAuth. Times are ISO, +05:30. */
@Serializable
data class McpConnection(
    val id: Int = 0,
    /** The name the app gave itself; null when it gave none. */
    val name: String? = null,
    @SerialName("connected_at") val connectedAt: String? = null,
    /** Null until the app first uses the connection. */
    @SerialName("last_used_at") val lastUsedAt: String? = null,
) {
    /** What the list calls it. */
    val label: String get() = name?.takeIf { it.isNotBlank() } ?: "An AI app"
}

/** `POST /api/me/connections/{id}/delete`. */
@Serializable
data class Disconnected(val deleted: Boolean = false)

/** Where the last sign-in settings are remembered, with the server they came from, so a
 * signed-in app can open without asking for them again ([Accounts.hasConfigFor]). */
interface ConfigCache {
    fun load(): Pair<String, AuthConfig>?
    fun save(server: String, config: AuthConfig)
}

/** `POST /api/me/whatsapp`: the code to send to the bot. */
@Serializable
data class WhatsAppLink(
    val code: String = "",
    @SerialName("expires_at") val expiresAt: String? = null,
    val message: String = "",
    @SerialName("bot_number") val botNumber: String? = null,
    val link: String? = null,
)

/** What the profile form sends. Null fields are left as they are, except the year when
 * [sendYear] is set (the edit form sends it always, so it can be cleared). */
data class ProfileForm(
    val username: String? = null,
    val name: String? = null,
    val college: String? = null,
    val branch: String? = null,
    val year: Int? = null,
    val interests: String? = null,
    val subjects: List<String>? = null,
    val sendYear: Boolean = false,
)

// --- Supabase Auth's own answers ------------------------------------------------------------------
@Serializable
internal data class SupabaseIdentity(val id: String? = null, val provider: String? = null)

@Serializable
internal data class SupabaseUser(
    val id: String = "",
    val email: String? = null,
    val identities: List<SupabaseIdentity>? = null,
)

/** /token and /verify answer with tokens and a user; /signup with confirmation on, with the user. */
@Serializable
internal data class SupabaseAnswer(
    @SerialName("access_token") val accessToken: String? = null,
    @SerialName("refresh_token") val refreshToken: String? = null,
    @SerialName("expires_in") val expiresIn: Long? = null,
    @SerialName("expires_at") val expiresAt: Long? = null,
    val user: SupabaseUser? = null,
    val id: String? = null,
    val email: String? = null,
    val identities: List<SupabaseIdentity>? = null,
)

sealed interface SignUpResult {
    /** Email confirmation is off in the project: signed in already. */
    data class SignedIn(val session: Session) : SignUpResult

    /** The usual case: Supabase emailed a code to [email]. */
    data class CodeSent(val email: String) : SignUpResult
}

private val JSON_TYPE = "application/json; charset=utf-8".toMediaType()

/**
 * Supabase Auth's REST API, called straight from the phone with the project's publishable key.
 * Why from the phone: Supabase limits sign-ins per IP address, so each student's own address
 * counts, not the server's. Codes, not links: the emails carry a 6-digit code (see
 * docs/supabase.md for the two templates), so no browser round trip is needed.
 * Failures are [ApiException]s whose detail is a sentence for the student.
 */
class SupabaseAuth(private val client: OkHttpClient, private val now: () -> Long = { System.currentTimeMillis() / 1000 }) {

    suspend fun signUp(config: AuthConfig, email: String, password: String): SignUpResult {
        val body = buildJsonObject {
            put("email", email)
            put("password", password)
        }
        val answer = call(config, "signup", body)
        if (answer.accessToken != null) return SignUpResult.SignedIn(session(config, answer))
        // An address that already has an account gets a stand-in user with no identities (so
        // that sign-up can't be used to find out who has an account) and no email is sent.
        if (answer.identities != null && answer.identities.isEmpty()) {
            throw ApiException(400, "That email already has an account. Log in, or reset your password.", "user_already_exists")
        }
        return SignUpResult.CodeSent(email)
    }

    suspend fun verifySignUp(config: AuthConfig, email: String, code: String): Session =
        session(config, call(config, "verify", buildJsonObject {
            put("type", "signup")
            put("email", email)
            put("token", code)
        }))

    suspend fun resendSignUpCode(config: AuthConfig, email: String) {
        call(config, "resend", buildJsonObject {
            put("type", "signup")
            put("email", email)
        })
    }

    suspend fun signIn(config: AuthConfig, email: String, password: String): Session =
        session(config, call(config, "token?grant_type=password", buildJsonObject {
            put("email", email)
            put("password", password)
        }))

    /** A new session for this one: refresh tokens work once (Supabase rotates them). */
    suspend fun refresh(session: Session): Session {
        val config = AuthConfig(enabled = true, supabaseUrl = session.project, publishableKey = session.key)
        return session(config, call(config, "token?grant_type=refresh_token", buildJsonObject {
            put("refresh_token", session.refreshToken)
        }))
    }

    /** Always answers the same, whether or not the address has an account. */
    suspend fun sendPasswordCode(config: AuthConfig, email: String) {
        call(config, "recover", buildJsonObject { put("email", email) })
    }

    suspend fun verifyPasswordCode(config: AuthConfig, email: String, code: String): Session =
        session(config, call(config, "verify", buildJsonObject {
            put("type", "recovery")
            put("email", email)
            put("token", code)
        }))

    suspend fun setPassword(session: Session, password: String) {
        val config = AuthConfig(enabled = true, supabaseUrl = session.project, publishableKey = session.key)
        call(config, "user", buildJsonObject { put("password", password) }, method = "PUT", bearer = session.accessToken)
    }

    /** Ends this session at Supabase (its refresh token stops working). Best effort. */
    suspend fun signOut(session: Session) {
        val config = AuthConfig(enabled = true, supabaseUrl = session.project, publishableKey = session.key)
        try {
            call(config, "logout?scope=local", JsonObject(emptyMap()), bearer = session.accessToken)
        } catch (e: ApiException) {
            // Signed out on this phone either way; an expired session is already over.
        }
    }

    /** A username sign-in comes back from our server as Supabase's own answer. */
    fun sessionFrom(config: AuthConfig, raw: String): Session =
        session(config, decodeAnswer<SupabaseAnswer>(raw))

    private fun session(config: AuthConfig, answer: SupabaseAnswer): Session {
        val access = answer.accessToken
        val refresh = answer.refreshToken
        val user = answer.user
        if (access.isNullOrBlank() || refresh.isNullOrBlank() || user == null || user.id.isBlank()) {
            throw ApiException(502, "The sign-in service sent an answer this app can't use. Try again.", "bad_answer")
        }
        val expires = answer.expiresAt ?: (now() + (answer.expiresIn ?: 3600))
        return Session(access, refresh, expires, user.id, user.email, config.supabaseUrl!!.trimEnd('/'), config.publishableKey!!)
    }

    private suspend fun call(
        config: AuthConfig,
        path: String,
        body: JsonObject,
        method: String = "POST",
        bearer: String? = null,
    ): SupabaseAnswer = withContext(Dispatchers.IO) {
        if (!config.usable) throw ApiException(503, "Accounts aren't set up on this server yet.", "auth_unavailable")
        val url = "${config.supabaseUrl!!.trimEnd('/')}/auth/v1/$path".toHttpUrlOrNull()
            ?: throw ApiException(0, "The sign-in address is wrong: ${config.supabaseUrl}")
        val builder = Request.Builder().url(url)
            .header("apikey", config.publishableKey!!)
            .method(method, body.toString().toRequestBody(JSON_TYPE))
        if (bearer != null) builder.header("Authorization", "Bearer $bearer")
        try {
            client.newCall(builder.build()).execute().use { response ->
                val text = response.body?.string().orEmpty()
                if (!response.isSuccessful) throw problem(response.code, text)
                if (text.isBlank()) SupabaseAnswer() else AppJson.decodeFromString<SupabaseAnswer>(text)
            }
        } catch (e: IOException) {
            throw ApiException(0, "Can't reach the sign-in service. Check your connection.")
        } catch (e: kotlinx.serialization.SerializationException) {
            throw ApiException(502, "The sign-in service sent an answer this app can't use. Try again.", "bad_answer")
        }
    }

    companion object {
        /** Supabase's error codes, said the way a student would want to hear them. */
        fun problem(status: Int, body: String): ApiException {
            val json = runCatching { AppJson.parseToJsonElement(body) as JsonObject }.getOrNull()
            fun field(name: String) = json?.get(name)?.let { runCatching { it.jsonPrimitive.content }.getOrNull() }
            val code = field("error_code") ?: field("error") ?: ""
            val said = field("msg") ?: field("error_description") ?: field("message")
            val detail = when (code) {
                "invalid_credentials", "invalid_grant" ->
                    if (said?.contains("refresh", ignoreCase = true) == true) "Your session ended. Log in again."
                    else "Wrong email or password."
                "email_not_confirmed" -> "Confirm your email first: enter the code we sent you."
                "user_already_exists", "email_exists" -> "That email already has an account. Log in, or reset your password."
                "weak_password" -> "Choose a stronger password: at least 8 characters, not a common one."
                "same_password" -> "Choose a password you haven't used here before."
                "otp_expired" -> "That code is wrong or has expired. Send a new one."
                "otp_disabled", "signup_disabled", "email_provider_disabled" -> "Signing up with email is turned off for this app."
                "over_email_send_rate_limit" -> "Too many emails just now. Wait a minute, then try again."
                "over_request_rate_limit" -> "Too many tries. Wait a minute, then try again."
                "email_address_invalid", "validation_failed" -> "Check the email address."
                "refresh_token_not_found", "refresh_token_already_used", "session_not_found", "session_expired",
                "bad_jwt", "user_not_found" -> "Your session ended. Log in again."
                "user_banned" -> "This account has been suspended."
                else -> when {
                    status == 429 -> "Too many tries. Wait a minute, then try again."
                    status >= 500 -> "The sign-in service isn't answering. Try again in a moment."
                    else -> said ?: "Couldn't do that (HTTP $status)."
                }
            }
            return ApiException(status, detail, code.ifBlank { null })
        }

        /** Supabase's own words for "this session is over" (the current error codes, and the
         * older `invalid_grant`). Nothing else ends a session: a 401 for a rotated API key, or a
         * 403 page from Supabase's edge, is a problem to retry, not a reason to sign out. */
        private val ENDED = setOf(
            "refresh_token_not_found", "refresh_token_already_used", "session_not_found",
            "session_expired", "user_not_found", "user_banned", "invalid_grant",
        )

        /** A session that the refresh endpoint refused for good: sign in again. */
        fun ended(e: ApiException): Boolean = e.status in 400..403 && e.code in ENDED
    }
}

/** For the profile form: only the fields set are sent. */
fun ProfileForm.toJson(): JsonObject = buildJsonObject {
    username?.let { put("username", it) }
    name?.let { put("name", it) }
    college?.let { put("college", it) }
    branch?.let { put("branch", it) }
    if (year != null) put("year", year) else if (sendYear) put("year", JsonNull)
    interests?.let { put("interests", it) }
    subjects?.let { list -> put("subjects", JsonArray(list.map { JsonPrimitive(it) })) }
}
