package com.sevenfive.app.ui.screens

import android.webkit.CookieManager
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

    PushScaffold("Settings", onBack) { padding ->
        Column(
            Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(padding),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
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
