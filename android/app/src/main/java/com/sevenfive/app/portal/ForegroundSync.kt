package com.sevenfive.app.portal

import android.content.Context
import android.net.Uri
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.ServerSettings
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
import java.time.Duration
import java.time.Instant

/**
 * Keeps attendance fresh while the app is open, from the phone, with the student's own session:
 * a full run every `refresh_minutes` and one light page every `keepalive_minutes`.
 *
 * It loads the portal's login page (which never touches the session) and lets the runner GET
 * the plan's pages from there, so every request has the portal's own Referer. If the session
 * has lapsed the runner meets the login page, and the student is asked to log in again the next
 * time they look — never with a notification. The brief accepts foreground-only for the
 * prototype; a background WebView is the hard part and is left out on purpose.
 */
class ForegroundSync(
    private val context: Context,
    private val engine: PortalEngine,
    private val store: PortalStore,
    private val servers: ServerSettings,
) {
    private var web: WebView? = null
    private val bridge = PortalBridge()
    @Volatile private var pageLoaded: CompletableDeferred<Unit>? = null

    /** Runs until cancelled; tied to the activity being STARTED. */
    suspend fun runWhileStarted() {
        var openedNow = true
        while (true) {
            runCatching { maybeSync(openedNow) }
            openedNow = false
            delay(CHECK_EVERY_MILLIS)
        }
    }

    private suspend fun maybeSync(openedNow: Boolean) {
        val status = store.status.value
        if (!status.everConnected || status.needsLogin || status.busy) return
        val connector = try {
            engine.connector()
        } catch (e: ApiException) {
            return
        }
        val now = Instant.now()
        val sinceFull = status.lastFullSync?.let { Duration.between(it, now).toMinutes() } ?: Long.MAX_VALUE
        val sinceKeep = status.lastKeepAlive?.let { Duration.between(it, now).toMinutes() } ?: Long.MAX_VALUE
        // On open, a full refresh unless one ran in the last few minutes (quick app switches).
        val full = sinceFull >= connector.info.refreshMinutes || (openedNow && sinceFull >= OPEN_REFRESH_MINUTES)
        val keep = sinceKeep >= connector.info.keepaliveMinutes
        if (!full && !keep) return

        val view = web ?: createWebView().also { web = it }
        val loaded = CompletableDeferred<Unit>().also { pageLoaded = it }
        view.loadUrl(engine.loginUrl(servers.config.value.portalUrl, connector))
        withTimeoutOrNull(PAGE_TIMEOUT_MILLIS) { loaded.await() } ?: return
        engine.fetchAndUpload(view, bridge, connector, keepAlive = !full)
        view.loadUrl("about:blank")
    }

    private fun createWebView(): WebView = WebView(context).apply {
        configureForPortal(bridge)
        webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val portal = Uri.parse(servers.config.value.portalUrl)
                return !sameOrigin(request.url, portal)
            }

            override fun onPageFinished(view: WebView, url: String?) {
                if (url != null && url != "about:blank") pageLoaded?.complete(Unit)
            }
        }
    }

    fun destroy() {
        web?.destroy()
        web = null
    }

    private companion object {
        const val CHECK_EVERY_MILLIS = 60_000L
        const val PAGE_TIMEOUT_MILLIS = 20_000L
        const val OPEN_REFRESH_MINUTES = 10L
    }
}
