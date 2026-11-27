package com.sevenfive.app.notify

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
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
 * Phone alarms, on the phone's own clock: the reminders the student asked for, and an optional
 * 8 am digest of what's due. Alarms are set from the last cards the app saw, so a reminder rings
 * on time with the app closed and with no network. The server stays the owner of what a reminder
 * is: its outbox delivers the same reminder too, and the ones this phone never heard of, and
 * [ReminderLog] lets only the first of the two show.
 *
 * Inexact "while idle" alarms fire within a few minutes of the time without the exact-alarm
 * permission. An urgent-call reminder gets no alarm: the server rings for it, and a call that
 * can't ring becomes one outbox message.
 */
object Alerts {
    private const val PREFS = "alerts"
    private const val KEY_SCHEDULED = "scheduled"
    private const val KEY_DIGEST = "digest_on"
    private const val DIGEST_REQUEST = 7_500_000
    const val DIGEST_HOUR = 8

    private fun prefs(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    // --- reminders ---------------------------------------------------------------------------

    /** Sets an alarm for every future reminder and cancels the ones that are gone. */
    @Synchronized
    fun syncReminders(context: Context, reminders: List<Reminder>) {
        val am = context.getSystemService(AlarmManager::class.java) ?: return
        val now = System.currentTimeMillis()
        val wanted = reminders.filterNot { it.isCall }.mapNotNull { r ->
            val at = Time.parse(r.firesAt)?.toInstant()?.toEpochMilli() ?: return@mapNotNull null
            if (at <= now) null else r to at
        }
        val keep = wanted.map { it.first.id.toString() }.toSet()
        (scheduled(context) - keep).forEach { id -> id.toIntOrNull()?.let { cancelAlarm(context, am, it) } }
        wanted.forEach { (r, at) ->
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, reminderIntent(context, r.id, r))
        }
        prefs(context).edit().putStringSet(KEY_SCHEDULED, keep).apply()
    }

    /** No reminder alarm of this phone's rings any more (the cards they came from are gone). */
    @Synchronized
    fun cancelReminders(context: Context) {
        val am = context.getSystemService(AlarmManager::class.java)
        if (am != null) scheduled(context).forEach { id -> id.toIntOrNull()?.let { cancelAlarm(context, am, it) } }
        prefs(context).edit().remove(KEY_SCHEDULED).apply()
    }

    private fun scheduled(context: Context): Set<String> =
        prefs(context).getStringSet(KEY_SCHEDULED, emptySet()).orEmpty()

    private fun cancelAlarm(context: Context, am: AlarmManager, id: Int) {
        val existing = PendingIntent.getBroadcast(
            context, id, reminderAction(context, id), PendingIntent.FLAG_NO_CREATE or PendingIntent.FLAG_IMMUTABLE,
        ) ?: return
        am.cancel(existing)
        existing.cancel()
    }

    private fun reminderAction(context: Context, id: Int) =
        Intent(context, ReminderReceiver::class.java).setAction("com.sevenfive.app.REMIND.$id")

    private fun reminderIntent(context: Context, id: Int, r: Reminder): PendingIntent {
        val intent = reminderAction(context, id)
            .putExtra("id", id)
            .putExtra("title", r.title ?: "Something is due")
            .putExtra("subject", r.subject)
            .putExtra("due", r.dueAt)
        return PendingIntent.getBroadcast(
            context, id, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
    }

    /** The alarm went off: shown, unless the outbox already brought the same reminder. */
    fun showReminder(context: Context, id: Int, title: String, subject: String?, dueAt: String?) {
        Notifications.showReminder(context, id, title, reminderBody(subject, dueAt))
    }

    /** Settings' "Try a reminder notification": looks like a reminder, never counts as one. */
    fun showTest(context: Context, title: String, subject: String?, dueAt: String?) {
        Notifications.post(context, Notifications.CHANNEL_REMINDERS, Notifications.TAG_TEST, 1, title, reminderBody(subject, dueAt))
    }

    private fun reminderBody(subject: String?, dueAt: String?): String {
        val due = Time.parse(dueAt)
        return buildString {
            if (!subject.isNullOrBlank()) append(subject)
            if (due != null) {
                if (isNotEmpty()) append(" · ")
                append("due ${Time.dayAndTime(due)} (${Time.until(due)})")
            }
        }.ifBlank { "You asked to be reminded" }
    }

    // --- digest ------------------------------------------------------------------------------

    fun digestOn(context: Context): Boolean = prefs(context).getBoolean(KEY_DIGEST, false)

    fun setDigest(context: Context, on: Boolean) {
        prefs(context).edit().putBoolean(KEY_DIGEST, on).apply()
        if (on) {
            scheduleDigest(context)
        } else {
            context.getSystemService(AlarmManager::class.java)?.cancel(digestIntent(context))
        }
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

    /** "3 things due this week", with the first five as lines. Attendance stays in the app
     * (decision 41): a notification never carries an attendance warning. */
    fun digestOf(cards: Cards): Pair<String, List<String>> {
        val due = cards.dueThisWeek
        val head = when (due.size) {
            0 -> "Nothing due this week"
            1 -> "1 thing due this week"
            else -> "${due.size} things due this week"
        }
        val lines = due.take(5).map { item ->
            val at = Time.parse(item.dueAt)
            "${item.title ?: "Untitled"}${at?.let { " · ${Time.until(it)}" } ?: ""}"
        }
        return head to lines
    }

    fun showDigest(context: Context, cards: Cards) {
        val (head, lines) = digestOf(cards)
        Notifications.post(context, Notifications.CHANNEL_DIGEST, Notifications.TAG_DIGEST, DIGEST_REQUEST, "Good morning", head, lines)
    }

    /** Someone else uses the app now: the last person's alarms, digest and shown reminders go. */
    fun forget(context: Context) {
        cancelReminders(context)
        setDigest(context, false)
        ReminderLog.forget(context)
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
