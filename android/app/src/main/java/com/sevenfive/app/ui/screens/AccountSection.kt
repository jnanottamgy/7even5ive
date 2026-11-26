package com.sevenfive.app.ui.screens

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PersistableBundle
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.outlined.AlternateEmail
import androidx.compose.material.icons.outlined.ContentCopy
import androidx.compose.material.icons.outlined.DeleteForever
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.Key
import androidx.compose.material.icons.outlined.PersonAdd
import androidx.compose.material.icons.outlined.School
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.Terminal
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.AccountState
import com.sevenfive.app.data.McpConnection
import com.sevenfive.app.data.PersonalToken
import com.sevenfive.app.data.WhatsAppLink
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.Group
import com.sevenfive.app.ui.components.GroupDivider
import com.sevenfive.app.ui.components.GroupRow
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.util.Time
import java.time.ZoneId

/** Settings' first section: who is signed in, and everything about the account itself. */
@Composable
fun AccountSection(vm: AppViewModel, onEditProfile: () -> Unit, onCreateAccount: () -> Unit) {
    val account by vm.account.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val token by vm.personalToken.collectAsStateWithLifecycle()
    val whatsapp by vm.whatsapp.collectAsStateWithLifecycle()
    val config by vm.authConfig.collectAsStateWithLifecycle()
    val app = LocalAppColors.current
    var confirmDelete by remember { mutableStateOf(false) }
    var confirmLogOut by remember { mutableStateOf(false) }
    var connectApps by rememberSaveable { mutableStateOf(false) }

    when (val a = account) {
        AccountState.Demo -> {
            // Whether this server has accounts at all (one from before accounts has only the demo).
            LaunchedEffect(Unit) { vm.refreshAuthConfig() }
            Group(
                header = "Account",
                footer = "Everyone who taps Try the demo shares this invented student. Your own account keeps your " +
                    "deadlines, college mail and Google to yourself.",
            ) {
                GroupRow("You're trying the demo", icon = Icons.Outlined.School, iconColor = app.event,
                    detail = "Demo Student · invented data")
                GroupDivider()
                val noAccounts = config?.usable == false
                GroupRow("Create your own account", icon = Icons.Outlined.PersonAdd, iconColor = MaterialTheme.colorScheme.primary,
                    titleColor = MaterialTheme.colorScheme.primary, chevron = !noAccounts, busy = "account" in busy,
                    enabled = !noAccounts,
                    detail = if (noAccounts) "This server has only the demo for now" else null) { onCreateAccount() }
                GroupDivider()
                GroupRow("Connect Claude Code or Codex", icon = Icons.Outlined.Terminal, iconColor = app.deadline,
                    chevron = true, detail = "Needs your own account") { connectApps = true }
                GroupDivider()
                GroupRow("Leave the demo", icon = Icons.AutoMirrored.Outlined.Logout, iconColor = app.tertiaryLabel,
                    busy = "account" in busy) { vm.logOut() }
            }
        }
        is AccountState.Ready -> {
            val p = a.me.profile
            Group(header = "Account") {
                GroupRow("@${p?.username ?: "you"}", icon = Icons.Outlined.AlternateEmail, iconColor = MaterialTheme.colorScheme.primary,
                    detail = listOfNotNull(p?.name, a.me.email ?: p?.email).joinToString(" · "))
                GroupDivider()
                GroupRow("Edit profile", icon = Icons.Outlined.Edit, iconColor = app.material, chevron = true,
                    detail = listOfNotNull(p?.college, p?.branch, p?.year?.let { "year $it" }).joinToString(" · ").ifBlank { null },
                    onClick = onEditProfile)
                GroupDivider()
                if (p?.whatsapp != null) {
                    GroupRow("WhatsApp linked", icon = Icons.AutoMirrored.Outlined.Chat, iconColor = LocalStatusColors.current.safe,
                        detail = "${p.whatsapp} · tap to unlink", busy = "whatsapp" in busy) { vm.unlinkWhatsApp() }
                } else {
                    GroupRow("Link WhatsApp", icon = Icons.AutoMirrored.Outlined.Chat, iconColor = LocalStatusColors.current.safe, chevron = true,
                        detail = "Forward class messages to the bot; urgent calls ring this number",
                        busy = "whatsapp" in busy) { vm.linkWhatsApp() }
                }
                GroupDivider()
                GroupRow("Connect Claude Code or Codex", icon = Icons.Outlined.Terminal, iconColor = app.deadline,
                    chevron = true, busy = "token" in busy,
                    detail = "One command on your computer, then sign in: no token to copy") { connectApps = true }
                if (p?.personalToken?.exists == true) {
                    GroupDivider()
                    val made = p.personalToken.createdAt?.let { Time.parse(it) }?.let { "Made ${Time.dayAndTime(it)}" }
                    GroupRow("Remove the personal token", icon = Icons.Outlined.Key, iconColor = app.tertiaryLabel,
                        detail = made, busy = "token" in busy) { vm.deletePersonalToken() }
                }
            }
            Spacer(Modifier.height(18.dp))
            Group(footer = "Deleting removes your cards, reminders, college mail, portal data and Google access, then the login itself.") {
                GroupRow("Log out", icon = Icons.AutoMirrored.Outlined.Logout, iconColor = app.tertiaryLabel,
                    busy = "account" in busy) { confirmLogOut = true }
                GroupDivider()
                GroupRow("Delete account", icon = Icons.Outlined.DeleteForever, iconColor = MaterialTheme.colorScheme.error,
                    titleColor = MaterialTheme.colorScheme.error, busy = "delete" in busy) { confirmDelete = true }
            }
        }
        else -> Unit
    }

    if (confirmLogOut) {
        AlertDialog(
            onDismissRequest = { confirmLogOut = false },
            title = { Text("Log out?") },
            text = { Text("This phone forgets your session, cards and portal login. Your account stays.") },
            confirmButton = { TextButton(onClick = { confirmLogOut = false; vm.logOut() }) { Text("Log out") } },
            dismissButton = { TextButton(onClick = { confirmLogOut = false }) { Text("Cancel") } },
        )
    }
    if (confirmDelete) DeleteDialog(onDismiss = { confirmDelete = false }) {
        confirmDelete = false
        vm.deleteAccount()
    }
    val ready = account as? AccountState.Ready
    if (connectApps && (ready != null || account == AccountState.Demo)) {
        val personal = ready?.me?.profile?.personalToken
        ConnectAppsDialog(
            vm,
            demo = ready == null,
            // The demo can't have a token: the server refuses it one.
            onUseToken = if (ready == null) null else ({
                connectApps = false
                vm.newPersonalToken()
            }),
            tokenMade = if (personal?.exists == true) personal.createdAt?.let { Time.parse(it) }?.let { Time.dayAndTime(it) } ?: "" else null,
            onDismiss = { connectApps = false },
        )
    }
    token?.let { TokenDialog(it) { vm.dismissPersonalToken() } }
    whatsapp?.let { WhatsAppDialog(it) { vm.dismissWhatsApp() } }
}

@Composable
private fun DeleteDialog(onDismiss: () -> Unit, onDelete: () -> Unit) {
    var typed by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Delete your account?") },
        text = {
            Column {
                Text("Everything goes, for good: your cards, reminders, call history, college mail read, portal " +
                    "data, Google access and your login. This can't be undone.")
                Spacer(Modifier.height(12.dp))
                Text("Type DELETE to confirm.", style = MaterialTheme.typography.labelLarge)
                OutlinedTextField(typed, { typed = it.trim().uppercase() }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(onClick = onDelete, enabled = typed == "DELETE") {
                Text("Delete", color = if (typed == "DELETE") MaterialTheme.colorScheme.error else LocalAppColors.current.tertiaryLabel)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

/** What Claude Code runs to add 7even5ive (its browser sign-in comes after, from /mcp). */
internal fun claudeCodeCommand(mcpUrl: String) = "claude mcp add --transport http --scope user 7even5ive $mcpUrl"

/** What Codex runs to add 7even5ive; it opens the browser to sign in by itself. */
internal fun codexCommand(mcpUrl: String) = "codex mcp add 7even5ive --url $mcpUrl"

/** "connected Fri 27 Nov, 10:15 AM · last used never", in the phone's zone. */
internal fun connectionDetail(c: McpConnection, zone: ZoneId = ZoneId.systemDefault()): String {
    val connected = Time.parse(c.connectedAt)?.let { "connected ${Time.dayAndTime(it, zone)}" }
    val used = Time.parse(c.lastUsedAt)?.let { Time.dayAndTime(it, zone) } ?: "never"
    return listOfNotNull(connected, "last used $used").joinToString(" · ")
}

/**
 * Settings → Connect Claude Code or Codex. One command on the student's computer adds 7even5ive;
 * then the app opens a browser where they sign in with their 7even5ive email or username and
 * password (OAuth), so no token is ever copied. Below, the apps connected so far, each with
 * Disconnect. The demo sees the commands but can't sign in, so it has no list. [onUseToken]: the
 * older personal token, for MCP apps that can only send an Authorization header; [tokenMade]
 * when one exists (making a new one replaces it).
 */
@Composable
private fun ConnectAppsDialog(
    vm: AppViewModel,
    demo: Boolean,
    onUseToken: (() -> Unit)?,
    tokenMade: String?,
    onDismiss: () -> Unit,
) {
    val state by vm.connections.collectAsStateWithLifecycle()
    val servers by vm.servers.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val app = LocalAppColors.current
    var confirm by remember { mutableStateOf<McpConnection?>(null) }
    var replaceToken by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { vm.loadConnections() }
    // The server's own address once it has answered; meanwhile (or from an older server) this one's.
    val url = state.mcpUrl ?: "${servers.coreUrl.trimEnd('/')}/mcp"
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Connect Claude Code or Codex") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Text(
                    "Run one command on your computer. Your browser then opens and you sign in: there's " +
                        "no token to copy. The AI app can read what this app shows; it can't send anything.",
                    style = MaterialTheme.typography.bodyMedium,
                )
                if (demo) {
                    Spacer(Modifier.height(10.dp))
                    Text(
                        "Connecting needs your own account: the demo can't sign in.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                Spacer(Modifier.height(16.dp))
                CommandBlock(
                    "Claude Code", claudeCodeCommand(url),
                    "In Claude Code, type /mcp, choose 7even5ive and Authenticate. Your browser opens: sign " +
                        "in with your 7even5ive email or username and password.",
                )
                Spacer(Modifier.height(16.dp))
                CommandBlock("Codex", codexCommand(url), "Codex opens your browser to sign in.")
                if (!demo) {
                    Spacer(Modifier.height(18.dp))
                    Text("Connected apps", style = MaterialTheme.typography.labelLarge)
                    Spacer(Modifier.height(6.dp))
                    state.problem?.let {
                        Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                    }
                    when {
                        state.loading && state.connections.isEmpty() ->
                            CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        state.connections.isEmpty() && state.problem == null ->
                            Text("No AI apps connected yet.", style = MaterialTheme.typography.bodyMedium,
                                color = app.secondaryLabel)
                        else -> state.connections.forEach { c ->
                            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(c.label, style = MaterialTheme.typography.bodyLarge)
                                    Text(connectionDetail(c), style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel)
                                }
                                TextButton(onClick = { confirm = c }, enabled = "mcp:${c.id}" !in busy) {
                                    Text("Disconnect", color = MaterialTheme.colorScheme.error)
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Done") } },
        dismissButton = onUseToken?.let { use ->
            { TextButton(onClick = { if (tokenMade != null) replaceToken = true else use() }) { Text("Use a token instead") } }
        },
    )
    confirm?.let { c ->
        AlertDialog(
            onDismissRequest = { confirm = null },
            title = { Text("Disconnect ${c.label}?") },
            text = { Text("It can't reach your 7even5ive account any more. You can connect it again at any time.") },
            confirmButton = {
                TextButton(onClick = {
                    confirm = null
                    vm.disconnect(c)
                }) { Text("Disconnect", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("Cancel") } },
        )
    }
    if (replaceToken && onUseToken != null) {
        AlertDialog(
            onDismissRequest = { replaceToken = false },
            title = { Text("Make a new personal token?") },
            text = {
                Text(
                    (if (tokenMade.isNullOrBlank()) "Your current token" else "The token made $tokenMade") +
                        " stops working, and apps using it can't reach your account until they get the new one.",
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    replaceToken = false
                    onUseToken()
                }) { Text("Make a new one") }
            },
            dismissButton = { TextButton(onClick = { replaceToken = false }) { Text("Cancel") } },
        )
    }
}

/** One app's command, to copy or send to the computer, and what to do after running it. */
@Composable
private fun CommandBlock(app: String, command: String, then: String) {
    val context = LocalContext.current
    val colors = LocalAppColors.current
    var copied by remember(command) { mutableStateOf(false) }
    Text(app, style = MaterialTheme.typography.labelLarge)
    Spacer(Modifier.height(6.dp))
    Text(
        command,
        fontFamily = FontFamily.Monospace,
        style = MaterialTheme.typography.bodySmall,
        modifier = Modifier
            .fillMaxWidth()
            .glassSurface(shape = MaterialTheme.shapes.small, strong = true)
            .padding(10.dp),
    )
    Row(verticalAlignment = Alignment.CenterVertically) {
        TextButton(onClick = {
            copyText(context, command)
            copied = true
        }) {
            Icon(Icons.Outlined.ContentCopy, contentDescription = null, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(6.dp))
            Text(if (copied) "Copied" else "Copy")
        }
        TextButton(onClick = { shareText(context, command, "Connect 7even5ive to $app") }) {
            Icon(Icons.Outlined.Share, contentDescription = null, modifier = Modifier.size(16.dp))
            Spacer(Modifier.width(6.dp))
            Text("Share")
        }
    }
    Text(then, style = MaterialTheme.typography.bodySmall, color = colors.secondaryLabel)
}

/** A command is no secret: copied plainly, so it shows in the clipboard preview. */
private fun copyText(context: Context, text: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager ?: return
    clipboard.setPrimaryClip(ClipData.newPlainText("7even5ive command", text))
}

/** Android's share sheet: to WhatsApp, mail or Nearby Share, to reach the student's computer. */
private fun shareText(context: Context, text: String, subject: String) {
    val send = Intent(Intent.ACTION_SEND)
        .setType("text/plain")
        .putExtra(Intent.EXTRA_TEXT, text)
        .putExtra(Intent.EXTRA_SUBJECT, subject)
    runCatching {
        context.startActivity(Intent.createChooser(send, "Send it to your computer").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
}

/** Copies a secret so Android hides it in the clipboard preview (13+), and can clear it after. */
private fun copySecret(context: Context, text: String?) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager ?: return
    if (text == null) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) clipboard.clearPrimaryClip()
        else clipboard.setPrimaryClip(ClipData.newPlainText("", "")) // nothing to clear with before 9
        return
    }
    val clip = ClipData.newPlainText("7even5ive token", text)
    clip.description.extras = PersistableBundle().apply { putBoolean("android.content.extra.IS_SENSITIVE", true) }
    clipboard.setPrimaryClip(clip)
}

@Composable
private fun TokenDialog(token: PersonalToken, onDone: () -> Unit) {
    val context = LocalContext.current
    var copied by rememberSaveable { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = {},
        title = { Text("Your personal token") },
        text = {
            Column {
                Text("Copy it now: it is shown only once. It is for MCP apps that let you set an Authorization " +
                    "header: give them the server below, with this token as the Bearer token. ChatGPT's " +
                    "connectors sign in with OAuth instead: give ChatGPT only the server address. The token " +
                    "reads the same things the app shows and can't send anything.")
                Spacer(Modifier.height(10.dp))
                Text("Server", style = MaterialTheme.typography.labelLarge)
                Text(token.mcpUrl, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(8.dp))
                Text("Token", style = MaterialTheme.typography.labelLarge)
                Text(token.token, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = {
            TextButton(onClick = {
                copySecret(context, token.token)
                copied = true
            }) { Text(if (copied) "Copied" else "Copy token") }
        },
        dismissButton = {
            TextButton(onClick = {
                if (copied) copySecret(context, null) // off the clipboard once it has been pasted
                onDone()
            }) { Text("Done") }
        },
    )
}

@Composable
private fun WhatsAppDialog(link: WhatsAppLink, onDone: () -> Unit) {
    val context = LocalContext.current
    val clipboard = LocalClipboardManager.current
    val expires = Time.parse(link.expiresAt)?.let { Time.dayAndTime(it) }
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text("Link WhatsApp") },
        text = {
            Column {
                Text(
                    if (link.botNumber != null) "Send this message to the 7even5ive bot (${link.botNumber}) from your " +
                        "own WhatsApp. The bot links the number it comes from."
                    else "Send this message to the 7even5ive bot from your own WhatsApp. The bot links the number it comes from.",
                )
                Spacer(Modifier.height(12.dp))
                Text(link.message, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.titleMedium)
                if (expires != null) {
                    Spacer(Modifier.height(6.dp))
                    Text("Works until $expires.", style = MaterialTheme.typography.bodySmall,
                        color = LocalAppColors.current.secondaryLabel)
                }
            }
        },
        confirmButton = {
            if (link.link != null) {
                TextButton(onClick = {
                    runCatching {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(link.link)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                    }
                    onDone()
                }) { Text("Open WhatsApp") }
            } else {
                TextButton(onClick = { clipboard.setText(AnnotatedString(link.message)); onDone() }) { Text("Copy message") }
            }
        },
        dismissButton = { TextButton(onClick = onDone) { Text("Close") } },
    )
}

