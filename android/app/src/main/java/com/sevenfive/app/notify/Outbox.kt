package com.sevenfive.app.notify

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.sevenfive.app.SevenFiveApp
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.OutboxMessage
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.util.concurrent.TimeUnit

/**
 * The phone's side of the outbox (decision P3): every message for the student is a row on the
 * server, and the phone pulls what is new. In the foreground every 20 seconds, in the background
 * every 15 minutes (WorkManager's shortest period), and at once when Firebase wakes the phone
 * (Push.kt) -- a push carries no content, only "go and look".
 */
class OutboxPuller(private val context: Context, private val core: CoreApi) {
    private val prefs = context.getSharedPreferences("outbox", Context.MODE_PRIVATE)
    private val lock = Mutex()

    /** Pulls and shows what is new. Returns what was shown. Never throws for a bad network. */
    suspend fun pull(): List<OutboxMessage> = lock.withLock {
        val last = prefs.getInt(LAST_ID, FIRST_RUN)
        try {
            if (last == FIRST_RUN) {
                // A phone opening for the first time learns where the outbox stands and is not
                // handed everything sent before it was installed.
                val now = core.notifications(after = -1)
                prefs.edit().putInt(LAST_ID, now.latestId).apply()
                return emptyList()
            }
            var outbox = core.notifications(after = last)
            if (outbox.latestId < last) {
                // The server started over (a demo reset, a fresh serverless instance): its ids did
                // too, so everything it holds now is new to this phone.
                outbox = core.notifications(after = 0)
            }
            outbox.notifications.forEach { Notifications.show(context, it) }
            prefs.edit().putInt(LAST_ID, outbox.latestId).apply()
            outbox.notifications
        } catch (e: ApiException) {
            emptyList()
        }
    }

    /** Runs until cancelled; the activity ties it to being on screen. */
    suspend fun pollWhileStarted() {
        while (true) {
            pull()
            delay(FOREGROUND_MILLIS)
        }
    }

    fun forget() {
        prefs.edit().remove(LAST_ID).apply()
    }

    companion object {
        private const val LAST_ID = "last_id"
        private const val FIRST_RUN = Int.MIN_VALUE
        const val FOREGROUND_MILLIS = 20_000L
    }
}

/** The background pull. Every 15 minutes, and once at once when Firebase wakes the phone. */
class OutboxWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val app = applicationContext as? SevenFiveApp ?: return Result.success()
        app.container.outbox.pull()
        return Result.success()
    }

    companion object {
        private const val PERIODIC = "outbox-pull"
        private const val NOW = "outbox-pull-now"
        private val online = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<OutboxWorker>(15, TimeUnit.MINUTES)
                .setConstraints(online)
                .build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, request)
        }

        /** Firebase said there is something: pull now (expedited, within Android's quota). */
        fun now(context: Context) {
            val request = OneTimeWorkRequestBuilder<OutboxWorker>()
                .setConstraints(online)
                .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
                .build()
            WorkManager.getInstance(context).enqueueUniqueWork(NOW, ExistingWorkPolicy.REPLACE, request)
        }
    }
}
