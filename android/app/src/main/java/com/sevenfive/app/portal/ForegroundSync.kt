package com.sevenfive.app.portal

import android.content.Context
import android.net.Uri
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
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
        if (!status.everConnected || status.needsLogin || status.busy || store.screenOpen) return
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

        // A fresh WebView per sync, destroyed after: nothing lingers in memory between runs.
        val view = createWebView().also { web = it }
        try {
            val loaded = CompletableDeferred<Unit>().also { pageLoaded = it }
            view.loadUrl(engine.loginUrl(servers.config.value.portalUrl, connector))
            withTimeoutOrNull(PAGE_TIMEOUT_MILLIS) { loaded.await() } ?: return
            if (store.screenOpen) return
            engine.fetchAndUpload(view, bridge, connector, keepAlive = !full)
        } finally {
            destroy()
        }
    }

    private fun createWebView(): WebView = WebView(context).apply {
        configureForPortal(bridge)
        // The same iPhone path as the login: if the sync's page loads went out with the WebView's
        // Android headers on the session the student logged in as an iPhone, the portal would see
        // two devices on one session and log it out.
        val ios = sendPortalFormsAsIphone(Uri.parse(servers.config.value.portalUrl).host.orEmpty())
        PortalLog.add("--- background sync WebView: ${if (ios != null) "iPhone path" else "plain WebView"}")
        webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                ios?.interceptGet(request)

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val portal = Uri.parse(servers.config.value.portalUrl)
                return !sameOrigin(request.url, portal)
            }

            override fun onPageFinished(view: WebView, url: String?) {
                if (url != null && url != "about:blank") pageLoaded?.complete(Unit)
            }

            // The page's renderer died (memory, a WebView bug). Without this, Android kills the
            // whole app with it. Drop this sync; the next one starts a new WebView.
            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                pageLoaded?.completeExceptionally(IllegalStateException("portal page renderer gone"))
                if (web === view) web = null
                view.destroy()
                return true
            }
        }
    }

    fun destroy() {
        val view = web ?: return
        web = null
        view.stopLoading()
        view.destroy()
    }

    private companion object {
        const val CHECK_EVERY_MILLIS = 60_000L
        const val PAGE_TIMEOUT_MILLIS = 20_000L
        const val OPEN_REFRESH_MINUTES = 10L
    }
}
