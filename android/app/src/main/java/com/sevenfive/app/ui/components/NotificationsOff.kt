package com.sevenfive.app.ui.components

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.LocalActivity
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.NotificationsOff
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import com.sevenfive.app.notify.Notifications
import com.sevenfive.app.ui.theme.LocalAppColors

/** Whether the app may post notifications, read again whenever the screen comes back to the
 * front (after Android's prompt, or the system settings). */
@Composable
fun rememberNotificationsPermitted(): Boolean {
    val context = LocalContext.current
    var permitted by remember { mutableStateOf(Notifications.permitted(context)) }
    LifecycleResumeEffect(Unit) {
        permitted = Notifications.permitted(context)
        onPauseOrDispose { }
    }
    return permitted
}

/**
 * Turns notifications on the only way still open: Android's prompt while it would still show
 * ([ask]), else this app's notification settings (after the student declined for good, or on
 * Android 12 and older, where notifications are switched off in settings).
 */
fun turnOnNotifications(activity: Activity?, context: Context, ask: () -> Unit) {
    if (Notifications.needsAsking(context) && activity != null && Notifications.promptStillShows(activity)) {
        ask()
        return
    }
    val settings = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
        .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    try {
        context.startActivity(settings)
    } catch (e: ActivityNotFoundException) {
        // A phone without that page: the app's own page has the switch too.
        runCatching {
            context.startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }
    }
}

/** Reminders: says plainly that reminders can't reach the student, with the way to fix it. */
@Composable
fun NotificationsOffCard(onAsk: () -> Unit, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val activity = LocalActivity.current
    val red = MaterialTheme.colorScheme.error
    AppCard(modifier) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconTile(Icons.Outlined.NotificationsOff, red)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text("Notifications are off", style = MaterialTheme.typography.titleMedium, color = red)
                Text(
                    "Your reminders can't reach you while the app is closed.",
                    style = MaterialTheme.typography.bodySmall,
                    color = LocalAppColors.current.secondaryLabel,
                )
            }
            Spacer(Modifier.width(8.dp))
            PrimaryPill("Turn on", onClick = { turnOnNotifications(activity, context, onAsk) })
        }
    }
}
