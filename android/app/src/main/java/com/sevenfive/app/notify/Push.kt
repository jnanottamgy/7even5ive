package com.sevenfive.app.notify

import android.content.Context
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.sevenfive.app.BuildConfig
import com.sevenfive.app.SevenFiveApp
import com.sevenfive.app.data.ApiException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Firebase only wakes the phone; it never carries a title, a deadline or any words (fcm.py sends
 * {"type": "sync"}). On a wake-up the phone pulls its outbox over our own API.
 *
 * Optional by build settings: with the four sevenfive.fcm* values in gradle.properties the app
 * starts Firebase itself (no google-services.json, no plugin) and registers its token with
 * POST /api/devices. Without them nothing starts, and the 15-minute pull still delivers
 * everything, only later.
 */
object Push {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val configured: Boolean
        get() = BuildConfig.FCM_APP_ID.isNotBlank() && BuildConfig.FCM_API_KEY.isNotBlank() &&
            BuildConfig.FCM_PROJECT_ID.isNotBlank() && BuildConfig.FCM_SENDER_ID.isNotBlank()

    fun start(context: Context) {
        if (!configured) return
        try {
            if (FirebaseApp.getApps(context).isEmpty()) {
                val options = FirebaseOptions.Builder()
                    .setApplicationId(BuildConfig.FCM_APP_ID)
                    .setApiKey(BuildConfig.FCM_API_KEY)
                    .setProjectId(BuildConfig.FCM_PROJECT_ID)
                    .setGcmSenderId(BuildConfig.FCM_SENDER_ID)
                    .build()
                FirebaseApp.initializeApp(context, options)
            }
            FirebaseMessaging.getInstance().token.addOnSuccessListener { register(context, it) }
        } catch (e: RuntimeException) {
            // A wrong Firebase setting must never take the app down: the pull still works.
        }
    }

    fun register(context: Context, token: String) {
        val app = context.applicationContext as? SevenFiveApp ?: return
        scope.launch {
            try {
                app.container.core.registerDevice(token)
            } catch (e: ApiException) {
                // Registered on the next start or token refresh.
            }
        }
    }
}

/** Declared in the manifest; only ever called once Push.start has set Firebase up. */
class WakeService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        OutboxWorker.now(applicationContext)
    }

    override fun onNewToken(token: String) {
        Push.register(applicationContext, token)
    }
}
