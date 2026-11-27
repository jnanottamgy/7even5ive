package com.sevenfive.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import java.io.File
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

/**
 * One source of truth for every screen: `GET /api/cards`, polled while the app is in front.
 *
 * An answer belongs to whoever was signed in when it was asked for. [reset] (someone else now)
 * bumps [generation], and an answer asked for before it is dropped: never shown, never kept on
 * disk, never turned into alarms. [applying] keeps the two apart, so once [reset] returns no
 * answer of the last person's can still be applied.
 */
class CardsRepository(private val core: CoreApi, private val cacheFile: File? = null) {
    private val _state = MutableStateFlow(CardsState(cards = loadCache(), loading = true))
    val state: StateFlow<CardsState> = _state.asStateFlow()
    private val lock = Mutex()
    private val applying = Mutex()
    @Volatile private var generation = 0L

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
            val asked = generation
            try {
                val json = core.cardsJson()
                val cards = decodeAnswer<Cards>(json).let { c ->
                    c.copy(approvals = c.approvals.filterNot { it.token in hiddenApprovals })
                }
                applying.withLock {
                    if (generation != asked) return@withLock
                    _state.value = CardsState(cards, loading = false, error = null, updatedAt = Instant.now())
                    saveCache(json)
                    onCards(cards)
                }
            } catch (e: ApiException) {
                // A busy server is asked again by the next poll by itself: the banner says so.
                val said = if (e.busy) BUSY_RETRYING else e.detail
                applying.withLock {
                    if (generation == asked) {
                        _state.update { it.copy(loading = false, error = said, unreachable = e.status == 0) }
                    }
                }
            }
        }
    }

    /** Runs until cancelled; the caller ties it to the foreground (repeatOnLifecycle STARTED).
     * [firstAfter]: the caller has just asked once itself. */
    suspend fun pollForever(firstAfter: Long = 0) {
        delay(firstAfter)
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

    /** Someone else now (or another server): nothing of the last cards stays, here or on disk. */
    suspend fun reset() = applying.withLock {
        generation++
        hiddenApprovals.clear()
        _state.value = CardsState()
        runCatching { cacheFile?.delete() }
        onReset()
    }

    /** Called after every good poll (reminder alarms, the widget). Set once by the container. */
    var onCards: suspend (Cards) -> Unit = {}

    /** Called by [reset], after the cards are gone: what was made from them goes too. */
    var onReset: suspend () -> Unit = {}

    /** The last good cards, for the widget, the digest and a launch with no network. */
    fun cached(): Cards? = _state.value.cards ?: loadCache()

    private fun loadCache(): Cards? = runCatching {
        cacheFile?.takeIf { it.exists() }?.readText()?.let { decodeAnswer<Cards>(it) }
    }.getOrNull()

    private suspend fun saveCache(json: String) = withContext(Dispatchers.IO) {
        // App-private storage: the same data the screens show, never logged or shared.
        runCatching {
            val file = cacheFile ?: return@runCatching
            val tmp = File(file.parentFile, file.name + ".tmp")
            tmp.writeText(json)
            tmp.renameTo(file)
        }
    }

    companion object {
        /** The brief asks for 5–10 s. */
        const val POLL_MILLIS = 7_000L
    }
}
