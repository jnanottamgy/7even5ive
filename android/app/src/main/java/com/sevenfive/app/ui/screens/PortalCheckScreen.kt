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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Science
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.sevenfive.app.portal.PortalCheck
import com.sevenfive.app.ui.AppViewModel
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
@OptIn(ExperimentalMaterial3Api::class)
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

    BackHandler {
        val web = webView
        if (web != null && web.canGoBack()) web.goBack() else onBack()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Portal test")
                        Text(
                            portalHost,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = {
                        problem = null
                        val web = webView
                        if (web != null) web.reload() else webKey++
                    }) { Icon(Icons.Outlined.Refresh, contentDescription = "Reload") }
                },
            )
        },
    ) { inner ->
        Column(Modifier.padding(inner).fillMaxSize()) {
            Surface(color = MaterialTheme.colorScheme.secondaryContainer) {
                Row(
                    Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(Icons.Outlined.Science, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(
                        "A test only. You log in yourself on the portal's own page. 7even5ive adds " +
                            "nothing to it, reads nothing from it and sends nothing anywhere.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
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
                if (title.isNotBlank()) {
                    Text(
                        "Page: $title",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                problem?.let {
                    Text(it, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.error)
                }
            }
            if (loading) LinearProgressIndicator(Modifier.fillMaxWidth())

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
                                CookieManager.getInstance().setAcceptCookie(true)
                                CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
                                webChromeClient = object : WebChromeClient() {
                                    override fun onReceivedTitle(view: WebView, t: String?) {
                                        title = t.orEmpty()
                                    }
                                }
                                webViewClient = object : WebViewClient() {
                                    // Only the portal's own site opens here; anything else stays out.
                                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                                        val target = request.url
                                        if (PortalCheck.sameSite(portalHost, target.host, target.scheme)) return false
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
                Modifier.fillMaxWidth().padding(horizontal = 8.dp),
                horizontalArrangement = Arrangement.End,
            ) {
                TextButton(onClick = {
                    // The app has one cookie store: this also logs out of the demo portal.
                    CookieManager.getInstance().removeAllCookies(null)
                    CookieManager.getInstance().flush()
                    vm.container.portalStore.forget()
                    vm.say("Logged out of every portal in the app")
                    webView?.reload()
                }) { Text("Log out of all portals") }
            }
        }
    }
}
