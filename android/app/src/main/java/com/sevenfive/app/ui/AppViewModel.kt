package com.sevenfive.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.sevenfive.app.AppContainer
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.Approval
import com.sevenfive.app.data.CardsState
import com.sevenfive.app.data.Item
import com.sevenfive.app.data.Reminder
import com.sevenfive.app.data.ServerConfig
import com.sevenfive.app.portal.PortalCheck
import com.sevenfive.app.portal.PortalStatus
import com.sevenfive.app.util.Diagnostics
import com.sevenfive.app.util.Time
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** An approval the student already tapped this session, kept on screen as proof it ran once. */
data class DoneApproval(val approval: Approval, val title: String)

class AppViewModel(val container: AppContainer) : ViewModel() {
    val cards: StateFlow<CardsState> = container.cards.state
    val portal: StateFlow<PortalStatus> = container.portalStore.status
    val servers: StateFlow<ServerConfig> = container.servers.config

    private val _busy = MutableStateFlow<Set<String>>(emptySet())
    /** Keys of actions in flight (approval tokens, "rem:<id>"), so buttons can't double-fire. */
    val busy: StateFlow<Set<String>> = _busy.asStateFlow()

    private val _portalCheckUrl = MutableStateFlow(PortalCheck.DEFAULT_URL)
    /** The address the portal test opens (Settings → Test a college portal). */
    val portalCheckUrl: StateFlow<String> = _portalCheckUrl.asStateFlow()

    fun setPortalCheckUrl(url: String) {
        _portalCheckUrl.value = url
    }

    private val _tour = MutableStateFlow<TourState?>(null)
    /** The demo tour, while it runs (Settings → Start the demo tour). */
    val tour: StateFlow<TourState?> = _tour.asStateFlow()

    private val _resetting = MutableStateFlow(false)
    val resetting: StateFlow<Boolean> = _resetting.asStateFlow()

    private val _approved = MutableStateFlow<List<DoneApproval>>(emptyList())
    val approved: StateFlow<List<DoneApproval>> = _approved.asStateFlow()

    private val _messages = Channel<String>(Channel.BUFFERED)
    /** One-off messages for the snackbar: the server's own words when it refuses. */
    val messages = _messages.receiveAsFlow()

    val searching: StateFlow<Boolean> = container.finder.searching

    init {
        viewModelScope.launch { container.finder.messages.collect { say(it) } }
        if (Diagnostics.hasUnseen(container.appContext)) {
            say("7even5ive closed unexpectedly last time. Details: Settings → Diagnostics.")
        }
    }

    fun refresh() = viewModelScope.launch { container.cards.refresh() }

    fun startTour() {
        _tour.value = TourState()
    }

    fun endTour() {
        _tour.value = null
    }

    fun tourBack() = _tour.update { t -> t?.copy(index = (t.index - 1).coerceAtLeast(0), result = null) }

    fun tourNext() = _tour.update { t ->
        t?.copy(index = (t.index + 1).coerceAtMost(DemoTour.steps.lastIndex), result = null)
    }

    /** Runs the current step's live moment on the demo server, then refreshes the cards. */
    fun tourAct() {
        val state = _tour.value ?: return
        val action = DemoTour.steps[state.index].action ?: return
        if (state.busy) return
        _tour.update { it?.copy(busy = true, result = null) }
        viewModelScope.launch {
            val result = try {
                runAction(action)
            } catch (e: ApiException) {
                if (e.status == 404) "This server has no demo tour: use the online demo server."
                else "The server said: ${e.detail}"
            }
            container.cards.refresh(wait = true)
            _tour.update { it?.copy(busy = false, result = result) }
        }
    }

    private suspend fun runAction(action: DemoAction): String {
        val core = container.core
        return when (action) {
            DemoAction.FORWARD_QUIZ -> core.demoForward("quiz").filed
                ?.let { "New card “${it.title}”, filed via ${it.route}: no AI call." }
                ?: "Sent, but no card was filed."
            DemoAction.FORWARD_NOTES -> core.demoForward("notes").filed
                ?.let { "“${it.title}” filed under ${it.subject}." }
                ?: "Sent, but nothing was filed."
            DemoAction.SIGNED_ONLY -> {
                val stranger = core.demoForward("stranger")
                val forged = core.demoForward("forged")
                "Stranger: answered ${stranger.webhookStatus}, nothing filed. " +
                    "Forged signature: refused (${forged.webhookStatus})."
            }
            DemoAction.AI_CALENDAR -> {
                val due = cards.value.cards?.dueThisWeek.orEmpty()
                val item = due.firstOrNull { it.title == DemoTour.QUIZ_TITLE } ?: due.firstOrNull()
                    ?: return "Nothing dated to add yet: forward the quiz first (step 2)."
                val out = core.tool("add_to_calendar", buildJsonObject { put("item_id", item.id) })
                if (out.status == "approval_needed") "Held for your tap: approve “${item.title}” at the top."
                else "The gateway answered: ${out.status}"
            }
            DemoAction.NO_SEND_TOOL -> {
                val refused = try {
                    core.tool("send_email", buildJsonObject { put("to", "everyone@college.edu") })
                    "it ran (it never should)"
                } catch (e: ApiException) {
                    "refused (${e.status}: ${e.detail})"
                }
                "send_email $refused. No token: refused (${core.statusWithoutToken()})."
            }
            DemoAction.SERVERLESS -> {
                val host = java.net.URI(servers.value.coreUrl).host ?: servers.value.coreUrl
                "Answered by $host in ${core.healthMillis()} ms."
            }
        }
    }

    /** Back to the demo morning on the server, and a clean slate on this phone. */
    fun resetDemo() {
        if (_resetting.value) return
        _resetting.value = true
        viewModelScope.launch {
            try {
                container.core.demoReset()
                _approved.value = emptyList()
                container.portalStore.forget()
                container.cards.reset()
                container.cards.refresh(wait = true)
                say("Demo reset: back to the morning")
            } catch (e: ApiException) {
                say(if (e.status == 404) "This server has no demo reset: use the online demo server." else e.detail)
            } finally {
                _resetting.value = false
            }
        }
    }

    fun say(message: String) {
        _messages.trySend(message)
    }

    fun titleFor(approval: Approval): String =
        cards.value.cards?.itemById(approval.itemId)?.title ?: "item #${approval.itemId ?: "?"}"

    /** Never automatic: only ever called from the Approve button. */
    fun approve(approval: Approval) = action(approval.token) {
        val title = titleFor(approval)
        try {
            container.core.approve(approval.token)
            container.cards.dropApproval(approval.token)
            _approved.update { done -> listOf(DoneApproval(approval, title)) + done.filterNot { it.approval.token == approval.token } }
            say("Added to Google Calendar: $title")
        } catch (e: ApiException) {
            // "approval already used" / "approval expired": the gateway's word, shown as it is.
            say(e.detail)
            if (e.status == 403) container.cards.dropApproval(approval.token)
        }
        container.cards.refresh()
    }

    fun remind(item: Item, beforeMinutes: Int) = action("item:${item.id}") {
        try {
            val r = container.core.setReminder(item.id, beforeMinutes)
            val at = Time.parse(r.firesAt)?.let { Time.dayAndTime(it) } ?: "later"
            say("Reminder set for $at")
        } catch (e: ApiException) {
            say(e.detail)
        }
        container.cards.refresh()
    }

    fun cancel(reminder: Reminder) = action("rem:${reminder.id}") {
        try {
            container.core.cancelReminder(reminder.id)
            container.cards.dropReminder(reminder.id)
            say("Reminder cancelled")
        } catch (e: ApiException) {
            say(e.detail)
        }
        container.cards.refresh()
    }

    fun findLaptop() = viewModelScope.launch { container.finder.find(userAsked = true) }

    /** "https://…" for the online server, or a laptop's IP. */
    fun connectTo(input: String) = saveServers(ServerConfig.parse(input))

    fun useOnline() = saveServers(container.servers.buildDefault)

    fun saveServers(config: ServerConfig) {
        container.servers.save(config)
        container.portmax.forget()
        container.cards.reset()
        refresh()
        say("Saved. Connecting to ${config.coreUrl}")
    }

    private fun action(key: String, block: suspend () -> Unit) {
        if (key in _busy.value) return
        _busy.update { it + key }
        viewModelScope.launch {
            try {
                block()
            } finally {
                _busy.update { it - key }
            }
        }
    }
}
