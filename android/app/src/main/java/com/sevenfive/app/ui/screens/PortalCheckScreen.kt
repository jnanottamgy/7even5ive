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
import com.sevenfive.app.portal.PortalLog
import com.sevenfive.app.portal.IosFormSubmitter
import kotlinx.serialization.json.JsonArray
import kotlinx.coroutines.delay
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.heightIn
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
    var recaptchaState by remember { mutableStateOf<String?>(null) }
    var pageChecks by remember { mutableStateOf<List<Check>>(emptyList()) }
    var iosRef by remember { mutableStateOf<IosFormSubmitter?>(null) }
    var pagesFetched by remember { mutableIntStateOf(0) }
    var dataResults by remember { mutableStateOf<List<JsonObject>>(emptyList()) }

    // What the probe found on the page: is it a login form, the portal's notice, and the checks.
    val applyProbe: (String?) -> Unit = { v ->
        val o = runCatching { Json.parseToJsonElement(v ?: "") as JsonObject }.getOrNull()
        if (o != null) {
            val login = o["login"]?.jsonPrimitive?.booleanOrNull
            onLoginPage = login
            if (login == true) everOnLogin = true
            recaptchaState = o["rc"]?.jsonPrimitive?.contentOrNull?.ifBlank { null }
            dataResults = (o["data"] as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
            portalMessage = o["msg"]?.jsonPrimitive?.contentOrNull
                ?.replace(Regex("\\s+"), " ")?.trim()?.ifBlank { null }
            val checks = (o["checks"] as? JsonArray).orEmpty().mapNotNull { c ->
                val a = c as? JsonArray ?: return@mapNotNull null
                Check(a[0].jsonPrimitive.content, a[1].jsonPrimitive.content.toIntOrNull() ?: 1,
                    a.getOrNull(2)?.jsonPrimitive?.contentOrNull.orEmpty())
            }
            if (checks != pageChecks) {
                PortalLog.add("checks: login=$login " + checks.joinToString(" | ") {
                    (when (it.state) { 2 -> "OK "; 0 -> "FAIL "; else -> "WAIT " }) + it.name +
                        (if (it.detail.isNotEmpty()) " (${it.detail})" else "")
                } + (portalMessage?.let { " | portal says: $it" } ?: ""))
            }
            pageChecks = checks
        }
    }

    // Re-run the probe every 2 s, so the checks follow the page (the reCAPTCHA token and the
    // anti-tamper field change after it has loaded).
    LaunchedEffect(webKey) {
        while (true) {
            delay(2000)
            pagesFetched = iosRef?.pagesFetched ?: 0
            webView?.evaluateJavascript(LOGIN_PROBE_JS, applyProbe)
        }
    }

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
                    .heightIn(max = 330.dp)
                    .verticalScroll(rememberScrollState())
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
                val appChecks = appChecks(identity, pagesFetched, lastSend, onLoginPage)
                val all = pageChecks + appChecks
                if (all.isNotEmpty()) {
                    val passed = all.count { it.state == 2 }
                    Text(
                        "Checks: $passed of ${all.size} passing" +
                            (if (identity != PortalIdentity.IPHONE) " (iPhone checks fail in Android mode)" else ""),
                        style = MaterialTheme.typography.labelMedium,
                        color = LocalAppColors.current.secondaryLabel,
                    )
                    all.forEach { CheckRow(it) }
                    Spacer(Modifier.height(4.dp))
                }
                if (onLoginPage == false) {
                    Text(
                        "Test data pages (attendance, marks, results…)",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.pressable {
                            PortalLog.add("--- data test started")
                            webView?.evaluateJavascript(DATA_TEST_JS, null)
                        },
                    )
                }
                dataResults.forEach { DataRow(it) }
                LogButtons(appContext)
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
                recaptchaState?.let {
                    StatusRow("reCAPTCHA page", it, if (it.startsWith("token ready")) null else StatusRed)
                }
                lastSend?.let { r ->
                    StatusRow("Sent", "HTTP ${r.code}" + (r.redirect?.let { " → $it" } ?: " (page)") + " · ${r.millis} ms")
                    StatusRow("Fields", "${r.fieldCount} sent" +
                        (if (r.emptyFields.isEmpty()) ", none empty" else ", empty: ${r.emptyFields.joinToString()}"))
                    StatusRow("Field names", r.fieldNames.joinToString { it.take(14) }, lines = 4)
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
                                val ios = sendPortalFormsAsIphone(portalHost) { lastSend = it }
                                iosRef = ios
                                webChromeClient = object : WebChromeClient() {
                                    override fun onReceivedTitle(view: WebView, t: String?) {
                                        title = t.orEmpty()
                                    }

                                    // The portal page's own console: its script errors show up here.
                                    override fun onConsoleMessage(m: android.webkit.ConsoleMessage): Boolean {
                                        PortalLog.add("console ${m.messageLevel()}: ${m.message().take(240)} " +
                                            "(${PortalLog.where(m.sourceId())}:${m.lineNumber()})")
                                        return true
                                    }
                                }
                                PortalLog.add("--- WebView opened: ${identity.label} mode, $portalHost, " +
                                    "WebView ${androidx.webkit.WebViewCompat.getCurrentWebViewPackage(ctx)?.versionName ?: "?"}, " +
                                    "Android ${android.os.Build.VERSION.RELEASE}, app ${com.sevenfive.app.BuildConfig.VERSION_NAME}")
                                webViewClient = object : WebViewClient() {
                                    // iPhone mode: the portal's GETs go out with iPhone headers too.
                                    override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                                        ios?.interceptGet(request)

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
                                        PortalLog.add("navigation blocked to ${PortalLog.where(target.toString())}")
                                        return true
                                    }

                                    override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                                        PortalLog.add("page started ${PortalLog.where(url)}")
                                        loading = true
                                        problem = null
                                    }

                                    override fun onPageFinished(view: WebView, url: String?) {
                                        PortalLog.add("page finished ${PortalLog.where(url)}")
                                        loading = false
                                        // Two facts about the page, nothing else: is it a login form, and
                                        // the portal's own notice (Joomla's message box) if it shows one.
                                        view.evaluateJavascript(LOGIN_PROBE_JS, applyProbe)
                                        // Host and path only: a query string can carry personal details.
                                        val u = url?.let(Uri::parse)
                                        if (u?.host != null) where = u.host + u.path.orEmpty()
                                    }

                                    override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                                        if (!request.isForMainFrame) return
                                        loading = false
                                        problem = "Couldn't open the page: ${error.description}"
                                        PortalLog.add("page error ${error.errorCode} ${error.description} at ${PortalLog.where(request.url.toString())}")
                                    }

                                    override fun onReceivedHttpError(
                                        view: WebView,
                                        request: WebResourceRequest,
                                        errorResponse: WebResourceResponse,
                                    ) {
                                        if (!request.isForMainFrame) return
                                        problem = "The portal answered HTTP ${errorResponse.statusCode}"
                                        PortalLog.add("http error ${errorResponse.statusCode} at ${PortalLog.where(request.url.toString())}")
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
private fun StatusRow(label: String, value: String, color: Color? = null, lines: Int = 2, onClick: (() -> Unit)? = null) {
    Row(if (onClick != null) Modifier.pressable(onClick = onClick) else Modifier) {
        Text(label, style = MaterialTheme.typography.labelMedium,
            color = LocalAppColors.current.secondaryLabel, modifier = Modifier.width(92.dp))
        Text(value, style = MaterialTheme.typography.labelMedium, color = color ?: MaterialTheme.colorScheme.onSurface,
            maxLines = lines, overflow = TextOverflow.Ellipsis)
    }
}

/** One check on the test screen: state 2 passes (green), 1 is unknown or not yet (yellow), 0 fails (red). */
private data class Check(val name: String, val state: Int, val detail: String = "")

/** The fields a real browser's login sends (seen on the MSRIT portal); any missing one fails the login. */
private val REQUIRED_LOGIN_FIELDS =
    listOf("username", "passwd", "cs_cap", "cs_env", "cs_n", "captcha-response", "g-recaptcha-response")

/** The app's own steps: pages fetched as an iPhone, the login sent, its fields, cookie and outcome. */
private fun appChecks(identity: PortalIdentity, pages: Int, sent: SubmitReport?, onLogin: Boolean?): List<Check> {
    val iphone = identity == PortalIdentity.IPHONE
    val out = mutableListOf<Check>()
    out += Check("Pages fetched as iPhone", if (!iphone) 1 else if (pages > 0) 2 else 0, "$pages requests")
    if (sent == null) {
        out += Check("Login sent as iPhone", 1, "log in to run")
        return out
    }
    out += Check("Login sent as iPhone", 2, "HTTP ${sent.code}, ${sent.millis} ms")
    val missing = REQUIRED_LOGIN_FIELDS.filter { it !in sent.fieldNames }
    out += Check("Required login fields", if (missing.isEmpty()) 2 else 0,
        if (missing.isEmpty()) "all ${REQUIRED_LOGIN_FIELDS.size} present" else "missing: ${missing.joinToString()}")
    val emptyNeeded = REQUIRED_LOGIN_FIELDS.filter { it in sent.emptyFields }
    out += Check("Required fields filled", if (emptyNeeded.isEmpty()) 2 else 0,
        if (emptyNeeded.isEmpty()) "none empty" else "empty: ${emptyNeeded.joinToString()}")
    out += Check("Session cookie sent", if (sent.cookiesSent.isNotEmpty()) 2 else 0, "${sent.cookiesSent.size} cookies")
    val session = sent.cookiesSet.firstOrNull()?.second
    out += Check("Portal kept/renewed session", if (session == null) 1 else 2, session ?: "no cookie set")
    out += Check("Still logged in after", when (onLogin) { false -> 2; true -> 0; null -> 1 },
        when (onLogin) { false -> "past the login"; true -> "back on login page"; null -> "checking" })
    return out
}

@Composable
private fun CheckRow(c: Check) {
    val color = when (c.state) { 2 -> StatusGreen; 0 -> StatusRed; else -> StatusYellow }
    val icon = when (c.state) { 2 -> Icons.Filled.CheckCircle; 0 -> Icons.Filled.Cancel; else -> Icons.Filled.Schedule }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, contentDescription = null, tint = color, modifier = Modifier.size(14.dp))
        Spacer(Modifier.width(6.dp))
        Text(c.name, style = MaterialTheme.typography.labelMedium, modifier = Modifier.width(170.dp),
            maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(c.detail, style = MaterialTheme.typography.labelSmall, color = LocalAppColors.current.secondaryLabel,
            maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/**
 * Probes the page: a login form, the portal's notice, the reCAPTCHA state, and checks of
 * everything the portal's own detectors read (UA, userAgentData, platform, window.chrome, its
 * cs_env field and its anti-tamper field). Reads no field values except those two detector fields.
 */
private val LOGIN_PROBE_JS = """
(function(){
var t=(document.body&&document.body.innerText)||'';
var login=!!document.querySelector('input[type=password]')||/log\s*in to your account|forgot password/i.test(t);
var e=document.querySelector('#system-message-container .alert,#system-message-container .alert-message,.alert-error,.alert-danger,.alert-warning');
var g=document.querySelector('[name=g-recaptcha-response]'),c=document.getElementById('captcha-response');
var tok=!!((g&&g.value)||(c&&c.value));
var rc=!login?'':(typeof grecaptcha==='undefined'?'script not loaded':!g?'loaded, widget missing':tok?'token ready':'loaded, no token yet');
var ua=navigator.userAgent||'',k=[];
function add(n,s,d){k.push([n,String(s),d||''])}
add('UA says iPhone Safari',/iPhone/.test(ua)&&!/Chrome|CriOS|; wv/.test(ua)?2:0,ua.slice(13,45));
add('userAgentData hidden',navigator.userAgentData===undefined?2:0);
add('platform is iPhone',navigator.platform==='iPhone'?2:0,navigator.platform);
add('vendor is Apple',/Apple/.test(navigator.vendor||'')?2:0,navigator.vendor);
add('no window.chrome',!window.chrome?2:0);
add('webdriver off',!navigator.webdriver?2:0);
add('no flutter/WebView bridge',typeof window.flutter_inappwebview==='undefined'?2:0);
var ce=document.getElementById('cs_env');
add('cs_env detector says ok',!ce?1:(ce.value==='ok'?2:0),ce?(ce.value||'empty'):'not on page');
var at=null;document.querySelectorAll('input[type=hidden]').forEach(function(i){if(/^u\d+\./.test(i.value))at=i});
if(at){var fl=at.value.split('.').slice(1).join('.');add('anti-tamper clean',fl?0:2,fl?('flags: '+fl):('taps seen: '+at.value.split('.')[0].slice(1)))}else add('anti-tamper clean',1,'not on page');
add('reCAPTCHA script loaded',typeof grecaptcha!=='undefined'?2:(login?0:1));
add('reCAPTCHA token ready',tok?2:(login?0:1),tok?'yes':'none yet');
add('iPhone form hook in page',window.__sfIos?2:0);
return {login:login,rc:rc,checks:k,data:window.__sfData||[],msg:e?e.innerText.trim().slice(0,200):''};
})()
""".trimIndent()

/** Copy or share the portal log (paste it to whoever is debugging), or clear it before a fresh try. */
@Composable
private fun LogButtons(context: android.content.Context) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    var note by remember { mutableStateOf<String?>(null) }
    Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
        Text("Copy log", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.pressable {
                clipboard.setText(androidx.compose.ui.text.AnnotatedString(PortalLog.dump()))
                note = "copied"
            })
        Text("Share log", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.pressable {
                val send = android.content.Intent(android.content.Intent.ACTION_SEND)
                    .setType("text/plain")
                    .putExtra(android.content.Intent.EXTRA_TEXT, PortalLog.dump())
                context.startActivity(android.content.Intent.createChooser(send, "Share portal log")
                    .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
            })
        Text("Clear log", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.pressable { PortalLog.clear(); note = "cleared" })
        note?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = LocalAppColors.current.secondaryLabel) }
    }
}

/** One data page's result: green when it came back logged in with the data's markers on it. */
@Composable
private fun DataRow(o: JsonObject) {
    fun str(k: String) = o[k]?.jsonPrimitive?.contentOrNull
    fun num(k: String) = o[k]?.jsonPrimitive?.contentOrNull?.toDoubleOrNull()?.toInt() ?: 0
    val page = str("page") ?: "?"
    val error = str("error")
    val status = num("status")
    val login = str("login") == "true"
    val markers = num("attendBadges") + num("attendRows") + num("chartArrays") + num("sgpa") + num("tables")
    val state = when {
        error != null || login || status >= 400 -> 0
        markers > 0 -> 2
        else -> 1
    }
    val detail = when {
        error != null -> "failed: $error"
        login -> "HTTP $status, but it's the LOGIN page (session lost)"
        else -> "HTTP $status, ${num("size") / 1024} KB, badges ${num("attendBadges")}, rows ${num("attendRows")}, " +
            "charts ${num("chartArrays")}, tables ${num("tables")}" +
            (if (num("sgpa") > 0) ", SGPA x${num("sgpa")}" else "") + (if (str("cgpa") == "true") ", CGPA" else "")
    }
    CheckRow(Check("Data: $page", state, detail))
}

/**
 * Fetches Contineo's data pages in this session, one at a time, from the logged-in page (so the
 * requests go through the iPhone path like the background sync's would). Reports structure only:
 * status, size, whether the login form came back, and counts of the elements the connector will
 * parse. No marks, attendance figures or names are read out.
 */
private val DATA_TEST_JS = """
(function(){
if(window.__sfDataRunning)return 'busy';
window.__sfDataRunning=1;window.__sfData=[];
var base=location.pathname.replace(/[^\/]*$/,'')+'index.php?';
var sd='option=com_studentdashboard&controller=studentdashboard&task=';
var pages=[['Dashboard',sd+'dashboard'],['Attendance',sd+'attendencelist'],['CIE marks',sd+'ciedetails'],
['Timetable',sd+'timetable'],['Results','option=com_history&controller=history&task=getResult']];
var B=window.SevenFiveIosSubmit;function L(m){try{B&&B.log(m)}catch(e){}}
var i=0;
function next(){
if(i>=pages.length){window.__sfDataRunning=0;L('data test done');return;}
var p=pages[i++],t0=Date.now();
fetch(base+p[1],{credentials:'include'}).then(function(r){return r.text().then(function(h){return [r.status,h]})}).then(function(a){
var h=a[1],d=new DOMParser().parseFromString(h,'text/html'),txt=(d.body&&d.body.textContent)||'';
var login=!!d.querySelector('#login-form,input[type=password]')||/log\s*in to your account/i.test(txt);
var m={page:p[0],status:a[0],ms:Date.now()-t0,size:h.length,login:login,
attendBadges:d.querySelectorAll('.cn-attend').length,
attendRows:d.querySelectorAll('.cn-attend-list1 tr,.cn-attend-list2 tr').length,
chartArrays:(h.match(/columns\s*:/g)||[]).length,
sgpa:(txt.match(/SGPA/g)||[]).length,cgpa:/CGPA/.test(txt),
tables:d.querySelectorAll('table').length};
window.__sfData.push(m);L('data '+JSON.stringify(m));setTimeout(next,600);
}).catch(function(e){var m={page:p[0],error:String(e)};window.__sfData.push(m);L('data '+JSON.stringify(m));setTimeout(next,600);});
}
next();return 'started';
})()
""".trimIndent()
