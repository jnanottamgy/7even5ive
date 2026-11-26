package com.sevenfive.app.ui.screens

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.net.Uri
import android.webkit.CookieManager
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.Json
import com.sevenfive.app.portal.SubmitReport
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Science
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.sevenfive.app.portal.PortalCheck
import com.sevenfive.app.portal.PortalIdentity
import com.sevenfive.app.portal.PortalSettings
import com.sevenfive.app.portal.hardenPortalWebView
import com.sevenfive.app.portal.sendPortalFormsAsIphone
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.GlassPill
import com.sevenfive.app.ui.components.PushTopBar
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable
import com.sevenfive.app.util.Diagnostics

/**
 * Opens a college's real portal in the app's ordinary WebView, for the student to log in
 * themselves: does the college accept a login from an app?
 *
 * The WebView is configured like the portal login's and otherwise left as Android ships it: its
 * real User-Agent, no script added, nothing read from the page, nothing sent anywhere. The only
 * addition over the login screen is third-party cookies, which ordinary browsers allow and
 * which a login CAPTCHA served from another site can need.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun PortalCheckScreen(vm: AppViewModel, portalUrl: String, onBack: () -> Unit) {
    val portalHost = remember(portalUrl) { Uri.parse(portalUrl).host.orEmpty() }
    val appContext = vm.container.appContext
    var webView by remember { mutableStateOf<WebView?>(null) }
    var webKey by remember { mutableIntStateOf(0) }
    var loading by remember { mutableStateOf(true) }
    var title by remember { mutableStateOf("") }
    var where by remember { mutableStateOf(portalHost) }
    var problem by remember { mutableStateOf<String?>(null) }
    var identity by remember { mutableStateOf(PortalSettings.identity) }
    var lastSend by remember { mutableStateOf<SubmitReport?>(null) }
    var onLoginPage by remember { mutableStateOf<Boolean?>(null) }
    var everOnLogin by remember { mutableStateOf(false) }
    var portalMessage by remember { mutableStateOf<String?>(null) }

    BackHandler {
        val web = webView
        if (web != null && web.canGoBack()) web.goBack() else onBack()
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            PushTopBar("Portal test", portalHost, onBack = onBack) {
                Box(
                    Modifier
                        .padding(end = 10.dp)
                        .size(38.dp)
                        .pressable {
                            problem = null
                            val web = webView
                            if (web != null) web.reload() else webKey++
                        }
                        .glassSurface(shape = CircleShape, strong = true),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Outlined.Refresh, contentDescription = "Reload", modifier = Modifier.size(20.dp))
                }
            }
        },
    ) { inner ->
        Column(Modifier.padding(inner).fillMaxSize()) {
            val verdict = verdictOf(loading, problem, lastSend, onLoginPage, everOnLogin, portalMessage)
            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 6.dp)
                    .glassSurface(shape = MaterialTheme.shapes.medium, strong = true)
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(3.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(verdict.icon, contentDescription = verdict.level.name, tint = verdict.level.color,
                        modifier = Modifier.size(22.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(verdict.headline, style = MaterialTheme.typography.titleSmall, color = verdict.level.color,
                        maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                StatusRow("Browser", "${identity.label} · tap to switch", MaterialTheme.colorScheme.primary) {
                    val next = if (identity == PortalIdentity.IPHONE) PortalIdentity.ANDROID_CHROME
                    else PortalIdentity.IPHONE
                    PortalSettings.identity = next
                    identity = next
                    problem = null
                    lastSend = null
                    onLoginPage = null
                    everOnLogin = false
                    portalMessage = null
                    webView = null
                    webKey++
                }
                StatusRow("Page", where + (if (title.isNotBlank()) " · $title" else ""))
                StatusRow("Login form", when (onLoginPage) { true -> "showing"; false -> "not on this page"; null -> "-" })
                lastSend?.let { r ->
                    StatusRow("Sent", "HTTP ${r.code}" + (r.redirect?.let { " → $it" } ?: " (page)") + " · ${r.millis} ms")
                    StatusRow("Fields", "${r.fieldCount} sent" +
                        (if (r.emptyFields.isEmpty()) ", none empty" else ", empty: ${r.emptyFields.joinToString()}"))
                    StatusRow(
                        "reCAPTCHA",
                        when (r.captchaToken) { null -> "no token field"; true -> "token included"; false -> "token EMPTY" },
                        if (r.captchaToken == false) StatusRed else null,
                    )
                    StatusRow(
                        "Cookies sent",
                        if (r.cookiesSent.isEmpty()) "none" else "${r.cookiesSent.size}: ${r.cookiesSent.joinToString { it.take(12) }}",
                        if (r.cookiesSent.isEmpty()) StatusRed else null,
                    )
                    StatusRow("Cookies set",
                        if (r.cookiesSet.isEmpty()) "none" else r.cookiesSet.joinToString { "${it.first.take(12)} ${it.second}" })
                }
                portalMessage?.let { StatusRow("Portal says", it, StatusRed) }
                problem?.let { StatusRow("Problem", it, StatusRed) }
                Text(
                    "You log in yourself. In iPhone mode the app sends the portal's forms to the portal " +
                        "with iPhone headers; nothing is saved or sent anywhere else.",
                    style = MaterialTheme.typography.labelSmall,
                    color = LocalAppColors.current.secondaryLabel,
                )
            }
            Box(Modifier.fillMaxWidth().height(3.dp)) {
                if (loading) {
                    LinearProgressIndicator(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.primary,
                        trackColor = Color.Transparent)
                }
            }

            Box(Modifier.weight(1f).fillMaxWidth()) {
                key(webKey) {
                    AndroidView(
                        modifier = Modifier.fillMaxSize(),
                        factory = { ctx ->
                            Diagnostics.step(appContext, "portal test: opening $portalHost")
                            WebView(ctx).apply {
                                settings.javaScriptEnabled = true
                                settings.domStorageEnabled = true
                                settings.allowFileAccess = false
                                settings.allowContentAccess = false
                                // Same WebView hardening as the login (clean UA, third-party cookies,
                                // no X-Requested-With, userAgentData removed) so the portal's
                                // "no third-party apps" checks pass. No JS bridge is added.
                                hardenPortalWebView()
                                // iPhone mode: the login POST goes out with Safari's headers.
                                sendPortalFormsAsIphone(portalHost) { lastSend = it }
                                webChromeClient = object : WebChromeClient() {
                                    override fun onReceivedTitle(view: WebView, t: String?) {
                                        title = t.orEmpty()
                                    }
                                }
                                webViewClient = object : WebViewClient() {
                                    // The portal's own site, plus Google reCAPTCHA's frames (the
                                    // login's invisible challenge needs them); anything else stays out.
                                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                                        val target = request.url
                                        val host = target.host ?: ""
                                        val recaptcha = host == "google.com" || host.endsWith(".google.com") ||
                                            host == "gstatic.com" || host.endsWith(".gstatic.com") ||
                                            host == "recaptcha.net" || host.endsWith(".recaptcha.net")
                                        if (recaptcha || PortalCheck.sameSite(portalHost, target.host, target.scheme)) return false
                                        problem = "Stayed on $portalHost: the page tried to open ${target.host ?: "another app"}"
                                        return true
                                    }

                                    override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                                        loading = true
                                        problem = null
                                    }

                                    override fun onPageFinished(view: WebView, url: String?) {
                                        loading = false
                                        // Two facts about the page, nothing else: is it a login form, and
                                        // the portal's own notice (Joomla's message box) if it shows one.
                                        view.evaluateJavascript(LOGIN_PROBE_JS) { v ->
                                            val o = runCatching { Json.parseToJsonElement(v ?: "") as JsonObject }.getOrNull()
                                            val login = o?.get("login")?.jsonPrimitive?.booleanOrNull
                                            onLoginPage = login
                                            if (login == true) everOnLogin = true
                                            portalMessage = o?.get("msg")?.jsonPrimitive?.contentOrNull
                                                ?.replace(Regex("\\s+"), " ")?.trim()?.ifBlank { null }
                                        }
                                        // Host and path only: a query string can carry personal details.
                                        val u = url?.let(Uri::parse)
                                        if (u?.host != null) where = u.host + u.path.orEmpty()
                                    }

                                    override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                                        if (!request.isForMainFrame) return
                                        loading = false
                                        problem = "Couldn't open the page: ${error.description}"
                                    }

                                    override fun onReceivedHttpError(
                                        view: WebView,
                                        request: WebResourceRequest,
                                        errorResponse: WebResourceResponse,
                                    ) {
                                        if (!request.isForMainFrame) return
                                        problem = "The portal answered HTTP ${errorResponse.statusCode}"
                                    }

                                    override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                                        Diagnostics.step(appContext, "portal test: page renderer gone")
                                        if (webView === view) webView = null
                                        loading = false
                                        problem = "The page stopped working. Tap reload to try again."
                                        return true
                                    }
                                }
                                loadUrl(portalUrl)
                                webView = this
                            }
                        },
                        onRelease = { it.destroy() },
                    )
                }
            }

            Row(
                Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.End,
            ) {
                GlassPill("Log out of all portals", tint = MaterialTheme.colorScheme.error, onClick = {
                    // The app has one cookie store: this also logs out of the demo portal.
                    CookieManager.getInstance().removeAllCookies(null)
                    CookieManager.getInstance().flush()
                    vm.container.portalStore.forget()
                    vm.say("Logged out of every portal in the app")
                    webView?.reload()
                })
            }
        }
    }
}

private val StatusGreen = Color(0xFF2E9E4F)
private val StatusYellow = Color(0xFFD99A00)
private val StatusRed = Color(0xFFD93F3F)

private enum class Level(val color: Color) { GREEN(StatusGreen), YELLOW(StatusYellow), RED(StatusRed) }

private class Verdict(val level: Level, val headline: String) {
    val icon: ImageVector
        get() = when (level) {
            Level.GREEN -> Icons.Filled.CheckCircle
            Level.YELLOW -> Icons.Filled.Schedule
            Level.RED -> Icons.Filled.Cancel
        }
}

/**
 * Green: past the login form after logging in. Red: a page error, the portal's error notice, or
 * sent back to the login form after submitting it. Yellow: nothing tried yet, or still loading.
 */
private fun verdictOf(
    loading: Boolean,
    problem: String?,
    sent: SubmitReport?,
    onLogin: Boolean?,
    everOnLogin: Boolean,
    message: String?,
): Verdict = when {
    problem != null -> Verdict(Level.RED, "Failed: page error")
    loading -> Verdict(Level.YELLOW, "Loading…")
    sent != null && onLogin == true ->
        Verdict(Level.RED, if (message != null) "Refused: the portal sent you back to login"
        else "Refused: back on the login page, no reason given")
    onLogin == false && (sent != null || everOnLogin) -> Verdict(Level.GREEN, "Passed: you're past the login")
    message != null -> Verdict(Level.RED, "The portal shows an error")
    onLogin == true -> Verdict(Level.YELLOW, "Log in on the page below to run the test")
    else -> Verdict(Level.YELLOW, "Waiting for the login page")
}

@Composable
private fun StatusRow(label: String, value: String, color: Color? = null, onClick: (() -> Unit)? = null) {
    Row(if (onClick != null) Modifier.pressable(onClick = onClick) else Modifier) {
        Text(label, style = MaterialTheme.typography.labelMedium,
            color = LocalAppColors.current.secondaryLabel, modifier = Modifier.width(92.dp))
        Text(value, style = MaterialTheme.typography.labelMedium, color = color ?: MaterialTheme.colorScheme.onSurface,
            maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

/** Returns {login, msg}: a login form on the page (password box or the portal's login text), and its notice. */
private const val LOGIN_PROBE_JS =
    "(function(){var t=(document.body&&document.body.innerText)||'';" +
        "var login=!!document.querySelector('input[type=password]')||/log\\s*in to your account|forgot password/i.test(t);" +
        "var e=document.querySelector('#system-message-container .alert,#system-message-container .alert-message," +
        ".alert-error,.alert-danger,.alert-warning');" +
        "return {login:login,msg:e?e.innerText.trim().slice(0,200):''};})()"
