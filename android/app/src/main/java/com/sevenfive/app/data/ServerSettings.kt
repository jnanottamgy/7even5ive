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
    companion object {
        fun forHost(host: String): ServerConfig {
            val h = host.trim().removePrefix("http://").removePrefix("https://").trimEnd('/')
                .substringBefore(':')
            return ServerConfig("http://$h:8000", "http://$h:8002", "http://$h:8765")
        }
    }
}

/** Server addresses only. The token is a build constant and is never written to disk here. */
class ServerSettings(context: Context, defaultHost: String) {
    private val prefs = context.getSharedPreferences("servers", Context.MODE_PRIVATE)
    private val fallback = ServerConfig.forHost(defaultHost)

    private val _config = MutableStateFlow(
        ServerConfig(
            coreUrl = prefs.getString("core", null) ?: fallback.coreUrl,
            portmaxUrl = prefs.getString("portmax", null) ?: fallback.portmaxUrl,
            portalUrl = prefs.getString("portal", null) ?: fallback.portalUrl,
        )
    )
    val config: StateFlow<ServerConfig> = _config.asStateFlow()

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
