package com.sevenfive.app

import android.app.Application
import android.content.Context
import com.sevenfive.app.data.CardsRepository
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.Http
import com.sevenfive.app.data.PortMaxApi
import com.sevenfive.app.data.ServerFinder
import com.sevenfive.app.data.ServerSettings
import com.sevenfive.app.portal.PortalEngine
import com.sevenfive.app.portal.PortalStore
import com.sevenfive.app.util.Diagnostics

class SevenFiveApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        Diagnostics.install(this)
        container = AppContainer(this)
    }
}

/** Hand-wired dependencies: a prototype doesn't need a DI framework. */
class AppContainer(context: Context) {
    val appContext: Context = context.applicationContext
    val servers = ServerSettings(context, BuildConfig.DEFAULT_HOST)
    private val http = Http(BuildConfig.STUDENT_TOKEN)
    val core = CoreApi(http) { servers.config.value.coreUrl }
    val portmax = PortMaxApi(http) { servers.config.value.portmaxUrl }
    val cards = CardsRepository(core)
    val portalStore = PortalStore(context)
    val portal = PortalEngine(portmax, cards, portalStore, BuildConfig.COLLEGE)
    val finder = ServerFinder(servers, cards, portmax)
}
