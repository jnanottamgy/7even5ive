package com.sevenfive.app.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.PhoneInTalk
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.sevenfive.app.data.CallSettings
import com.sevenfive.app.ui.theme.LocalAppColors

/**
 * The one-time consent before 7even5ive may ring the student (decision P4). It says exactly
 * what the call is and is not, and nothing is turned on until the student taps "Turn on".
 */
@Composable
fun CallConsentDialog(calls: CallSettings?, onAccept: () -> Unit, onDismiss: () -> Unit) {
    val app = LocalAppColors.current
    val number = calls?.phone
    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(Icons.Outlined.PhoneInTalk, contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
        title = { Text("Let 7even5ive call you?") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    if (number != null) "Your phone ($number) rings shortly before something you choose is due."
                    else "Your phone rings shortly before something you choose is due. There's no number on file " +
                        "yet, so the server will turn calls into notifications until one is set.",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(
                    "• Only for items you pick with \"Call me\"\n" +
                        "• Never between ${calls?.quietStart ?: "22:00"} and ${calls?.quietEnd ?: "08:00"}, " +
                        "at most ${calls?.maxPerDay ?: 2} a day, once per item\n" +
                        "• A short voice reminder, at most ${calls?.maxSeconds ?: 90} seconds; it can't change or send anything\n" +
                        "• Missed? You get one notification instead, never a second call",
                    style = MaterialTheme.typography.bodySmall,
                    color = app.secondaryLabel,
                )
                Text("You can turn it off any time in Settings.", style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.Medium)
            }
        },
        confirmButton = { TextButton(onClick = onAccept) { Text("Turn on and call me") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Not now") } },
    )
}
