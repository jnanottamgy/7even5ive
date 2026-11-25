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
import com.sevenfive.app.portal.PortalStatus
import com.sevenfive.app.util.Time
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** An approval the student already tapped this session, kept on screen as proof it ran once. */
data class DoneApproval(val approval: Approval, val title: String)

class AppViewModel(val container: AppContainer) : ViewModel() {
    val cards: StateFlow<CardsState> = container.cards.state
    val portal: StateFlow<PortalStatus> = container.portalStore.status
    val servers: StateFlow<ServerConfig> = container.servers.config

    private val _busy = MutableStateFlow<Set<String>>(emptySet())
    /** Keys of actions in flight (approval tokens, "rem:<id>"), so buttons can't double-fire. */
    val busy: StateFlow<Set<String>> = _busy.asStateFlow()

    private val _approved = MutableStateFlow<List<DoneApproval>>(emptyList())
    val approved: StateFlow<List<DoneApproval>> = _approved.asStateFlow()

    private val _messages = Channel<String>(Channel.BUFFERED)
    /** One-off messages for the snackbar: the server's own words when it refuses. */
    val messages = _messages.receiveAsFlow()

    fun refresh() = viewModelScope.launch { container.cards.refresh() }

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
