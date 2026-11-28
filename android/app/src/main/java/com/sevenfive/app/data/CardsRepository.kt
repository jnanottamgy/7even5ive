package com.sevenfive.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.CoroutineScope
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
    private val _state = MutableStateFlow(CardsState(cards = null, loading = true))
    val state: StateFlow<CardsState> = _state.asStateFlow()
    private val lock = Mutex()
    private val applying = Mutex()
    @Volatile private var generation = 0L

    /** What the server tagged the cards on screen: sent back so an unchanged poll is a 304. */
    @Volatile private var etag: String? = null

    /** When the server last answered well: what the offline banner says ("data from 2 min ago"). */
    @Volatile private var lastGood: Instant? = null

    /** The cards as the server last sent them. Screens see these with [pending] laid over them. */
    @Volatile private var server: Cards? = null

    /** Approvals already run or refused here: never shown again, whatever the next poll says. */
    private val hiddenApprovals: MutableSet<String> = java.util.concurrent.ConcurrentHashMap.newKeySet()

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
                // "Only if changed": the server answers 304 when the cards are as tagged, and then
                // nothing is downloaded, read or redrawn. Most polls are this.
                val known = etag.takeIf { server != null }
                val issued = synchronized(overlay) { ++requests }
                val answer = core.cardsIfChanged(known)
                val json = answer.body
                if (json == null) {
                    applying.withLock {
                        if (generation != asked) return@withLock
                        val current = server ?: return@withLock
                        lastGood = Instant.now()
                        settleSeenBy(issued)
                        // Only a state that showed a problem changes; otherwise nothing is emitted
                        // and no screen recomposes.
                        if (_state.value.let { it.error != null || it.loading || it.unreachable }) {
                            _state.update { it.copy(loading = false, error = null, unreachable = false, updatedAt = lastGood) }
                        }
                        onCards(current)
                    }
                    return@withLock
                }
                // Reading the answer is real work: off the main thread, so a poll never costs a frame.
                val cards = withContext(Dispatchers.Default) { decodeAnswer<Cards>(json) }
                applying.withLock {
                    if (generation != asked) return@withLock
                    // Nothing changed (a server without tags): keep the very same object, so every
                    // screen sees identical data and skips its work.
                    val previous = server
                    val same = previous != null && withContext(Dispatchers.Default) { previous == cards }
                    val kept = if (same) previous!! else cards
                    lastGood = Instant.now()
                    etag = answer.etag
                    val quiet = same && _state.value.let { it.error == null && !it.loading && !it.unreachable }
                    synchronized(overlay) {
                        server = kept
                        if (!quiet) _state.value = CardsState(shown(kept), loading = false, error = null, updatedAt = lastGood)
                    }
                    settleSeenBy(issued)
                    if (!same) saveCache(json)
                    // Always: it notices time passing too (the lock-screen countdown's last 24 h),
                    // and only acts when what it would show changes.
                    onCards(kept)
                }
            } catch (e: ApiException) {
                // A busy server is asked again by the next poll by itself: the banner says so.
                val said = if (e.busy) BUSY_RETRYING else e.detail
                applying.withLock {
                    if (generation == asked) {
                        _state.update {
                            it.copy(loading = false, error = said, unreachable = e.status == 0, updatedAt = lastGood ?: it.updatedAt)
                        }
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

    /** Hides one approval now and on every later poll (approved, used, expired or refused). */
    fun dropApproval(token: String) = synchronized(overlay) {
        hiddenApprovals += token
        publish()
    }

    /** An approval that couldn't run (the network, the server): shown again to try once more. */
    fun restoreApproval(token: String) = synchronized(overlay) {
        hiddenApprovals -= token
        publish()
    }

    // --- what the student just did, shown before the server has it --------------------------------
    // A tap changes the screen at once and the server is told in the background. Each change is
    // laid over the server's cards until an answer asked for after the server took it comes back
    // (then the server's own cards show it), or until the server refuses it (then it is taken
    // back at once). Alarms, the widget and the disk only ever get the server's own cards.

    private val overlay = Any()
    private var pending = Pending()
    private var changes = 0L
    /** How many card requests have been sent: an answer to a later one has seen a confirmed change. */
    private var requests = 0L
    /** Where each item was on screen when it was marked done, to put it back there on Undo. */
    private val places = HashMap<Int, Map<Int, Int>>()

    // After every field above: the load below runs on its own thread at once, and must find them made.
    init {
        // The last good cards from disk, read and decoded off the main thread: the app's first
        // frame never waits for them (the opening screen covers the moment they take).
        if (cacheFile != null) {
            val born = generation
            CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
                val saved = loadCache() ?: return@launch
                applying.withLock {
                    if (generation == born && server == null) synchronized(overlay) {
                        server = saved
                        _state.update { it.copy(cards = shown(saved)) }
                    }
                }
            }
        }
    }

    private data class Pending(
        val items: Map<Int, ItemChange> = emptyMap(),
        val reminders: Map<Int, ReminderChange> = emptyMap(),
    )

    /** [item] done ([hidden]) or back on its lists. [seenAfter]: the request count when the server confirmed it. */
    private data class ItemChange(val hidden: Boolean, val item: Item, val version: Long, val seenAfter: Long? = null)

    /** A reminder [added] before the server has it, or one taken away before the server agrees. */
    private data class ReminderChange(val reminder: Reminder, val added: Boolean, val version: Long, val seenAfter: Long? = null)

    /** Shows [item] as done, or ([done] false) back where it was, at once. Returns the change's
     * number for [confirm] / [takeBack]. */
    fun showDone(item: Item, done: Boolean): Long = synchronized(overlay) {
        if (done) shown(server)?.let { c ->
            val at = c.lists().withIndex()
                .mapNotNull { (which, list) -> list.indexOfFirst { it.id == item.id }.takeIf { it >= 0 }?.let { which to it } }
                .toMap()
            if (at.isNotEmpty()) places[item.id] = at
        }
        val v = ++changes
        pending = pending.copy(items = pending.items + (item.id to ItemChange(done, item, v)))
        publish()
        v
    }

    /** Shows [reminder] as set ([added]) or as cancelled, at once. */
    fun showReminder(reminder: Reminder, added: Boolean): Long = synchronized(overlay) {
        val v = ++changes
        pending = pending.copy(reminders = pending.reminders + (reminder.id to ReminderChange(reminder, added, v)))
        publish()
        v
    }

    /** The server took change [version]: the next answer asked for after now shows it by itself. */
    fun confirm(version: Long) = synchronized(overlay) {
        val seen = requests
        pending = Pending(
            items = pending.items.mapValues { (_, c) -> if (c.version == version) c.copy(seenAfter = seen) else c },
            reminders = pending.reminders.mapValues { (_, c) -> if (c.version == version) c.copy(seenAfter = seen) else c },
        )
    }

    /** The server refused change [version] (or couldn't be reached): the screen shows its cards again. */
    fun takeBack(version: Long) = synchronized(overlay) {
        val before = pending
        pending = Pending(
            items = pending.items.filterValues { it.version != version },
            reminders = pending.reminders.filterValues { it.version != version },
        )
        if (pending != before) publish()
    }

    /** The server's reminder for [itemId] firing at [firesAt] (a set one that has its own id by now). */
    fun serverReminder(itemId: Int?, firesAt: String?): Reminder? =
        server?.reminders?.firstOrNull { it.itemId == itemId && sameInstant(it.firesAt, firesAt) }

    /** An answer to request [issued] has come: every change confirmed before it was sent is in it. */
    private fun settleSeenBy(issued: Long) = synchronized(overlay) {
        val before = pending
        pending = Pending(
            items = pending.items.filterValues { it.seenAfter == null || it.seenAfter >= issued },
            reminders = pending.reminders.filterValues { it.seenAfter == null || it.seenAfter >= issued },
        )
        if (pending != before) publish()
    }

    /** Call inside synchronized(overlay). */
    private fun publish() {
        _state.update { it.copy(cards = shown(server)) }
    }

    /** What screens show: the server's cards with what is pending laid over them. With nothing
     * pending it is the server's very object, so screens that compare it skip their work. */
    private fun shown(base: Cards?): Cards? {
        base ?: return null
        val p = pending
        val hidden = hiddenApprovals
        if (p.items.isEmpty() && p.reminders.isEmpty() && hidden.isEmpty()) return base
        var c = base
        if (hidden.isNotEmpty()) c = c.copy(approvals = c.approvals.filterNot { it.token in hidden })
        if (p.items.isNotEmpty()) {
            val lists = c.lists().mapIndexed { which, list ->
                var out = list.filterNot { p.items[it.id]?.hidden == true }
                for ((id, change) in p.items) {
                    if (change.hidden || out.any { it.id == id }) continue
                    val at = places[id]?.get(which) ?: continue
                    out = out.toMutableList().also { it.add(at.coerceIn(0, it.size), change.item) }
                }
                out
            }
            c = c.copy(dueThisWeek = lists[0], materials = lists[1], opportunities = lists[2], needsReview = lists[3])
        }
        val done = p.items.filterValues { it.hidden }.keys
        if (p.reminders.isNotEmpty() || done.isNotEmpty()) {
            // A cancelled one is matched by id, or by item and time: one cancelled while it was
            // still on its way to the server comes back from it under its new id.
            val cancelled = p.reminders.values.filter { !it.added }.map { it.reminder }
            val added = p.reminders.values.filter { it.added }.map { it.reminder }
                .filter { a -> c.reminders.none { it.itemId == a.itemId && sameInstant(it.firesAt, a.firesAt) } }
            val kept = c.reminders.filterNot { r ->
                r.itemId in done || cancelled.any { x -> x.id == r.id || (x.itemId == r.itemId && sameInstant(x.firesAt, r.firesAt)) }
            }
            c = c.copy(
                reminders = if (added.isEmpty()) kept
                else (kept + added).sortedBy { com.sevenfive.app.util.Time.parse(it.firesAt)?.toInstant() },
            )
        }
        return c
    }

    private fun Cards.lists() = listOf(dueThisWeek, materials, opportunities, needsReview)

    private fun sameInstant(a: String?, b: String?): Boolean {
        val x = com.sevenfive.app.util.Time.parse(a) ?: return false
        val y = com.sevenfive.app.util.Time.parse(b) ?: return false
        return x.toInstant() == y.toInstant()
    }

    /** Someone else now (or another server): nothing of the last cards stays, here or on disk. */
    suspend fun reset() = applying.withLock {
        generation++
        etag = null
        lastGood = null
        hiddenApprovals.clear()
        synchronized(overlay) {
            server = null
            pending = Pending()
            places.clear()
        }
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
