package com.sevenfive.app.ui.screens

import android.webkit.CookieManager
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.foundation.layout.heightIn
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.BuildConfig
import com.sevenfive.app.data.ServerConfig
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.util.Diagnostics

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(vm: AppViewModel, onBack: () -> Unit) {
    val current by vm.servers.collectAsStateWithLifecycle()
    var host by remember { mutableStateOf(current.coreUrl.substringAfter("://").substringBefore(':').substringBefore('/')) }
    var core by remember { mutableStateOf(current.coreUrl) }
    var portmax by remember { mutableStateOf(current.portmaxUrl) }
    var portal by remember { mutableStateOf(current.portalUrl) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Server") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") }
                },
            )
        },
    ) { inner ->
        Column(
            Modifier.padding(inner).fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            val searching by vm.searching.collectAsStateWithLifecycle()
            val online = vm.container.servers.buildDefault.takeIf { it.isOnline }
            Text("Where the app gets its data", style = MaterialTheme.typography.titleMedium)
            Text(
                if (current.isOnline) "Online server: ${current.coreUrl}" else "Laptop: ${current.coreUrl}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (online != null && !current.isOnline) {
                Button(
                    onClick = { vm.useOnline(); onBack() },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text("Use the online server") }
            }
            Row {
                OutlinedTextField(
                    value = host,
                    onValueChange = { host = it.trim() },
                    label = { Text("Online address or laptop IP") },
                    placeholder = { Text("https://… or 192.168.1.20") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                Button(
                    onClick = { vm.connectTo(host); onBack() },
                    enabled = host.isNotBlank(),
                    modifier = Modifier.padding(top = 8.dp),
                ) { Text("Connect") }
            }
            OutlinedButton(
                onClick = { vm.findLaptop() },
                enabled = !searching,
                modifier = Modifier.fillMaxWidth(),
            ) { Text(if (searching) "Looking…" else "Find a laptop on this Wi-Fi") }

            HorizontalDivider()
            Text("Addresses (advanced)", style = MaterialTheme.typography.titleMedium)
            UrlField("7even5ive core (cards, approvals)", core) { core = it }
            UrlField("PortMax (portal settings, upload)", portmax) { portmax = it }
            UrlField("College portal", portal) { portal = it }
            Button(
                onClick = {
                    vm.saveServers(ServerConfig(core, portmax, portal))
                    onBack()
                },
                enabled = listOf(core, portmax, portal).all { it.startsWith("http://") || it.startsWith("https://") },
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Save and reconnect") }

            HorizontalDivider()
            Text("Portal session", style = MaterialTheme.typography.titleMedium)
            Text(
                "Your portal login lives only in this phone's browser storage. This logs it out here.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            OutlinedButton(onClick = {
                CookieManager.getInstance().removeAllCookies(null)
                CookieManager.getInstance().flush()
                vm.container.portalStore.forget()
                vm.say("Logged out of the portal on this phone")
            }) { Text("Log out of portal on this phone") }

            HorizontalDivider()
            DiagnosticsSection(vm)

            HorizontalDivider()
            Text(
                "Signed in as the demo student (built in) · college ${BuildConfig.COLLEGE} · v${BuildConfig.VERSION_NAME}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.outline,
            )
        }
    }
}

@Composable
private fun UrlField(label: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = { onChange(it.trim()) },
        label = { Text(label) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun DiagnosticsSection(vm: AppViewModel) {
    val context = vm.container.appContext
    var report by remember { mutableStateOf(Diagnostics.report(context)) }
    val clipboard = LocalClipboardManager.current
    Text("Diagnostics", style = MaterialTheme.typography.titleMedium)
    if (report == null) {
        Text(
            "No crashes recorded.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        return
    }
    Text(
        "Why the app last closed. Copy it and send it to the team. It holds no messages or passwords.",
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Text(
        report!!.take(3_000),
        style = MaterialTheme.typography.bodySmall,
        fontFamily = FontFamily.Monospace,
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(max = 280.dp)
            .verticalScroll(rememberScrollState()),
    )
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = {
            clipboard.setText(AnnotatedString(report!!))
            vm.say("Copied: paste it into a message")
        }) { Text("Copy") }
        OutlinedButton(onClick = {
            Diagnostics.clear(context)
            report = Diagnostics.report(context)
        }) { Text("Clear") }
    }
}
