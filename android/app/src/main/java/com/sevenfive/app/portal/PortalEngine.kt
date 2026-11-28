package com.sevenfive.app.portal

import android.annotation.SuppressLint
import android.net.Uri
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebSettings
import android.webkit.WebView
import androidx.webkit.WebSettingsCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.CardsRepository
import com.sevenfive.app.data.Connector
import com.sevenfive.app.data.PagesResult
import com.sevenfive.app.data.PortMaxApi
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import java.util.UUID
import kotlin.coroutines.resume

/** A failure reported by the runner itself, with PortMax's code (`session_expired`, ...). */
class RunnerFailure(val code: String, val detail: String) : Exception(detail)

sealed interface SyncOutcome {
    data class Saved(val result: PagesResult) : SyncOutcome
    /** The portal showed its login page: the student logs in again, in the app. */
    data object SessionExpired : SyncOutcome
    data class Failed(val message: String) : SyncOutcome
}

/**
 * The runner's way back to Kotlin. `run()` returns a Promise, which evaluateJavascript can't
 * await, so the script posts the result here. A fresh nonce per run means a stray or replayed
 * call from the page can't complete a run it didn't start.
 */
class PortalBridge {
    @Volatile private var expected: String? = null
    @Volatile private var result: CompletableDeferred<String>? = null

    fun arm(): Pair<String, CompletableDeferred<String>> {
        val nonce = UUID.randomUUID().toString()
        val deferred = CompletableDeferred<String>()
        result?.cancel()
        expected = nonce
        result = deferred
        return nonce to deferred
    }

    @JavascriptInterface
    fun pages(nonce: String, json: String) {
        if (nonce != expected) return
        expected = null
        result?.complete(json)
    }

    @JavascriptInterface
    fun error(nonce: String, code: String, detail: String) {
        if (nonce != expected) return
        expected = null
        result?.completeExceptionally(RunnerFailure(code, detail))
    }

    companion object {
        const val NAME = "SevenFiveBridge"
    }
}

/**
 * Injected before the portal's own scripts run. Contineo's `cs_env` detector flags an Android
 * WebView through `navigator.userAgentData.brands` ("Android WebView") and submits it as a hidden
 * field at login; an iOS WebView has no `userAgentData` at all and is accepted. So we make Android
 * match iOS by removing `userAgentData`. It is redefined on `Navigator.prototype`, not on the
 * `navigator` instance, so the page's own anti-tamper check — `getOwnPropertyDescriptor(navigator,
 * "userAgentData")` — still sees no own property. Runs at document start in every frame.
 */
private const val HIDE_WEBVIEW_JS =
    "(function(){try{Object.defineProperty(Navigator.prototype,'userAgentData'," +
        "{get:function(){return undefined;},configurable:true});}catch(e){}})();"

/** A plain Chrome-on-Android User-Agent, with no "wv" token for the portal to sniff. */
const val PORTAL_USER_AGENT =
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) " +
        "Chrome/158.0.0.0 Mobile Safari/537.36"

/** Safari on an iPhone (iOS 26 Safari freezes the OS at 18_6 in its UA, so this is current). */
const val IOS_USER_AGENT =
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 " +
        "(KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1"

/**
 * What the portal sees the WebView as. IPHONE copies an iOS WebView, which the portal accepts:
 * Safari's UA plus the navigator fields a script checks next (platform, vendor, touch points), so
 * the UA and the page's JavaScript tell the same story on every page, not just the login.
 */
enum class PortalIdentity(val label: String) { IPHONE("iPhone"), ANDROID_CHROME("Android Chrome") }

/** Process-wide, so the login screen uses whatever passed on the test screen. */
object PortalSettings {
    @Volatile var identity: PortalIdentity = PortalIdentity.IPHONE
}

/**
 * The iPhone extras, at document start in every frame. Getters go on Navigator.prototype (not the
 * instance) for the same anti-tamper reason as HIDE_WEBVIEW_JS. Safari has no window.chrome.
 */
private const val IOS_NAVIGATOR_JS =
    "(function(){try{var P=Navigator.prototype;" +
        "function d(k,v){Object.defineProperty(P,k,{get:function(){return v;},configurable:true});}" +
        "d('platform','iPhone');d('vendor','Apple Computer, Inc.');d('maxTouchPoints',5);" +
        "try{delete window.chrome;}catch(e){}}catch(e){}})();"

/**
 * The WebView sends its X-Requested-With header (this app's package name, a WebView fingerprint)
 * to no site. Lint calls the feature flag library-internal: androidx.webkit 1.12 still marks it
 * so. The call only runs where the runtime check says the WebView has the feature, and webkit is
 * pinned, so a change can only come with a deliberate upgrade (which runs lint again).
 */
@SuppressLint("RestrictedApi")
private fun WebSettings.sendRequestedWithToNoOne() {
    if (WebViewFeature.isFeatureSupported(WebViewFeature.REQUESTED_WITH_HEADER_ALLOW_LIST)) {
        WebSettingsCompat.setRequestedWithHeaderOriginAllowList(this, emptySet())
    }
}

/**
 * Everything that gets an Android WebView past a Contineo-style "no third-party apps" wall, shared
 * by the portal login and the portal test:
 *  - a plain Chrome User-Agent (the portal refuses the WebView "wv" token),
 *  - third-party cookies on (the invisible Google reCAPTCHA sets cookies on google.com),
 *  - no X-Requested-With header (it carries the app's package — a WebView tell), and
 *  - the `userAgentData` removal injected before the page's own scripts run (see HIDE_WEBVIEW_JS).
 * Adds no JavaScript bridge, so it is safe for the test screen, which must touch nothing on the page.
 */
fun WebView.hardenPortalWebView(identity: PortalIdentity = PortalSettings.identity) {
    val iphone = identity == PortalIdentity.IPHONE
    settings.userAgentString = if (iphone) IOS_USER_AGENT else PORTAL_USER_AGENT
    // Pages that pop a second window (a "next step" opened with target=_blank) stay in this view.
    settings.javaScriptCanOpenWindowsAutomatically = true
    settings.setSupportMultipleWindows(false)
    CookieManager.getInstance().setAcceptCookie(true)
    CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
    settings.sendRequestedWithToNoOne()
    // Needs a recent System WebView; where unavailable the UA fix alone still clears the UA check.
    if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
        WebViewCompat.addDocumentStartJavaScript(this, HIDE_WEBVIEW_JS, setOf("*"))
        if (iphone) WebViewCompat.addDocumentStartJavaScript(this, IOS_NAVIGATOR_JS, setOf("*"))
    }
}

/**
 * The portal's own page, unchanged: JavaScript and cookies on, hardened against WebView sniffing,
 * no file access. We never fill in or submit the login form.
 */
@SuppressLint("SetJavaScriptEnabled", "JavascriptInterface")
fun WebView.configureForPortal(bridge: PortalBridge) {
    settings.javaScriptEnabled = true
    settings.domStorageEnabled = true
    settings.allowFileAccess = false
    settings.allowContentAccess = false
    hardenPortalWebView()
    addJavascriptInterface(bridge, PortalBridge.NAME)
}

suspend fun WebView.eval(script: String): String = suspendCancellableCoroutine { cont ->
    evaluateJavascript(script) { value -> if (cont.isActive) cont.resume(value ?: "null") }
}

fun sameOrigin(a: Uri, b: Uri): Boolean =
    a.scheme.equals(b.scheme, ignoreCase = true) &&
        a.host.equals(b.host, ignoreCase = true) &&
        effectivePort(a) == effectivePort(b)

private fun effectivePort(u: Uri): Int =
    if (u.port != -1) u.port else if (u.scheme.equals("https", true)) 443 else 80

/** Runs a connector's fetch plan in a WebView that is on the portal, and uploads the pages. */
class PortalEngine(
    private val portmax: PortMaxApi,
    private val cards: CardsRepository,
    private val store: PortalStore,
    val college: String,
) {
    suspend fun connector(): Connector = portmax.connector(college)

    fun loginUrl(portalBase: String, connector: Connector): String =
        portalBase.trimEnd('/') + "/" + connector.info.loginPath.trimStart('/')

    /** Defines PortMaxRunner in the current page (each page load starts clean). */
    suspend fun inject(web: WebView) {
        web.eval(portmax.runnerJs() + "\n;true;")
    }

    suspend fun isLoggedIn(web: WebView, connector: Connector): Boolean {
        inject(web)
        val markers = connector.info.markers.toString()
        val answer = web.eval(
            "(function(){try{return window.PortMaxRunner.isLoggedIn($markers);}catch(e){return false;}})()"
        )
        return answer == "true"
    }

    /**
     * One full run (every page of the plan) or one keep-alive (one light page), then upload.
     * Every request is a GET from the portal's own page with the student's own session.
     */
    suspend fun fetchAndUpload(
        web: WebView,
        bridge: PortalBridge,
        connector: Connector,
        keepAlive: Boolean,
    ): SyncOutcome {
        if (store.status.value.busy) return SyncOutcome.Failed("A portal refresh is already running")
        store.setBusy(true)
        try {
            inject(web)
            val (nonce, deferred) = bridge.arm()
            web.eval(startScript(connector.raw, keepAlive, nonce))
            val pagesJson = withTimeoutOrNull(RUN_TIMEOUT_MILLIS) { deferred.await() }
                ?: return fail("The portal took too long to answer")
            val result = portmax.upload(college, pagesJson)
            store.recordSuccess(full = !keepAlive)
            cards.refresh()
            return SyncOutcome.Saved(result)
        } catch (e: RunnerFailure) {
            if (e.code == "session_expired") return expired()
            return fail(e.detail)
        } catch (e: ApiException) {
            if (e.status == 409 || e.code == "session_expired") return expired()
            return fail(e.detail)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            // A malformed answer from the page or the server is a failed refresh, not a crash.
            return fail("Refresh failed: ${e.javaClass.simpleName}")
        } finally {
            store.setBusy(false)
        }
    }

    private fun expired(): SyncOutcome {
        store.markNeedsLogin()
        return SyncOutcome.SessionExpired
    }

    private fun fail(message: String): SyncOutcome {
        store.recordError(message)
        return SyncOutcome.Failed(message)
    }

    companion object {
        /** A full plan is a handful of pages paced 400 ms apart; two minutes is generous. */
        const val RUN_TIMEOUT_MILLIS = 120_000L

        /** The settings JSON goes to the runner unchanged, as the brief asks. */
        fun startScript(settingsJson: String, keepAlive: Boolean, nonce: String): String {
            val call = if (keepAlive) "keepAlive" else "run"
            return """
                (function(){
                  var b = window.${PortalBridge.NAME};
                  try {
                    var s = $settingsJson;
                    window.PortMaxRunner.$call(s).then(
                      function(pages){ b.pages('$nonce', JSON.stringify(pages)); },
                      function(e){ b.error('$nonce', String((e && e.code) || 'runner_error'),
                                           String((e && (e.detail || e.message)) || e)); });
                  } catch (e) {
                    b.error('$nonce', String((e && e.code) || 'runner_error'),
                            String((e && (e.detail || e.message)) || e));
                  }
                  return 'started';
                })();
            """.trimIndent()
        }
    }
}
