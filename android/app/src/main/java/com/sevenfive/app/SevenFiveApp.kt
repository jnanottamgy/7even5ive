package com.sevenfive.app

import android.app.Application
import android.content.Context
import com.sevenfive.app.data.CardsRepository
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.Http
import com.sevenfive.app.data.PortMaxApi
import com.sevenfive.app.data.ServerFinder
import com.sevenfive.app.data.ServerSettings
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

class SevenFiveApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        Diagnostics.install(this)
        container = AppContainer(this)
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
    private val http = Http(BuildConfig.STUDENT_TOKEN)
    val core = CoreApi(http) { servers.config.value.coreUrl }
    val portmax = PortMaxApi(http) { servers.config.value.portmaxUrl }
    val cards = CardsRepository(core)
    val portalStore = PortalStore(context)
    val portal = PortalEngine(portmax, cards, portalStore, BuildConfig.COLLEGE)
    val finder = ServerFinder(servers, cards, portmax)
    val outbox = OutboxPuller(appContext, core)
    val keepAlive = KeepAliveSettings(context)
    val briefingPlayer = BriefingPlayer(appContext, core)
    val voice = VoiceAssistant(appContext, core, cards, http.client)
}
