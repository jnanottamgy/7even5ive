package com.sevenfive.app.data

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.net.URI

/**
 * Keeps the app pointed at a working laptop with no typing: while the saved server can't be
 * reached, it looks for one on the phone's network and switches to it. The manual address in
 * Settings still works and wins whenever it answers.
 */
class ServerFinder(
    private val servers: ServerSettings,
    private val cards: CardsRepository,
    private val portmax: PortMaxApi,
    private val discovery: Discovery = Discovery(),
) {
    private val _searching = MutableStateFlow(false)
    val searching: StateFlow<Boolean> = _searching.asStateFlow()

    private val _messages = MutableSharedFlow<String>(extraBufferCapacity = 4)
    val messages: SharedFlow<String> = _messages.asSharedFlow()

    private val lock = Mutex()
    private var lastSearch = 0L

    /** Runs while the app is on screen: a search after the server has been unreachable a while. */
    suspend fun runWhileStarted() {
        while (true) {
            delay(CHECK_MILLIS)
            val state = cards.state.value
            val due = System.currentTimeMillis() - lastSearch > RETRY_MILLIS
            if (state.unreachable && due) find(userAsked = false)
        }
    }

    /** One search now. Returns the host it switched to, or null. */
    suspend fun find(userAsked: Boolean): String? = lock.withLock {
        lastSearch = System.currentTimeMillis()
        _searching.value = true
        try {
            val host = discovery.find()
            if (host == null) {
                if (userAsked) {
                    _messages.tryEmit(
                        "No laptop found. Is start-demo running, and is the phone on its Wi-Fi or hotspot?"
                    )
                }
                return null
            }
            val current = runCatching { URI(servers.config.value.coreUrl).host }.getOrNull()
            if (host != current) {
                servers.save(ServerConfig.forHost(host))
                portmax.forget()
                _messages.tryEmit("Found the laptop at $host")
            } else if (userAsked) {
                _messages.tryEmit("Connected to the laptop at $host")
            }
            cards.refresh(wait = true)
            host
        } finally {
            _searching.value = false
        }
    }

    private companion object {
        const val CHECK_MILLIS = 3_000L
        /** After a search that found nothing, wait this long before the next automatic one. */
        const val RETRY_MILLIS = 20_000L
    }
}
