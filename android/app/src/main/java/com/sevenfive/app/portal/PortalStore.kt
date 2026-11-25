package com.sevenfive.app.portal

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import java.time.Instant

/**
 * What the app remembers about the portal. Never the password and never the cookies' values:
 * the session lives in the WebView's CookieManager, on this phone only.
 */
data class PortalStatus(
    /** At least one upload succeeded, so a background refresh is worth trying. */
    val everConnected: Boolean = false,
    /** The last attempt met the login page: ask the student next time, never by notification. */
    val needsLogin: Boolean = false,
    val lastFullSync: Instant? = null,
    val lastKeepAlive: Instant? = null,
    val busy: Boolean = false,
    val lastError: String? = null,
)

class PortalStore(context: Context) {
    private val prefs = context.getSharedPreferences("portal", Context.MODE_PRIVATE)

    private val _status = MutableStateFlow(
        PortalStatus(
            everConnected = prefs.getBoolean("ever", false),
            needsLogin = prefs.getBoolean("needs_login", false),
            lastFullSync = prefs.getLong("full", 0L).takeIf { it > 0 }?.let(Instant::ofEpochMilli),
            lastKeepAlive = prefs.getLong("keep", 0L).takeIf { it > 0 }?.let(Instant::ofEpochMilli),
        )
    )
    val status: StateFlow<PortalStatus> = _status.asStateFlow()

    fun setBusy(busy: Boolean) = _status.update { it.copy(busy = busy) }

    fun recordSuccess(full: Boolean, at: Instant = Instant.now()) {
        _status.update {
            it.copy(
                everConnected = true, needsLogin = false, lastError = null,
                lastFullSync = if (full) at else it.lastFullSync,
                // Any upload proves the session is alive, so it counts as a keep-alive too.
                lastKeepAlive = at,
            )
        }
        persist()
    }

    fun markNeedsLogin() {
        _status.update { it.copy(needsLogin = true, lastError = null) }
        persist()
    }

    /** "Log out of the portal on this phone": the cookies go too (see SettingsScreen). */
    fun forget() {
        _status.value = PortalStatus()
        prefs.edit().clear().apply()
    }

    fun recordError(message: String) = _status.update { it.copy(lastError = message) }

    private fun persist() {
        val s = _status.value
        prefs.edit()
            .putBoolean("ever", s.everConnected)
            .putBoolean("needs_login", s.needsLogin)
            .putLong("full", s.lastFullSync?.toEpochMilli() ?: 0L)
            .putLong("keep", s.lastKeepAlive?.toEpochMilli() ?: 0L)
            .apply()
    }
}
