package com.sevenfive.app

import android.app.Application
import android.content.Context
import android.webkit.CookieManager
import android.webkit.WebStorage
import android.webkit.WebView
import androidx.core.app.NotificationManagerCompat
import com.sevenfive.app.data.Accounts
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.AuthConfigStore
import com.sevenfive.app.data.CardsRepository
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.Http
import com.sevenfive.app.data.PortMaxApi
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
import com.sevenfive.app.notify.Alerts
import com.sevenfive.app.ui.BriefingPlayer
import com.sevenfive.app.util.Diagnostics
import com.sevenfive.app.voice.VoiceAssistant
import com.sevenfive.app.widget.WeekWidget
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

class SevenFiveApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        Diagnostics.install(this)
        container = AppContainer(this)
        // Who was signed in, read off the main thread (the Keystore is slow); the app shows its
        // start screen until then. An account made on the server an older build used is signed
        // out if this build moved the app to another one.
        Thread({
            container.accounts.start(movedFrom = container.servers.movedFrom)
            container.servers.movedHandled()
        }, "accounts-start").start()
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
    val servers = ServerSettings(context, BuildConfig.DEFAULT_HOST, BuildConfig.DEFAULT_SERVER, BuildConfig.PORTAL)
    private val sessions = SessionStore(context)

    /** Who is signed in. The demo's token is public (it is "Try the demo"); accounts use Supabase. */
    val accounts = Accounts(
        sessions, SupabaseAuth(okhttp3.OkHttpClient()), BuildConfig.STUDENT_TOKEN,
        configCache = AuthConfigStore(context),
    )
    private val http = Http(accounts)
    val core = CoreApi(http) { servers.config.value.coreUrl }
    val portmax = PortMaxApi(http) { servers.config.value.portmaxUrl }
    val cards = CardsRepository(core, File(context.filesDir, "cards.json")).also { repo ->
        // After each good poll: phone alarms for the reminders, and the widget. Only when what
        // they show changed, not on every 7-second poll.
        var lastReminders: Any? = null
        var lastWidget: Any? = null
        repo.onCards = { c ->
            val reminders = c.reminders.map { Triple(it.id, it.firesAt, it.channel) }
            if (reminders != lastReminders) {
                Alerts.syncReminders(appContext, c.reminders)
                lastReminders = reminders
            }
            val widget = c.dueThisWeek.map { it.id to it.dueAt } to c.attendance.subjects.map { it.percent }
            if (widget != lastWidget) {
                WeekWidget.refresh(appContext)
                lastWidget = widget
            }
        }
        // The cards are gone: so are the alarms made from them, and the widget empties.
        repo.onReset = {
            lastReminders = null
            lastWidget = null
            Alerts.cancelReminders(appContext)
            WeekWidget.refresh(appContext)
        }
    }
    val portalStore = PortalStore(context)
    val portal = PortalEngine(portmax, cards, portalStore, BuildConfig.COLLEGE)
    val finder = ServerFinder(servers, cards, portmax, mayMove = { accounts.session == null })
    val outbox = OutboxPuller(appContext, core)
    val keepAlive = KeepAliveSettings(context)
    val briefingPlayer = BriefingPlayer(appContext, core)
    val voice = VoiceAssistant(appContext, core, cards, http.client)

    init {
        accounts.core = core
        accounts.onSwitch = { forget() }
        accounts.onLeft = { token, server -> unregister(token, server) }
        accounts.onArrive = { Push.register(appContext) }
    }

    /** Their reminders stop waking this phone: sent with their own [token], as it is, to the
     * [server] they used. Only with Firebase (Push.kt); best effort. */
    private suspend fun unregister(token: String, server: String) {
        val device = Push.currentToken(appContext) ?: return
        try {
            core.removeDeviceAs(token, device, server)
        } catch (e: ApiException) {
            // Their session may be over already; the next sign-in on this phone moves the
            // registration to that student anyway.
        }
    }

    /**
     * Someone else uses the app now: nothing of the last person's may stay on this phone. Their
     * cards (and the copy kept on disk), the alarms set for their reminders and their 8 am digest,
     * the widget, the outbox position, the portal login and everything the portal's WebView
     * stored, shown notifications, the briefing's audio, the materials they opened. Each step on
     * its own: one failing (a WebView being updated) never stops the rest.
     */
    private suspend fun forget() {
        // First: once it returns, no answer of theirs still in flight can set an alarm.
        runCatching { cards.reset() }
        runCatching { Alerts.forget(appContext) }
        outbox.forget()
        portmax.forget()
        runCatching {
            appContext.cacheDir.listFiles { f -> f.name.startsWith("briefing-") }?.forEach { it.delete() }
        }
        // Materials they opened (Opener keeps the downloaded copies here).
        runCatching { File(appContext.cacheDir, "opened").deleteRecursively() }
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
