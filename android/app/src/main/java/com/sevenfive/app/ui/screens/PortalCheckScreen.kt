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
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 6.dp)
                    .glassSurface(shape = MaterialTheme.shapes.medium, strong = true)
                    .padding(horizontal = 12.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Outlined.Science, contentDescription = null, tint = LocalAppColors.current.event,
                    modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(10.dp))
                Text(
                    "A test only. You log in yourself on the portal's own page. 7even5ive adds " +
                        "nothing to it, reads nothing from it and sends nothing anywhere.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Column(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Text(
                    "On: $where",
                    style = MaterialTheme.typography.labelMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                // Which browser the portal sees. Switching rebuilds the WebView from the start page.
                Text(
                    "Looks like: ${identity.label} · tap to switch",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.pressable {
                        val next = if (identity == PortalIdentity.IPHONE) PortalIdentity.ANDROID_CHROME
                        else PortalIdentity.IPHONE
                        PortalSettings.identity = next
                        identity = next
                        problem = null
                        webView = null
                        webKey++
                    },
                )
                if (title.isNotBlank()) {
                    Text(
                        "Page: $title",
                        style = MaterialTheme.typography.labelMedium,
                        color = LocalAppColors.current.secondaryLabel,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                problem?.let {
                    Text(it, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.error)
                }
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
