package com.sevenfive.app.notify

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.sevenfive.app.MainActivity
import com.sevenfive.app.R
import com.sevenfive.app.data.OutboxMessage

/**
 * What 7even5ive may put in the notification shade: the student's own opt-in reminders, the one
 * message a refused or unanswered urgent call becomes (decision 41), and the 8 am digest of
 * what's due when the student turns it on ([Alerts]). Never the briefing, never an attendance
 * warning, never a deadline the student just forwarded themselves.
 */
object Notifications {
    const val CHANNEL_REMINDERS = "reminders"
    const val CHANNEL_CALLS = "calls"
    const val CHANNEL_DIGEST = "digest"

    /** Each kind has its own ids (a reminder's, an outbox message's): the tag keeps them apart. */
    const val TAG_REMINDER = "reminder"
    const val TAG_OUTBOX = "outbox"
    const val TAG_DIGEST = "digest"
    const val TAG_TEST = "test"

    fun createChannels(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_REMINDERS, "Reminders you set", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "Only the reminders you asked for, before something is due."
            },
        )
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_CALLS, "Urgent call updates", NotificationManager.IMPORTANCE_HIGH).apply {
                description = "When an urgent call you asked for couldn't ring or wasn't answered."
            },
        )
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_DIGEST, "Morning digest", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "What's due this week, at 8 am, when you turn it on in Settings."
            },
        )
    }

    /** Android 13+ asks the student first; before that, the app may post unless blocked. */
    fun permitted(context: Context): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) return false
        return NotificationManagerCompat.from(context).areNotificationsEnabled()
    }

    fun needsAsking(context: Context): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED

    private fun prefs(context: Context) = context.getSharedPreferences("notifications", Context.MODE_PRIVATE)

    /** Whether the app has shown Android's permission prompt before. */
    fun asked(context: Context): Boolean = prefs(context).getBoolean("asked", false)

    fun markAsked(context: Context) {
        prefs(context).edit().putBoolean("asked", true).apply()
    }

    /**
     * Whether a request would still show Android's prompt: never asked, or Android says a reason
     * may be shown. Once the student has declined for good, only the system settings can change it.
     */
    fun promptStillShows(activity: android.app.Activity): Boolean =
        !asked(activity) || androidx.core.app.ActivityCompat.shouldShowRequestPermissionRationale(
            activity, Manifest.permission.POST_NOTIFICATIONS,
        )

    /** One outbox message as one notification. A message pulled twice (foreground and
     * background at once) keeps its id, so it shows once; a reminder this phone's own alarm
     * already showed is not shown again ([ReminderLog]). */
    fun show(context: Context, message: OutboxMessage) {
        val reminder = message.reminderId?.takeIf { message.kind == "reminder" }
        if (reminder != null) {
            showReminder(context, reminder, message.title, message.body)
            return
        }
        val channel = if (message.kind == "call") CHANNEL_CALLS else CHANNEL_REMINDERS
        post(context, channel, TAG_OUTBOX, message.id, message.title, message.body)
    }

    /** One reminder, from whichever way reached the phone first: the alarm or the outbox. */
    fun showReminder(context: Context, reminderId: Int, title: String, body: String) {
        if (!permitted(context) || !ReminderLog.claim(context, reminderId)) return
        post(context, CHANNEL_REMINDERS, TAG_REMINDER, reminderId, title, body)
    }

    /** How every 7even5ive notification looks. [lines]: an inbox-style list under [body]. */
    fun post(
        context: Context,
        channel: String,
        tag: String,
        id: Int,
        title: String,
        body: String,
        lines: List<String> = emptyList(),
    ) {
        if (!permitted(context)) return
        val open = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val urgent = channel != CHANNEL_DIGEST
        val builder = NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(BRAND_ORANGE)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(if (urgent) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
            .setOnlyAlertOnce(true)
            .setAutoCancel(true)
            .setContentIntent(open)
        if (urgent) builder.setCategory(NotificationCompat.CATEGORY_REMINDER)
        builder.setStyle(
            if (lines.isEmpty()) NotificationCompat.BigTextStyle().bigText(body)
            else NotificationCompat.InboxStyle().setSummaryText(body).also { style -> lines.forEach(style::addLine) },
        )
        try {
            NotificationManagerCompat.from(context).notify(tag, id, builder.build())
        } catch (e: SecurityException) {
            // The permission was withdrawn between the check and the post: the message stays in
            // the app's Reminders screen.
        }
    }

    private const val BRAND_ORANGE = 0xFFFF8A1F.toInt()
}
