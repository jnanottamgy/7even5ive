package com.sevenfive.app.data

import android.content.Context
import androidx.core.content.edit
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Where the three servers are. On the laptop setup all three share one host. */
data class ServerConfig(
    val coreUrl: String,
    val portmaxUrl: String,
    val portalUrl: String,
) {
    /**
     * The online (cloud) service: core and PortMax are one address. The portal may differ — a
     * college whose own portal the WebView opens (e.g. MSRIT) still uploads to this cloud — so the
     * portal is deliberately not part of this check, which only tells cloud from laptop. A laptop
     * setup always has core and PortMax on different ports (8000, 8002), so no scheme check is
     * needed, and a server's own plain-HTTP address (http://13.233.1.2) still counts as online.
     */
    val isOnline: Boolean get() = coreUrl == portmaxUrl

    companion object {
        /** One HTTPS address serving the core, PortMax and the portal (seventy5.cloud). */
        fun forOnline(url: String): ServerConfig {
            val u = url.trim().trimEnd('/').let { if (it.startsWith("http")) it else "https://$it" }
            return ServerConfig(u, u, u)
        }

        /** What the student typed: an online address (https://…) or a laptop's IP. */
        fun parse(input: String): ServerConfig {
            val t = input.trim().trimEnd('/')
            val http = t.startsWith("http://")
            val hostPart = t.substringAfter("://").substringBefore('/')
            val online = t.startsWith("https://") ||
                (http && ':' !in hostPart) ||          // http://server, no port: one address
                (!http && hostPart.any { it.isLetter() }) // a domain name, no scheme
            return if (online) {
                forOnline(t)
            } else {
                forHost(t)
            }
        }

        fun forHost(host: String): ServerConfig {
            val h = host.trim().removePrefix("http://").removePrefix("https://").trimEnd('/')
                .substringBefore(':')
            return ServerConfig("http://$h:8000", "http://$h:8002", "http://$h:8765")
        }
    }
}

/** Server addresses only. The token is a build constant and is never written to disk here. */
class ServerSettings(
    context: Context,
    private val defaultHost: String,
    private val defaultServer: String = "",
    defaultPortal: String = "",
) {
    private val prefs = context.getSharedPreferences("servers", Context.MODE_PRIVATE)

    /**
     * The build's own choice: its online server if it has one, else the laptop default. When the
     * build names a separate portal (`sevenfive.portal`, e.g. the college's real portal), that
     * address replaces the portal URL while core and PortMax stay on the cloud server.
     */
    val buildDefault: ServerConfig =
        (if (defaultServer.isNotBlank()) ServerConfig.forOnline(defaultServer)
        else ServerConfig.forHost(defaultHost)).let {
            if (defaultPortal.isBlank()) it
            else it.copy(portalUrl = defaultPortal.trim().trimEnd('/')
                .let { p -> if (p.startsWith("http")) p else "https://$p" })
        }

    private val _config = MutableStateFlow(load())
    val config: StateFlow<ServerConfig> = _config.asStateFlow()

    /**
     * The server an older build of the app used, when this build's own default took over from
     * it: an account signed in there belongs to that server, so it is signed out (the demo just
     * moves along). Kept until [movedHandled], so a restart before then still signs it out.
     */
    val movedFrom: String? get() = prefs.getString(MOVED_FROM, null)

    fun movedHandled() {
        prefs.edit { remove(MOVED_FROM) }
    }

    private fun load(): ServerConfig {
        // A build with a new online server takes over from whatever an older build saved,
        // so installing it is enough. A choice made under this same build is kept.
        val seen = prefs.getString(DEFAULT_SEEN, null)
        if ((seen ?: "") != defaultServer) {
            val moved = movedFrom(seen, prefs.getString("core", null), defaultServer, defaultHost)
            prefs.edit {
                clear()
                putString(DEFAULT_SEEN, defaultServer)
                if (moved != null) putString(MOVED_FROM, moved)
            }
            return buildDefault
        }
        return ServerConfig(
            coreUrl = prefs.getString("core", null) ?: buildDefault.coreUrl,
            portmaxUrl = prefs.getString("portmax", null) ?: buildDefault.portmaxUrl,
            portalUrl = prefs.getString("portal", null) ?: buildDefault.portalUrl,
        )
    }

    fun save(config: ServerConfig) {
        val clean = ServerConfig(
            config.coreUrl.trim().trimEnd('/'),
            config.portmaxUrl.trim().trimEnd('/'),
            config.portalUrl.trim().trimEnd('/'),
        )
        prefs.edit()
            .putString("core", clean.coreUrl)
            .putString("portmax", clean.portmaxUrl)
            .putString("portal", clean.portalUrl)
            .apply()
        _config.value = clean
    }

    companion object {
        private const val DEFAULT_SEEN = "default_seen"
        private const val MOVED_FROM = "moved_from"

        /**
         * The core address the app used before, when this build's [defaultServer] takes over from
         * the one an older build last saw ([seen]: null on a new install): the address chosen then
         * ([savedCore]), else that build's own default. Null when the app stays where it was.
         */
        fun movedFrom(seen: String?, savedCore: String?, defaultServer: String, defaultHost: String): String? {
            if ((seen ?: "") == defaultServer) return null
            if (seen == null && savedCore == null) return null // a new install: nothing was used before
            val before = savedCore
                ?: if (seen.isNullOrBlank()) ServerConfig.forHost(defaultHost).coreUrl else ServerConfig.forOnline(seen).coreUrl
            val now = if (defaultServer.isNotBlank()) ServerConfig.forOnline(defaultServer).coreUrl
            else ServerConfig.forHost(defaultHost).coreUrl
            return before.trimEnd('/').takeIf { it != now.trimEnd('/') }
        }
    }
}
