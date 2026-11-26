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
import com.sevenfive.app.notify.Alerts
import com.sevenfive.app.util.Diagnostics
import com.sevenfive.app.widget.WeekWidget
import java.io.File

class SevenFiveApp : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        Diagnostics.install(this)
        container = AppContainer(this)
        Alerts.channels(this)
    }
}

/** Hand-wired dependencies: a prototype doesn't need a DI framework. */
class AppContainer(context: Context) {
    val appContext: Context = context.applicationContext
    val servers = ServerSettings(context, BuildConfig.DEFAULT_HOST, BuildConfig.DEFAULT_SERVER)
    private val http = Http(BuildConfig.STUDENT_TOKEN)
    val core = CoreApi(http) { servers.config.value.coreUrl }
    val portmax = PortMaxApi(http) { servers.config.value.portmaxUrl }
    val cards = CardsRepository(core, File(context.filesDir, "cards.json")).also { repo ->
        // After each good poll: phone alarms for the reminders, and the widget. Only when what
        // they show changed, not on every 7-second poll.
        var lastReminders: Any? = null
        var lastWidget: Any? = null
        repo.onCards = { c ->
            val reminders = c.reminders.map { it.id to it.firesAt }
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
    }
    val portalStore = PortalStore(context)
    val portal = PortalEngine(portmax, cards, portalStore, BuildConfig.COLLEGE)
    val finder = ServerFinder(servers, cards, portmax)
}
