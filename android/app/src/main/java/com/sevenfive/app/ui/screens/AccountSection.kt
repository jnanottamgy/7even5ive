package com.sevenfive.app.ui.screens

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.PersistableBundle
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.outlined.AlternateEmail
import androidx.compose.material.icons.outlined.DeleteForever
import androidx.compose.material.icons.outlined.Edit
import androidx.compose.material.icons.outlined.Key
import androidx.compose.material.icons.outlined.PersonAdd
import androidx.compose.material.icons.outlined.School
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.AccountState
import com.sevenfive.app.data.PersonalToken
import com.sevenfive.app.data.WhatsAppLink
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.Group
import com.sevenfive.app.ui.components.GroupDivider
import com.sevenfive.app.ui.components.GroupRow
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.util.Time

/** Settings' first section: who is signed in, and everything about the account itself. */
@Composable
fun AccountSection(vm: AppViewModel, onEditProfile: () -> Unit, onCreateAccount: () -> Unit) {
    val account by vm.account.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val token by vm.personalToken.collectAsStateWithLifecycle()
    val whatsapp by vm.whatsapp.collectAsStateWithLifecycle()
    val app = LocalAppColors.current
    var confirmDelete by remember { mutableStateOf(false) }
    var confirmLogOut by remember { mutableStateOf(false) }

    when (val a = account) {
        AccountState.Demo -> Group(
            header = "Account",
            footer = "Everyone who taps Try the demo shares this invented student. Your own account keeps your " +
                "deadlines, college mail and Google to yourself.",
        ) {
            GroupRow("You're trying the demo", icon = Icons.Outlined.School, iconColor = app.event,
                detail = "Demo Student · invented data")
            GroupDivider()
            GroupRow("Create your own account", icon = Icons.Outlined.PersonAdd, iconColor = MaterialTheme.colorScheme.primary,
                titleColor = MaterialTheme.colorScheme.primary, chevron = true, busy = "account" in busy) { onCreateAccount() }
            GroupDivider()
            GroupRow("Leave the demo", icon = Icons.AutoMirrored.Outlined.Logout, iconColor = app.tertiaryLabel,
                busy = "account" in busy) { vm.logOut() }
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
                val made = p?.personalToken?.createdAt?.let { Time.parse(it) }?.let { "made ${Time.dayAndTime(it)} · " }.orEmpty()
                GroupRow(
                    if (p?.personalToken?.exists == true) "Personal token for AI apps" else "Connect Claude or ChatGPT",
                    icon = Icons.Outlined.Key, iconColor = app.deadline, chevron = true, busy = "token" in busy,
                    detail = if (p?.personalToken?.exists == true) "${made}tap to replace it" else "A token for MCP, shown once",
                ) { vm.newPersonalToken() }
                if (p?.personalToken?.exists == true) {
                    GroupDivider()
                    GroupRow("Remove the token", icon = Icons.Outlined.Key, iconColor = app.tertiaryLabel,
                        busy = "token" in busy) { vm.deletePersonalToken() }
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
                Text("Copy it now: it is shown only once. Paste it into Claude or ChatGPT as the MCP server's " +
                    "Bearer token. It reads the same things the app shows and can't send anything.")
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

