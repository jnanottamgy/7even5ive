package com.sevenfive.app

import android.app.Application
import android.content.Context
import android.webkit.CookieManager
import android.webkit.WebStorage
import android.webkit.WebView
import androidx.core.app.NotificationManagerCompat
import com.sevenfive.app.data.Accounts
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.CardsRepository
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.Http
import com.sevenfive.app.data.PortMaxApi
import com.sevenfive.app.data.Saved
import com.sevenfive.app.data.ServerFinder
import com.sevenfive.app.data.ServerSettings
import com.sevenfive.app.data.SessionStore
import com.sevenfive.app.data.SupabaseAuth
import com.sevenfive.app.notify.Notifications
import com.sevenfive.app.notify.OutboxPuller
import com.sevenfive.app.notify.OutboxWorker
import com.sevenfive.app.notify.Push
import com.sevenfive.app.portal.KeepAliveSettings
import com.sevenfive.app.portal.PortalEngine
import com.sevenfive.app.portal.PortalKeepAliveWorker
import com.sevenfive.app.portal.PortalStore
import com.sevenfive.app.ui.BriefingPlayer
import com.sevenfive.app.util.Diagnostics
import com.sevenfive.app.voice.VoiceAssistant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

class SevenFiveApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        Diagnostics.install(this)
        container = AppContainer(this)
        // Who was signed in, read off the main thread (the Keystore is slow); the app shows its
        // start screen until then.
        Thread({ container.accounts.start() }, "accounts-start").start()
        Notifications.createChannels(this)
        // Every 15 minutes the outbox is pulled even while the app is closed; Firebase, when the
        // build has it, wakes the phone sooner. The portal session is kept alive every 30.
        OutboxWorker.schedule(this)
        PortalKeepAliveWorker.apply(this, container.keepAlive.enabled)
        Push.start(this)
    }
}

/** Hand-wired dependencies: a prototype doesn't need a DI framework. */
class AppContainer(context: Context) {
    val appContext: Context = context.applicationContext
    val servers = ServerSettings(context, BuildConfig.DEFAULT_HOST, BuildConfig.DEFAULT_SERVER)
    private val sessions = SessionStore(context)

    /** Who is signed in. The demo's token is public (it is "Try the demo"); accounts use Supabase. */
    val accounts = Accounts(sessions, SupabaseAuth(okhttp3.OkHttpClient()), BuildConfig.STUDENT_TOKEN)
    private val http = Http(accounts)
    val core = CoreApi(http) { servers.config.value.coreUrl }
    val portmax = PortMaxApi(http) { servers.config.value.portmaxUrl }
    val cards = CardsRepository(core)
    val portalStore = PortalStore(context)
    val portal = PortalEngine(portmax, cards, portalStore, BuildConfig.COLLEGE)
    val finder = ServerFinder(servers, cards, portmax, mayMove = { accounts.session == null })
    val outbox = OutboxPuller(appContext, core)
    val keepAlive = KeepAliveSettings(context)
    val briefingPlayer = BriefingPlayer(appContext, core)
    val voice = VoiceAssistant(appContext, core, cards, http.client)

    init {
        accounts.core = core
        accounts.onSwitch = { leaving, token -> forget(leaving, token) }
        accounts.onArrive = { Push.register(appContext) }
    }

    /**
     * Someone else uses the app now: nothing of the last person's may stay. Their phone
     * registration (so their reminders stop waking this phone; sent with their own [token], as
     * it is), their cards, the outbox position, the portal login and everything the portal's
     * WebView stored, shown notifications, the briefing's audio. Each step on its own: one
     * failing (a WebView being updated) never stops the rest.
     */
    private suspend fun forget(leaving: Saved, token: String?) {
        if (leaving != Saved.Nobody && token != null) {
            Push.currentToken(appContext)?.let { device ->
                try {
                    core.removeDeviceAs(token, device)
                } catch (e: ApiException) {
                    // Their session may be over already; the next sign-in on this phone moves
                    // the registration to that student anyway.
                }
            }
        }
        cards.reset()
        outbox.forget()
        portmax.forget()
        runCatching {
            appContext.cacheDir.listFiles { f -> f.name.startsWith("briefing-") }?.forEach { it.delete() }
        }
        withContext(Dispatchers.Main) {
            runCatching { briefingPlayer.stop() }
            runCatching { voice.stop() }
            runCatching {
                CookieManager.getInstance().removeAllCookies(null)
                CookieManager.getInstance().flush()
            }
            runCatching { WebStorage.getInstance().deleteAllData() }
            runCatching { WebView(appContext).apply { clearCache(true) }.destroy() }
            runCatching { portalStore.forget() }
            runCatching { NotificationManagerCompat.from(appContext).cancelAll() }
        }
    }
}
