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
 * What 7even5ive may put in the notification shade: the student's own opt-in reminders, and the
 * one message a refused or unanswered urgent call becomes (decision 41). Never the briefing,
 * never an attendance warning, never a deadline the student just forwarded themselves.
 */
object Notifications {
    const val CHANNEL_REMINDERS = "reminders"
    const val CHANNEL_CALLS = "calls"

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

    /** One outbox message as one notification. The outbox id is the notification id, so a
     * message pulled twice (foreground and background at once) shows once. */
    fun show(context: Context, message: OutboxMessage) {
        if (!permitted(context)) return
        val open = PendingIntent.getActivity(
            context,
            message.id,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val channel = if (message.kind == "call") CHANNEL_CALLS else CHANNEL_REMINDERS
        val notification = NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(message.title)
            .setContentText(message.body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message.body))
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(open)
            .build()
        try {
            NotificationManagerCompat.from(context).notify(message.id, notification)
        } catch (e: SecurityException) {
            // The permission was withdrawn between the check and the post: the message stays in
            // the app's Reminders screen.
        }
    }
}
