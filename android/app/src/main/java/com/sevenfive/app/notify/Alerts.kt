package com.sevenfive.app.notify

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.sevenfive.app.MainActivity
import com.sevenfive.app.R
import com.sevenfive.app.SevenFiveApp
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.Reminder
import com.sevenfive.app.util.Time
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime

/**
 * Phone notifications, on the phone's own clock: the reminders the student asked for, and an
 * optional 8 am digest. Alarms are set from the last cards the app saw, so they fire with the
 * app closed and with no network; the server stays the owner of what a reminder is.
 *
 * Why AlarmManager and not push (FCM): no Google project, no device tokens on the server, and
 * the phone already knows every reminder. Inexact "while idle" alarms: they fire within a few
 * minutes of the time, without the exact-alarm permission.
 */
object Alerts {
    const val CHANNEL_REMINDERS = "reminders"
    const val CHANNEL_DIGEST = "digest"
    private const val PREFS = "alerts"
    private const val KEY_SCHEDULED = "scheduled"
    private const val KEY_DIGEST = "digest_on"
    private const val DIGEST_REQUEST = 7_500_000
    const val DIGEST_HOUR = 8

    fun channels(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = context.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_REMINDERS, "Reminders", NotificationManager.IMPORTANCE_HIGH)
                .apply { description = "The reminders you set on a card" },
        )
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_DIGEST, "Morning digest", NotificationManager.IMPORTANCE_DEFAULT)
                .apply { description = "What's due and your lowest attendance, at 8 am" },
        )
    }

    fun canNotify(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
            PackageManager.PERMISSION_GRANTED

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    // --- reminders ---------------------------------------------------------------------------

    /** Sets an alarm for every future reminder and cancels the ones that are gone. */
    fun syncReminders(context: Context, reminders: List<Reminder>) {
        val am = context.getSystemService(AlarmManager::class.java) ?: return
        val now = System.currentTimeMillis()
        val wanted = reminders.mapNotNull { r ->
            val at = Time.parse(r.firesAt)?.toInstant()?.toEpochMilli() ?: return@mapNotNull null
            if (at <= now) null else r to at
        }
        val previous = prefs(context).getStringSet(KEY_SCHEDULED, emptySet()).orEmpty()
        val keep = wanted.map { it.first.id.toString() }.toSet()
        (previous - keep).forEach { id ->
            id.toIntOrNull()?.let { am.cancel(reminderIntent(context, it, null)) }
        }
        wanted.forEach { (r, at) ->
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, reminderIntent(context, r.id, r))
        }
        prefs(context).edit().putStringSet(KEY_SCHEDULED, keep).apply()
    }

    private fun reminderIntent(context: Context, id: Int, r: Reminder?): PendingIntent {
        val intent = Intent(context, ReminderReceiver::class.java).setAction("com.sevenfive.app.REMIND.$id")
        if (r != null) {
            intent.putExtra("id", id)
            intent.putExtra("title", r.title ?: "Something is due")
            intent.putExtra("subject", r.subject)
            intent.putExtra("due", r.dueAt)
        }
        return PendingIntent.getBroadcast(
            context, id, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    fun showReminder(context: Context, id: Int, title: String, subject: String?, dueAt: String?) {
        val due = Time.parse(dueAt)
        val body = buildString {
            if (!subject.isNullOrBlank()) append(subject)
            if (due != null) {
                if (isNotEmpty()) append(" · ")
                append("due ${Time.dayAndTime(due)} (${Time.until(due)})")
            }
        }
        post(context, CHANNEL_REMINDERS, id, title, body.ifBlank { "You asked to be reminded" }, emptyList())
    }

    // --- digest ------------------------------------------------------------------------------

    fun digestOn(context: Context): Boolean = prefs(context).getBoolean(KEY_DIGEST, false)

    fun setDigest(context: Context, on: Boolean) {
        prefs(context).edit().putBoolean(KEY_DIGEST, on).apply()
        val am = context.getSystemService(AlarmManager::class.java) ?: return
        if (on) scheduleDigest(context) else am.cancel(digestIntent(context))
    }

    /** The next 8:00 on the phone's clock. */
    fun scheduleDigest(context: Context) {
        val am = context.getSystemService(AlarmManager::class.java) ?: return
        val zone = ZoneId.systemDefault()
        var next = ZonedDateTime.of(LocalDate.now(zone), LocalTime.of(DIGEST_HOUR, 0), zone)
        if (!next.isAfter(ZonedDateTime.now(zone))) next = next.plusDays(1)
        am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, next.toInstant().toEpochMilli(), digestIntent(context))
    }

    private fun digestIntent(context: Context): PendingIntent = PendingIntent.getBroadcast(
        context, DIGEST_REQUEST, Intent(context, DigestReceiver::class.java),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    /** "3 due this week · DBMS at 73%", with the items as lines. Null when there are no cards. */
    fun digestOf(cards: Cards): Pair<String, List<String>> {
        val due = cards.dueThisWeek
        val worst = cards.attendance.subjects.minByOrNull { it.percent }
        val head = buildList {
            add(
                when (due.size) {
                    0 -> "Nothing due this week"
                    1 -> "1 thing due this week"
                    else -> "${due.size} things due this week"
                },
            )
            if (worst != null && worst.status != "safe") add("${worst.name} at ${worst.percent.toInt()}%")
        }.joinToString(" · ")
        val lines = due.take(5).map { item ->
            val at = Time.parse(item.dueAt)
            "${item.title ?: "Untitled"}${at?.let { " · ${Time.until(it)}" } ?: ""}"
        }
        return head to lines
    }

    fun showDigest(context: Context, cards: Cards) {
        val (head, lines) = digestOf(cards)
        post(context, CHANNEL_DIGEST, DIGEST_REQUEST, "Good morning", head, lines)
    }

    // --- posting ------------------------------------------------------------------------------

    private fun post(context: Context, channel: String, id: Int, title: String, body: String, lines: List<String>) {
        if (!canNotify(context)) return
        channels(context)
        val open = PendingIntent.getActivity(
            context, 0, Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = NotificationCompat.Builder(context, channel)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(0xFFF27A0C.toInt())
            .setContentTitle(title)
            .setContentText(body)
            .setContentIntent(open)
            .setAutoCancel(true)
            .setPriority(
                if (channel == CHANNEL_REMINDERS) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT,
            )
        if (lines.isNotEmpty()) {
            builder.setStyle(NotificationCompat.InboxStyle().setSummaryText(body).also { s -> lines.forEach(s::addLine) })
        } else {
            builder.setStyle(NotificationCompat.BigTextStyle().bigText(body))
        }
        try {
            NotificationManagerCompat.from(context).notify(id, builder.build())
        } catch (_: SecurityException) {
            // Permission withdrawn between the check and the post: nothing to show.
        }
    }
}

/** A reminder's alarm went off. */
class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val id = intent.getIntExtra("id", -1)
        if (id < 0) return
        Alerts.showReminder(
            context, id, intent.getStringExtra("title") ?: "Something is due",
            intent.getStringExtra("subject"), intent.getStringExtra("due"),
        )
    }
}

/** 8 am: fetch fresh cards if the server answers within a few seconds, else use the last ones. */
class DigestReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!Alerts.digestOn(context)) return
        val pending = goAsync()
        val repo = (context.applicationContext as SevenFiveApp).container.cards
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            try {
                withTimeoutOrNull(8_000) { repo.refresh(wait = true) }
                repo.cached()?.let { Alerts.showDigest(context, it) }
                Alerts.scheduleDigest(context)
            } finally {
                pending.finish()
            }
        }
    }
}

/** Alarms don't survive a restart: set them again from the last cards. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED && intent.action != Intent.ACTION_MY_PACKAGE_REPLACED) return
        val repo = (context.applicationContext as SevenFiveApp).container.cards
        repo.cached()?.let { Alerts.syncReminders(context, it.reminders) }
        if (Alerts.digestOn(context)) Alerts.scheduleDigest(context)
    }
}
