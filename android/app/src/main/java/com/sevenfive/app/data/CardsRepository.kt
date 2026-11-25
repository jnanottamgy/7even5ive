package com.sevenfive.app.data

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.time.Instant

data class CardsState(
    val cards: Cards? = null,
    val loading: Boolean = true,
    /** Why the last poll failed; the last good cards stay on screen. */
    val error: String? = null,
    val updatedAt: Instant? = null,
)

/** One source of truth for every screen: `GET /api/cards`, polled while the app is in front. */
class CardsRepository(private val core: CoreApi) {
    private val _state = MutableStateFlow(CardsState())
    val state: StateFlow<CardsState> = _state.asStateFlow()
    private val lock = Mutex()

    suspend fun refresh() {
        // Overlapping polls (a tap plus the timer) collapse into one request.
        if (lock.isLocked) return
        lock.withLock {
            try {
                val cards = core.cards()
                _state.value = CardsState(cards, loading = false, error = null, updatedAt = Instant.now())
            } catch (e: ApiException) {
                _state.update { it.copy(loading = false, error = e.detail) }
            }
        }
    }

    /** Runs until cancelled; the caller ties it to the foreground (repeatOnLifecycle STARTED). */
    suspend fun pollForever() {
        while (true) {
            refresh()
            delay(POLL_MILLIS)
        }
    }

    /** Hides one approval right away, before the next poll confirms it. */
    fun dropApproval(token: String) {
        _state.update { s ->
            s.copy(cards = s.cards?.let { c -> c.copy(approvals = c.approvals.filterNot { it.token == token }) })
        }
    }

    fun dropReminder(id: Int) {
        _state.update { s ->
            s.copy(cards = s.cards?.let { c -> c.copy(reminders = c.reminders.filterNot { it.id == id }) })
        }
    }

    fun reset() {
        _state.value = CardsState()
    }

    companion object {
        /** The brief asks for 5–10 s. */
        const val POLL_MILLIS = 7_000L
    }
}
