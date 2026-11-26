package com.sevenfive.app.ui.screens

import android.content.Intent
import android.provider.Settings
import android.webkit.CookieManager
import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.Bedtime
import androidx.compose.material.icons.outlined.Call
import androidx.compose.material.icons.outlined.GraphicEq
import androidx.compose.material.icons.outlined.LinkOff
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.PhoneInTalk
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.TextButton
import androidx.lifecycle.compose.LifecycleResumeEffect
import com.sevenfive.app.data.CallRecord
import com.sevenfive.app.notify.Notifications
import com.sevenfive.app.notify.Push
import com.sevenfive.app.ui.LocalOpenVoice
import com.sevenfive.app.ui.components.CallConsentDialog
import com.sevenfive.app.ui.components.GroupSwitchRow
import com.sevenfive.app.util.Time
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.BugReport
import androidx.compose.material.icons.outlined.Cloud
import androidx.compose.material.icons.outlined.ContentCopy
import androidx.compose.material.icons.outlined.DeleteOutline
import androidx.compose.material.icons.outlined.Laptop
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material.icons.outlined.Restore
import androidx.compose.material.icons.outlined.Science
import androidx.compose.material.icons.outlined.SlowMotionVideo
import androidx.compose.material.icons.outlined.Wifi
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.BuildConfig
import com.sevenfive.app.data.ServerConfig
import com.sevenfive.app.portal.PortalCheck
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.Group
import com.sevenfive.app.ui.components.GroupAction
import com.sevenfive.app.ui.components.GroupDivider
import com.sevenfive.app.ui.components.GroupField
import com.sevenfive.app.ui.components.GroupRow
import com.sevenfive.app.ui.components.PushScaffold
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.util.Diagnostics

@Composable
fun SettingsScreen(vm: AppViewModel, onBack: () -> Unit, onPortalCheck: () -> Unit = {}) {
    val current by vm.servers.collectAsStateWithLifecycle()
    var host by remember { mutableStateOf(current.coreUrl.substringAfter("://").substringBefore(':').substringBefore('/')) }
    var core by remember { mutableStateOf(current.coreUrl) }
    var portmax by remember { mutableStateOf(current.portmaxUrl) }
    var portal by remember { mutableStateOf(current.portalUrl) }
    val app = LocalAppColors.current
    val status = LocalStatusColors.current

    LifecycleResumeEffect(Unit) {
        // Also on coming back from Google's sign-in page in the browser.
        vm.refreshSettings()
        onPauseOrDispose { }
    }

    PushScaffold("Settings", onBack) { padding ->
        Column(
            Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(padding),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            GoogleSection(vm)
            CallsSection(vm)
            NotificationsSection(vm)
            VoiceSection(vm)

            val searching by vm.searching.collectAsStateWithLifecycle()
            val resetting by vm.resetting.collectAsStateWithLifecycle()
            val online = vm.container.servers.buildDefault.takeIf { it.isOnline }

            Group(header = "Data source", footer = "Where the app gets its cards. The online demo needs no laptop.") {
                GroupRow(
                    if (current.isOnline) "Online server" else "Laptop",
                    icon = if (current.isOnline) Icons.Outlined.Cloud else Icons.Outlined.Laptop,
                    iconColor = if (current.isOnline) app.material else app.event,
                    detail = current.coreUrl,
                )
                if (online != null && !current.isOnline) {
                    GroupDivider()
                    GroupRow("Use the online server", icon = Icons.Outlined.Cloud, iconColor = app.material,
                        titleColor = MaterialTheme.colorScheme.primary, chevron = true) {
                        vm.useOnline()
                        onBack()
                    }
                }
                GroupDivider()
                GroupRow(
                    if (searching) "Looking…" else "Find a laptop on this Wi-Fi",
                    icon = Icons.Outlined.Wifi,
                    iconColor = status.safe,
                    enabled = !searching,
                    busy = searching,
                ) { vm.findLaptop() }
                GroupDivider(inset = false)
                GroupField(host, { host = it.trim() }, "Online address or laptop IP", "https://… or 192.168.1.20")
                GroupDivider(inset = false)
                GroupAction("Connect", onClick = { vm.connectTo(host); onBack() }, enabled = host.isNotBlank())
            }

            Group(header = "Demo tour", footer = "Runs the whole demo from this phone, step by step: each step opens " +
                "the right tab, says what to tell the audience, and makes the live moments happen. Works with " +
                "the online demo server.") {
                GroupRow("Start the tour (fresh)", icon = Icons.Outlined.PlayArrow, iconColor = MaterialTheme.colorScheme.primary,
                    enabled = !resetting, chevron = true) {
                    vm.resetDemo()
                    vm.startTour()
                }
                GroupDivider()
                GroupRow("Start, keep data", icon = Icons.Outlined.SlowMotionVideo, iconColor = app.deadline, chevron = true) {
                    vm.startTour()
                }
                GroupDivider()
                GroupRow(if (resetting) "Resetting…" else "Reset demo data", icon = Icons.Outlined.Restore,
                    iconColor = app.notice, enabled = !resetting, busy = resetting) { vm.resetDemo() }
            }

            val checkStart by vm.portalCheckUrl.collectAsStateWithLifecycle()
            var checkUrl by remember { mutableStateOf(checkStart) }
            val checkTarget = PortalCheck.normalise(checkUrl)
            Group(header = "Test a college portal", footer = "Opens your college's real portal in the app, to see " +
                "whether it lets you log in from an app. You log in yourself; nothing is read from the page or " +
                "sent anywhere, and the demo keeps using its own portal.") {
                GroupField(checkUrl, { checkUrl = it.trim() }, "Portal address", PortalCheck.DEFAULT_URL)
                GroupDivider(inset = false)
                GroupRow("Open portal test", icon = Icons.Outlined.Science, iconColor = app.event,
                    enabled = checkTarget != null, chevron = true) {
                    if (checkTarget != null) {
                        vm.setPortalCheckUrl(checkTarget)
                        onPortalCheck()
                    }
                }
            }

            Group(header = "Portal session", footer = "Your portal login lives only in this phone's browser storage.") {
                GroupRow("Log out of portal on this phone", icon = Icons.AutoMirrored.Outlined.Logout,
                    iconColor = MaterialTheme.colorScheme.error, titleColor = MaterialTheme.colorScheme.error) {
                    CookieManager.getInstance().removeAllCookies(null)
                    CookieManager.getInstance().flush()
                    vm.container.portalStore.forget()
                    vm.say("Logged out of the portal on this phone")
                }
            }

            Group(header = "Addresses (advanced)") {
                GroupField(core, { core = it.trim() }, "7even5ive core (cards, approvals)")
                GroupDivider(inset = false)
                GroupField(portmax, { portmax = it.trim() }, "PortMax (portal settings, upload)")
                GroupDivider(inset = false)
                GroupField(portal, { portal = it.trim() }, "College portal")
                GroupDivider(inset = false)
                GroupAction(
                    "Save and reconnect",
                    onClick = {
                        vm.saveServers(ServerConfig(core, portmax, portal))
                        onBack()
                    },
                    enabled = listOf(core, portmax, portal).all { it.startsWith("http://") || it.startsWith("https://") },
                )
            }

            DiagnosticsSection(vm)

            Text(
                "Signed in as the demo student (built in) · college ${BuildConfig.COLLEGE} · v${BuildConfig.VERSION_NAME}",
                style = MaterialTheme.typography.bodySmall,
                color = app.tertiaryLabel,
                modifier = Modifier.padding(horizontal = 16.dp),
            )
        }
    }
}

@Composable
private fun GoogleSection(vm: AppViewModel) {
    val settings by vm.settings.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val app = LocalAppColors.current
    val google = settings?.google
    Group(
        header = "Google account",
        footer = "One sign-in, on the server: Gmail read-only for college mail, Calendar only for events " +
            "you approve, Classroom for coursework due dates. This phone never holds a Google token.",
    ) {
        when {
            google == null -> GroupRow("Checking…", icon = Icons.Outlined.AccountCircle, iconColor = app.tertiaryLabel)
            !google.configured -> GroupRow(
                "Not set up on the server yet", icon = Icons.Outlined.AccountCircle, iconColor = app.tertiaryLabel,
                detail = "The team adds a Google OAuth client (docs/keys.md). College mail uses the demo mailbox until then.",
            )
            google.connected -> {
                GroupRow("Connected", icon = Icons.Outlined.AccountCircle, iconColor = LocalStatusColors.current.safe,
                    detail = google.email ?: "Google account")
                GroupDivider()
                val parts = listOfNotNull(
                    "Gmail (read-only)".takeIf { google.gmail },
                    "Calendar".takeIf { google.calendar },
                    "Classroom".takeIf { google.classroom },
                )
                GroupRow("Allowed", icon = Icons.Outlined.Sync, iconColor = app.material,
                    detail = parts.joinToString(" · ").ifBlank { "Nothing: connect again and allow access" })
                GroupDivider()
                GroupRow("Disconnect", icon = Icons.Outlined.LinkOff, iconColor = MaterialTheme.colorScheme.error,
                    titleColor = MaterialTheme.colorScheme.error, busy = "google" in busy) { vm.disconnectGoogle() }
            }
            else -> GroupRow("Connect Google", icon = Icons.Outlined.AccountCircle, iconColor = MaterialTheme.colorScheme.primary,
                titleColor = MaterialTheme.colorScheme.primary, chevron = true, busy = "google" in busy,
                detail = "Opens Google's sign-in in your browser") { vm.connectGoogle() }
        }
    }
}

@Composable
private fun CallsSection(vm: AppViewModel) {
    val settings by vm.settings.collectAsStateWithLifecycle()
    val history by vm.callHistory.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val app = LocalAppColors.current
    val calls = settings?.calls
    var consent by remember { mutableStateOf(false) }
    var quiet by remember { mutableStateOf(false) }
    Group(
        header = "Urgent call",
        footer = when {
            calls == null -> null
            !calls.live -> "The server has no phone line yet (ElevenLabs): calls are recorded and shown here, not rung."
            else -> "A short ElevenLabs voice call before something you picked with \"Call me\". At most " +
                "${calls.maxPerDay} a day, never in quiet hours; a missed call becomes one notification."
        },
    ) {
        GroupSwitchRow(
            "Let 7even5ive call me",
            checked = calls?.enabled == true,
            onChange = { on -> if (on) consent = true else vm.setCallsEnabled(false) },
            icon = Icons.Outlined.PhoneInTalk,
            iconColor = app.event,
            detail = calls?.phone ?: "No number on file for calls",
            enabled = calls != null && "calls" !in busy,
        )
        GroupDivider()
        GroupRow("Quiet hours", icon = Icons.Outlined.Bedtime, iconColor = app.exam,
            detail = calls?.let { "${it.quietStart} to ${it.quietEnd}, India time" } ?: "—",
            chevron = true, enabled = calls != null) { quiet = true }
        GroupDivider()
        GroupRow("Test call now", icon = Icons.Outlined.Call, iconColor = LocalStatusColors.current.safe,
            detail = "About the soonest thing due, under every rule above",
            enabled = calls?.enabled == true, busy = "testcall" in busy) { vm.testCall() }
        history.take(3).forEach { record ->
            GroupDivider()
            GroupRow(callTitle(record), detail = callDetail(record))
        }
    }
    if (consent) {
        CallConsentDialog(calls, onAccept = {
            consent = false
            vm.setCallsEnabled(true)
        }, onDismiss = { consent = false })
    }
    if (quiet && calls != null) {
        QuietHoursDialog(calls.quietStart, calls.quietEnd, onSave = { start, end ->
            quiet = false
            vm.setQuietHours(start, end)
        }, onDismiss = { quiet = false })
    }
}

private fun callTitle(record: CallRecord): String = when (record.status) {
    "answered" -> "Answered"
    "missed" -> "Missed: you got a notification"
    "voicemail" -> "Voicemail: you got a notification"
    "refused" -> "Not called (${record.reason?.replace('_', ' ') ?: "a rule"})"
    "failed" -> "Couldn't be placed"
    else -> "Placed"
} + (record.title?.let { " · $it" } ?: "")

private fun callDetail(record: CallRecord): String =
    listOfNotNull(Time.parse(record.createdAt)?.let { Time.dayAndTime(it) },
        record.durationSeconds?.takeIf { it > 0 }?.let { "${it}s" }).joinToString(" · ")

@Composable
private fun QuietHoursDialog(start: String, end: String, onSave: (String, String) -> Unit, onDismiss: () -> Unit) {
    var from by remember { mutableStateOf(start) }
    var to by remember { mutableStateOf(end) }
    val valid = Regex("^([01]\\d|2[0-3]):[0-5]\\d$")
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Quiet hours") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("No calls between these times (24-hour, India time). A call that falls inside " +
                    "becomes a notification.", style = MaterialTheme.typography.bodySmall)
                OutlinedTextField(from, { from = it.trim() }, label = { Text("From (e.g. 22:00)") }, singleLine = true,
                    isError = !valid.matches(from))
                OutlinedTextField(to, { to = it.trim() }, label = { Text("To (e.g. 08:00)") }, singleLine = true,
                    isError = !valid.matches(to))
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(from, to) }, enabled = valid.matches(from) && valid.matches(to)) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun NotificationsSection(vm: AppViewModel) {
    val settings by vm.settings.collectAsStateWithLifecycle()
    val keepAlive by vm.keepAlive.collectAsStateWithLifecycle()
    val context = vm.container.appContext
    val activity = androidx.compose.ui.platform.LocalContext.current as? android.app.Activity
    val app = LocalAppColors.current
    // Read again whenever Settings comes back to the front (after the prompt or system settings).
    var permitted by remember { mutableStateOf(Notifications.permitted(context)) }
    LifecycleResumeEffect(Unit) {
        permitted = Notifications.permitted(context)
        onPauseOrDispose { }
    }
    Group(
        header = "Notifications and background",
        footer = "Notifications are only your own reminders and a missed urgent call. The briefing and " +
            "attendance stay in the app.",
    ) {
        GroupRow(
            if (permitted) "Notifications are on" else "Allow notifications",
            icon = Icons.Outlined.Notifications,
            iconColor = if (permitted) LocalStatusColors.current.safe else MaterialTheme.colorScheme.error,
            detail = if (permitted) "Reminders reach you even when the app is closed" else "Reminders will only show in the app",
            chevron = !permitted,
        ) {
            if (Notifications.needsAsking(context) && activity != null && Notifications.promptStillShows(activity)) {
                vm.askForNotifications()
            } else {
                context.startActivity(
                    Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            }
        }
        GroupDivider()
        val instant = Push.configured && settings?.push?.wakeups == true
        GroupRow("Delivery", icon = Icons.Outlined.Sync, iconColor = app.material,
            detail = if (instant) "At once (Firebase wakes the phone; no content passes through it)"
            else "At once while the app is open, within 15 minutes when it's closed")
        GroupDivider()
        GroupSwitchRow(
            "Keep the portal logged in",
            checked = keepAlive,
            onChange = { vm.setKeepAlive(it) },
            icon = Icons.Outlined.Sync,
            iconColor = app.deadline,
            detail = "Every 30 minutes in the background, from this phone, with your own session",
        )
    }
}

@Composable
private fun VoiceSection(vm: AppViewModel) {
    val settings by vm.settings.collectAsStateWithLifecycle()
    val openVoice = LocalOpenVoice.current
    val app = LocalAppColors.current
    val voice = settings?.voice
    Group(header = "Voice (ElevenLabs)") {
        GroupRow("Ask 7even5ive", icon = Icons.Outlined.Mic, iconColor = MaterialTheme.colorScheme.primary,
            detail = if (voice?.assistant == true) "Talk about your week; it uses the same rules as the app"
            else "Needs ElevenLabs on the server (docs/keys.md)",
            chevron = true, enabled = openVoice != null) { openVoice?.invoke() }
        GroupDivider()
        GroupRow("Briefing voice", icon = Icons.Outlined.GraphicEq, iconColor = app.event,
            detail = if (voice?.briefingAudio == true) "ElevenLabs" else "This phone's own voice")
    }
}

@Composable
private fun DiagnosticsSection(vm: AppViewModel) {
    val context = vm.container.appContext
    var report by remember { mutableStateOf(Diagnostics.report(context)) }
    val clipboard = LocalClipboardManager.current
    val app = LocalAppColors.current
    val shown = report
    if (shown == null) {
        Group(header = "Diagnostics") {
            GroupRow("No crashes recorded", icon = Icons.Outlined.BugReport, iconColor = LocalStatusColors.current.safe)
        }
        return
    }
    Group(header = "Diagnostics", footer = "Why the app last closed. Copy it and send it to the team. It holds no messages or passwords.") {
        Text(
            shown.take(3_000),
            style = MaterialTheme.typography.bodySmall,
            fontFamily = FontFamily.Monospace,
            color = app.secondaryLabel,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 280.dp)
                .verticalScroll(rememberScrollState())
                .padding(14.dp),
        )
        GroupDivider(inset = false)
        GroupRow("Copy", icon = Icons.Outlined.ContentCopy, iconColor = app.material) {
            clipboard.setText(AnnotatedString(shown))
            vm.say("Copied: paste it into a message")
        }
        GroupDivider()
        GroupRow("Clear", icon = Icons.Outlined.DeleteOutline, iconColor = MaterialTheme.colorScheme.error) {
            Diagnostics.clear(context)
            report = Diagnostics.report(context)
        }
    }
}
