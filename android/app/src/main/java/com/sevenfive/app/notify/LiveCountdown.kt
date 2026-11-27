package com.sevenfive.app.notify

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.sevenfive.app.MainActivity
import com.sevenfive.app.R
import com.sevenfive.app.data.Cards
import com.sevenfive.app.util.Time
import java.time.Duration
import java.time.Instant

/**
 * The last-day countdown: when a deadline or exam is less than 24 hours away, one quiet, ongoing
 * notification shows it on the lock screen with a live countdown (Android's own chronometer, so
 * it ticks without the app). It goes away at the deadline, when the item is marked done, or when
 * the student turns it off in Settings. Silent: it never rings or buzzes.
 */
object LiveCountdown {
    const val CHANNEL = "countdown"
    private const val TAG = "countdown"
    private const val ID = 75
    private const val PREFS = "live_countdown"
    private val WINDOW: Duration = Duration.ofHours(24)

    fun createChannel(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "Last-day countdown", NotificationManager.IMPORTANCE_LOW).apply {
                description = "A silent countdown on the lock screen when something is due within 24 hours."
                setShowBadge(false)
                lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
            },
        )
    }

    fun enabled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean("on", true)

    fun setEnabled(context: Context, on: Boolean, cards: Cards?) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean("on", on).apply()
        update(context, cards)
    }

    /** What would show now: the soonest deadline or exam due within 24 h, or nothing. */
    fun next(cards: Cards?, now: Instant = Instant.now()): Pair<com.sevenfive.app.data.Item, Instant>? =
        cards?.dueThisWeek.orEmpty()
            .filter { it.kind == "deadline" || it.kind == "exam" }
            .mapNotNull { item -> Time.parse(item.dueAt)?.toInstant()?.let { item to it } }
            .filter { (_, due) -> due.isAfter(now) && due.isBefore(now.plus(WINDOW)) }
            .minByOrNull { it.second }

    /** Shows, moves or removes the countdown to match [cards]. */
    fun update(context: Context, cards: Cards?) {
        val manager = NotificationManagerCompat.from(context)
        val shown = next(cards)
        if (shown == null || !enabled(context) || !Notifications.permitted(context)) {
            manager.cancel(TAG, ID)
            return
        }
        val (item, due) = shown
        val open = PendingIntent.getActivity(
            context,
            ID,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val at = Time.parse(item.dueAt)
        val what = if (item.kind == "exam") "Exam" else "Due"
        val body = listOfNotNull(at?.let { "$what ${Time.dayAndTime(it)}" }, item.subject).joinToString(" · ")
        val left = Duration.between(Instant.now(), due).toMillis()
        val notification = NotificationCompat.Builder(context, CHANNEL)
            .setSmallIcon(R.drawable.ic_notification)
            .setColor(0xFFFF8A1F.toInt())
            .setContentTitle(item.title ?: "Due soon")
            .setContentText(body)
            .setUsesChronometer(true)
            .setChronometerCountDown(true)
            .setWhen(due.toEpochMilli())
            .setShowWhen(true)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setTimeoutAfter(left.coerceAtLeast(1_000L))
            .setContentIntent(open)
            .build()
        try {
            manager.notify(TAG, ID, notification)
        } catch (e: SecurityException) {
            // Notifications were turned off in between: nothing to show.
        }
    }

    fun cancel(context: Context) = NotificationManagerCompat.from(context).cancel(TAG, ID)
}
