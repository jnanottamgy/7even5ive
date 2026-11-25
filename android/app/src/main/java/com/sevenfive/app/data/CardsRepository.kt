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
    /** The last poll couldn't reach the server at all (wrong or changed address). */
    val unreachable: Boolean = false,
    val updatedAt: Instant? = null,
)

/** One source of truth for every screen: `GET /api/cards`, polled while the app is in front. */
class CardsRepository(private val core: CoreApi) {
    private val _state = MutableStateFlow(CardsState())
    val state: StateFlow<CardsState> = _state.asStateFlow()
    private val lock = Mutex()

    /** Approvals already run or refused here: never shown again, whatever the next poll says. */
    private val hiddenApprovals = mutableSetOf<String>()

    /**
     * Overlapping background polls collapse into one request. A pull to refresh passes
     * [wait] = true: it waits for a poll already running and then asks again, so the student's
     * gesture always gets a fresh answer instead of returning at once.
     */
    suspend fun refresh(wait: Boolean = false) {
        if (!wait && lock.isLocked) return
        lock.withLock {
            try {
                val cards = core.cards().let { c ->
                    c.copy(approvals = c.approvals.filterNot { it.token in hiddenApprovals })
                }
                _state.value = CardsState(cards, loading = false, error = null, updatedAt = Instant.now())
            } catch (e: ApiException) {
                _state.update { it.copy(loading = false, error = e.detail, unreachable = e.status == 0) }
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

    /** Hides one approval now and on every later poll (used, expired or refused tokens). */
    fun dropApproval(token: String) {
        hiddenApprovals += token
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
        hiddenApprovals.clear()
        _state.value = CardsState()
    }

    companion object {
        /** The brief asks for 5–10 s. */
        const val POLL_MILLIS = 7_000L
    }
}
