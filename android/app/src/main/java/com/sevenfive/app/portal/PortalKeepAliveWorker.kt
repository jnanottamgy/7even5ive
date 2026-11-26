package com.sevenfive.app.portal

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.sevenfive.app.SevenFiveApp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.TimeUnit

/** Whether the activity is on screen; the foreground sync owns the portal then. */
object AppVisibility {
    @Volatile var foreground: Boolean = false
}

/**
 * The student's switch for the background keep-alive (on by default, decision P7). Its own file:
 * logging out of the portal clears the "portal" file, and must not switch this back on.
 */
class KeepAliveSettings(context: Context) {
    private val prefs = context.getSharedPreferences("portal_keepalive", Context.MODE_PRIVATE)

    var enabled: Boolean
        get() = prefs.getBoolean(KEY, true)
        set(value) = prefs.edit().putBoolean(KEY, value).apply()

    private companion object {
        const val KEY = "background_keepalive"
    }
}

/**
 * Keeps the portal session alive while the app is closed (plan 8.6): every 30 minutes, the same
 * pass the foreground sync runs -- one light page from the student's own session, or the whole
 * plan when it is due -- in a WebView made for it and destroyed after. MSRIT's session was
 * measured to die after 45-61 idle minutes, so 30 keeps it.
 *
 * Nothing happens when the student never logged in, the session has already lapsed (they log in
 * again next time they open the app, never prompted by a notification), the app is on screen,
 * or the switch in Settings is off. No notification either way.
 */
class PortalKeepAliveWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val app = applicationContext as? SevenFiveApp ?: return Result.success()
        val c = app.container
        if (!c.keepAlive.enabled || AppVisibility.foreground) return Result.success()
        val status = c.portalStore.status.value
        if (!status.everConnected || status.needsLogin) return Result.success()
        withContext(Dispatchers.Main) {
            val sync = ForegroundSync(applicationContext, c.portal, c.portalStore, c.servers)
            try {
                withTimeoutOrNull(TIMEOUT_MILLIS) { runCatching { sync.syncOnce(openedNow = false) } }
            } finally {
                sync.destroy()
            }
        }
        return Result.success()
    }

    companion object {
        private const val NAME = "portal-keepalive"
        private const val TIMEOUT_MILLIS = 3 * 60_000L

        /** Schedules or cancels the 30-minute keep-alive to match the switch. */
        fun apply(context: Context, enabled: Boolean) {
            val work = WorkManager.getInstance(context)
            if (!enabled) {
                work.cancelUniqueWork(NAME)
                return
            }
            val request = PeriodicWorkRequestBuilder<PortalKeepAliveWorker>(30, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            work.enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
