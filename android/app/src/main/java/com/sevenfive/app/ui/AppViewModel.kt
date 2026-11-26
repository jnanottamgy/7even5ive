package com.sevenfive.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.sevenfive.app.AppContainer
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.AppSettings
import com.sevenfive.app.data.Approval
import com.sevenfive.app.data.Briefing
import com.sevenfive.app.data.CallRecord
import com.sevenfive.app.data.CardsState
import com.sevenfive.app.data.Item
import com.sevenfive.app.data.Reminder
import com.sevenfive.app.data.ServerConfig
import com.sevenfive.app.notify.Notifications
import com.sevenfive.app.portal.PortalCheck
import com.sevenfive.app.portal.PortalKeepAliveWorker
import com.sevenfive.app.portal.PortalStatus
import com.sevenfive.app.voice.VoiceAssistant
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

/** A snackbar line, optionally with one action ("Undo"). */
data class UiMessage(val text: String, val action: String? = null, val onAction: (() -> Unit)? = null)

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

    private val _messages = Channel<UiMessage>(Channel.BUFFERED)
    /** One-off messages for the snackbar: the server's own words when it refuses. */
    val messages = _messages.receiveAsFlow()

    private val _settings = MutableStateFlow<AppSettings?>(null)
    /** Server-side settings (calls, Google, voice), loaded when Settings or a call option opens. */
    val settings: StateFlow<AppSettings?> = _settings.asStateFlow()

    private val _callHistory = MutableStateFlow<List<CallRecord>>(emptyList())
    val callHistory: StateFlow<List<CallRecord>> = _callHistory.asStateFlow()

    private val _briefing = MutableStateFlow<Briefing?>(null)
    val briefing: StateFlow<Briefing?> = _briefing.asStateFlow()
    val briefingPlayer = container.briefingPlayer.state

    val voice: StateFlow<VoiceAssistant.State> = container.voice.state

    private val _openUrl = Channel<String>(Channel.BUFFERED)
    /** Addresses to open in the phone's browser (Google's sign-in page). */
    val openUrl = _openUrl.receiveAsFlow()

    private val _askNotifications = Channel<Unit>(Channel.CONFLATED)
    /** Ask Android for permission to post notifications (13+), at a moment it makes sense. */
    val askNotifications = _askNotifications.receiveAsFlow()

    private val _keepAlive = MutableStateFlow(container.keepAlive.enabled)
    val keepAlive: StateFlow<Boolean> = _keepAlive.asStateFlow()

    private val _checkingMail = MutableStateFlow(false)
    val checkingMail: StateFlow<Boolean> = _checkingMail.asStateFlow()

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
            DemoAction.CHECK_MAIL -> {
                val out = core.checkMail()
                when {
                    out.new > 0 -> "${out.new} new card${if (out.new == 1) "" else "s"} from college mail; " +
                        "${out.leftOut} other mail${if (out.leftOut == 1) "" else "s"} left out."
                    else -> "Checked: nothing new since the last check."
                }
            }
            DemoAction.PLAY_BRIEFING -> {
                val today = container.briefingPlayer.play { core.briefing().also { _briefing.value = it } }
                    ?: return "The briefing is already loading."
                if (today.audio.available) "Playing ElevenLabs' voice." else "Playing with the phone's own voice (no ElevenLabs key on the server)."
            }
            DemoAction.TEST_CALL -> {
                val out = core.testCall()
                when (out.status) {
                    "placed" -> if (_settings.value?.calls?.live == true) "Ringing your phone now." else "Call recorded: the server has no phone line yet."
                    "refused" -> "Not rung (${out.reason?.replace('_', ' ')}): it became one notification."
                    else -> "The call couldn't be placed: ${out.reason ?: out.status}."
                }
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
        _messages.trySend(UiMessage(message))
    }

    fun say(message: String, action: String, onAction: () -> Unit) {
        _messages.trySend(UiMessage(message, action, onAction))
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

    /** [channel] push (a notification) or call (the urgent call; consent comes first, in the UI). */
    fun remind(item: Item, beforeMinutes: Int, channel: String = "push") = action("item:${item.id}") {
        try {
            val r = container.core.setReminder(item.id, beforeMinutes, channel)
            val at = Time.parse(r.firesAt)?.let { Time.dayAndTime(it) } ?: "later"
            say(if (r.channel == "call") "We'll call you $at" else "Reminder set for $at")
            // The first reminder is when a notification permission makes sense to ask for (once;
            // after that the Settings row takes the student to the system settings).
            val ctx = container.appContext
            if (Notifications.needsAsking(ctx) && !Notifications.asked(ctx)) _askNotifications.trySend(Unit)
        } catch (e: ApiException) {
            say(e.detail)
        }
        container.cards.refresh()
    }

    /** The one-time consent screen said yes: calls on, then this call reminder. */
    fun enableCallsAndRemind(item: Item, beforeMinutes: Int) = viewModelScope.launch {
        try {
            container.core.setCalls(enabled = true)
            refreshSettings()
            remind(item, beforeMinutes, "call")
        } catch (e: ApiException) {
            say(e.detail)
        }
    }

    /** Done, with Undo: it leaves "due this week" and its reminders and calls are skipped. */
    fun markDone(item: Item) = action("done:${item.id}") {
        try {
            container.core.markDone(item.id)
            container.cards.refresh(wait = true)
            say("Marked done: ${item.title ?: "item"}", "Undo") { reopen(item) }
        } catch (e: ApiException) {
            say(e.detail)
        }
    }

    fun reopen(item: Item) = action("done:${item.id}") {
        try {
            container.core.reopen(item.id)
            say("Back on your list")
        } catch (e: ApiException) {
            say(e.detail)
        }
        container.cards.refresh(wait = true)
    }

    // --- settings: calls, Google, background ----------------------------------------------------
    fun refreshSettings() = viewModelScope.launch {
        try {
            _settings.value = container.core.settings()
            _callHistory.value = container.core.callHistory().calls
        } catch (e: ApiException) {
            // Settings shows what it has; the offline banner already says why.
        }
    }

    fun setCallsEnabled(enabled: Boolean) = action("calls") {
        try {
            val calls = container.core.setCalls(enabled = enabled)
            _settings.value = _settings.value?.copy(calls = calls)
            say(if (enabled) "Urgent calls are on" else "Urgent calls are off; your call reminders stay, as notifications")
        } catch (e: ApiException) {
            say(e.detail)
        }
        container.cards.refresh()
    }

    fun setQuietHours(start: String, end: String) = action("quiet") {
        try {
            val calls = container.core.setCalls(quietStart = start, quietEnd = end)
            _settings.value = _settings.value?.copy(calls = calls)
            say("Quiet hours: $start to $end")
        } catch (e: ApiException) {
            say(e.detail)
        }
    }

    fun testCall() = action("testcall") {
        try {
            val out = container.core.testCall()
            say(
                when (out.status) {
                    "placed" -> if (_settings.value?.calls?.live == true) "Calling you now" else "Call recorded (the server has no phone line yet)"
                    "refused" -> "Not called: ${out.reason?.replace('_', ' ')}. You'll get a notification instead."
                    else -> "The call couldn't be placed: ${out.reason ?: out.status}"
                },
            )
        } catch (e: ApiException) {
            say(e.detail)
        }
        refreshSettings()
    }

    fun connectGoogle() = action("google") {
        try {
            _openUrl.send(container.core.googleStart().url)
        } catch (e: ApiException) {
            say(e.detail)
        }
    }

    /** The browser brought Google's code back: finish connecting, as this student. */
    fun finishGoogle(code: String, state: String) = action("google") {
        try {
            val out = container.core.googleFinish(code, state)
            _settings.value = _settings.value?.copy(google = out.google)
            say("Google connected" + (out.google.email?.let { ": $it" } ?: ""))
            refreshSettings()
        } catch (e: ApiException) {
            say(e.detail)
        }
        container.cards.refresh()
    }

    fun disconnectGoogle() = action("google") {
        try {
            val out = container.core.googleDisconnect()
            _settings.value = _settings.value?.copy(google = out.google)
            say("Google disconnected, and what was read from it is gone")
        } catch (e: ApiException) {
            say(e.detail)
        }
        container.cards.refresh()
    }

    fun setKeepAlive(enabled: Boolean) {
        container.keepAlive.enabled = enabled
        _keepAlive.value = enabled
        PortalKeepAliveWorker.apply(container.appContext, enabled)
    }

    fun askForNotifications() {
        _askNotifications.trySend(Unit)
    }

    // --- college mail ---------------------------------------------------------------------------
    fun checkMail() {
        if (_checkingMail.value) return
        _checkingMail.value = true
        viewModelScope.launch {
            try {
                val out = container.core.checkMail()
                say(
                    when {
                        out.new == 1 -> "1 new card from college mail"
                        out.new > 1 -> "${out.new} new cards from college mail"
                        out.updated > 0 -> "Updated ${out.updated} card${if (out.updated == 1) "" else "s"}"
                        else -> "Nothing new in college mail"
                    },
                )
            } catch (e: ApiException) {
                say(e.detail)
            } finally {
                _checkingMail.value = false
            }
            container.cards.refresh(wait = true)
        }
    }

    // --- the briefing ----------------------------------------------------------------------------
    fun loadBriefing() = viewModelScope.launch {
        try {
            _briefing.value = container.core.briefing()
        } catch (e: ApiException) {
            // The card stays as it was; the offline banner says why.
        }
    }

    fun playBriefing() = viewModelScope.launch {
        // The player shows "loading" at once, so a second tap while it fetches does nothing.
        container.briefingPlayer.play { container.core.briefing().also { _briefing.value = it } }
    }

    fun stopBriefing() = container.briefingPlayer.stop()

    // --- the voice assistant -----------------------------------------------------------------------
    fun startVoice() = container.voice.start()

    fun stopVoice() = container.voice.stop()

    fun clearVoice() = container.voice.clear()

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
