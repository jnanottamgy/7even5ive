package com.sevenfive.app.data

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Where the three servers are. On the laptop setup all three share one host. */
data class ServerConfig(
    val coreUrl: String,
    val portmaxUrl: String,
    val portalUrl: String,
) {
    /** The online service: one address for everything. A laptop setup uses three ports. */
    val isOnline: Boolean get() = coreUrl.startsWith("https://")

    companion object {
        /** One HTTPS address serving the core, PortMax and the portal (seventy5.cloud). */
        fun forOnline(url: String): ServerConfig {
            val u = url.trim().trimEnd('/').let { if (it.startsWith("http")) it else "https://$it" }
            return ServerConfig(u, u, u)
        }

        /** What the student typed: an online address (https://…) or a laptop's IP. */
        fun parse(input: String): ServerConfig {
            val t = input.trim().trimEnd('/')
            return if (t.startsWith("https://") || (t.any { it.isLetter() } && !t.startsWith("http://"))) {
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
class ServerSettings(context: Context, defaultHost: String, private val defaultServer: String = "") {
    private val prefs = context.getSharedPreferences("servers", Context.MODE_PRIVATE)

    /** The build's own choice: its online server if it has one, else the laptop default. */
    val buildDefault: ServerConfig =
        if (defaultServer.isNotBlank()) ServerConfig.forOnline(defaultServer) else ServerConfig.forHost(defaultHost)

    private val _config = MutableStateFlow(load())
    val config: StateFlow<ServerConfig> = _config.asStateFlow()

    private fun load(): ServerConfig {
        // A build with a new online server takes over from whatever an older build saved,
        // so installing it is enough. A choice made under this same build is kept.
        if (prefs.getString("default_seen", "") != defaultServer) {
            prefs.edit().clear().putString("default_seen", defaultServer).apply()
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
}
