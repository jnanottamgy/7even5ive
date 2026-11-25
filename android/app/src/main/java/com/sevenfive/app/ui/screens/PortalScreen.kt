package com.sevenfive.app.ui.screens

import android.graphics.Bitmap
import android.net.Uri
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
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
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.Connector
import com.sevenfive.app.portal.PortalBridge
import com.sevenfive.app.portal.SyncOutcome
import com.sevenfive.app.portal.configureForPortal
import com.sevenfive.app.portal.sameOrigin
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.util.Diagnostics
import kotlinx.coroutines.launch

private enum class Phase { Loading, Login, Fetching, Failed }

/**
 * The college portal's own login page, in a WebView. The student types everything the portal
 * asks for, CAPTCHA included. We never fill in, submit, store or see the password; once the
 * page shows the logged-in marker, the runner GETs the plan's pages and they go to PortMax.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PortalScreen(vm: AppViewModel, onDone: () -> Unit) {
    val engine = vm.container.portal
    val servers by vm.servers.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    val bridge = remember { PortalBridge() }

    var connector by remember { mutableStateOf<Connector?>(null) }
    var phase by remember { mutableStateOf(Phase.Loading) }
    var problem by remember { mutableStateOf<String?>(null) }
    var hint by remember { mutableStateOf<String?>(null) }
    var attempt by remember { mutableIntStateOf(0) }
    var webView by remember { mutableStateOf<WebView?>(null) }
    var pageLoading by remember { mutableStateOf(false) }
    // Bumped to build a fresh WebView after the old one's renderer died.
    var webKey by remember { mutableIntStateOf(0) }

    val store = vm.container.portalStore
    val appContext = vm.container.appContext
    fun trail(what: String) = Diagnostics.step(appContext, what)
    DisposableEffect(Unit) {
        trail("portal screen opened")
        store.screenOpen = true
        onDispose { store.screenOpen = false }
    }

    LaunchedEffect(attempt) {
        phase = Phase.Loading
        problem = null
        try {
            connector = engine.connector()
            trail("connector settings loaded")
            phase = Phase.Login
        } catch (e: ApiException) {
            problem = "Couldn't load the portal settings from PortMax: ${e.detail}"
            phase = Phase.Failed
        } catch (e: kotlinx.coroutines.CancellationException) {
            throw e
        } catch (e: Exception) {
            problem = "Couldn't read the portal settings from PortMax (${e.javaClass.simpleName})"
            phase = Phase.Failed
        }
    }

    fun fetch(web: WebView, c: Connector) {
        if (phase == Phase.Fetching) return
        phase = Phase.Fetching
        hint = null
        scope.launch {
            when (val out = engine.fetchAndUpload(web, bridge, c, keepAlive = false)) {
                is SyncOutcome.Saved -> {
                    vm.say("Attendance updated from ${c.info.name.ifBlank { "your portal" }}")
                    onDone()
                }
                SyncOutcome.SessionExpired -> {
                    phase = Phase.Login
                    hint = "You're not logged in yet. Finish logging in on the portal page."
                    web.loadUrl(engine.loginUrl(servers.portalUrl, c))
                }
                is SyncOutcome.Failed -> {
                    phase = Phase.Failed
                    problem = out.message
                }
            }
        }
    }

    BackHandler {
        val web = webView
        if (web != null && web.canGoBack() && phase == Phase.Login) web.goBack() else onDone()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Portal login")
                        connector?.info?.name?.takeIf { it.isNotBlank() }?.let {
                            Text(it, style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onDone) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    val web = webView
                    val c = connector
                    if (web != null && c != null && phase == Phase.Login) {
                        TextButton(onClick = { fetch(web, c) }) { Text("I'm logged in") }
                    }
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
                    Icon(Icons.Outlined.Lock, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(
                        hint ?: "Log in yourself on your portal's own page. 7even5ive never sees your password.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
            if (pageLoading && phase == Phase.Login) LinearProgressIndicator(Modifier.fillMaxWidth())

            Box(Modifier.weight(1f).fillMaxWidth()) {
                val c = connector
                if (c != null) {
                    val loginUrl = engine.loginUrl(servers.portalUrl, c)
                    val portalOrigin = Uri.parse(servers.portalUrl)
                    key(webKey) { AndroidView(
                        modifier = Modifier.fillMaxSize(),
                        factory = { ctx ->
                            trail("WebView provider: " + webViewProvider())
                            trail("creating WebView")
                            WebView(ctx).apply {
                                trail("WebView created; configuring")
                                configureForPortal(bridge)
                                trail("WebView configured")
                                webViewClient = object : WebViewClient() {
                                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                                        if (sameOrigin(request.url, portalOrigin)) return false
                                        vm.say("This screen only opens your college portal.")
                                        return true
                                    }

                                    override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                                        trail("page started")
                                        pageLoading = true
                                    }

                                    override fun onPageFinished(view: WebView, url: String?) {
                                        trail("page finished")
                                        pageLoading = false
                                        if (phase != Phase.Login) return
                                        scope.launch {
                                            val loggedIn = runCatching { engine.isLoggedIn(view, c) }.getOrDefault(false)
                                            if (loggedIn && phase == Phase.Login) fetch(view, c)
                                        }
                                    }

                                    // The page's renderer died. Without this Android kills the app too.
                                    override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                                        trail("page renderer gone (crashed=${detail.didCrash()})")
                                        if (webView === view) webView = null
                                        pageLoading = false
                                        problem = "The portal page stopped working. Tap Try again to reload it."
                                        phase = Phase.Failed
                                        return true
                                    }

                                    override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                                        if (!request.isForMainFrame) return
                                        pageLoading = false
                                        problem = "Couldn't open the portal at ${servers.portalUrl}: ${error.description}"
                                        phase = Phase.Failed
                                    }
                                }
                                trail("loading portal page")
                                loadUrl(loginUrl)
                                webView = this
                            }
                        },
                        onRelease = { it.destroy() },
                    ) }
                }

                when (phase) {
                    Phase.Loading -> Centered { CircularProgressIndicator() }
                    Phase.Fetching -> Overlay {
                        CircularProgressIndicator()
                        Text("Fetching attendance from your portal…", style = MaterialTheme.typography.titleMedium)
                        Text("Read-only: a few pages, one at a time, with your own session.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Phase.Failed -> Overlay {
                        Icon(Icons.Outlined.ErrorOutline, contentDescription = null,
                            tint = MaterialTheme.colorScheme.error, modifier = Modifier.size(40.dp))
                        Text(problem ?: "Something went wrong", style = MaterialTheme.typography.bodyLarge)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedButton(onClick = onDone) { Text("Close") }
                            Button(onClick = {
                                problem = null
                                val web = webView
                                if (connector == null) {
                                    attempt++
                                } else if (web == null) {
                                    phase = Phase.Login
                                    webKey++
                                } else {
                                    phase = Phase.Login
                                    web.loadUrl(engine.loginUrl(servers.portalUrl, connector!!))
                                }
                            }) { Text("Try again") }
                        }
                    }
                    Phase.Login -> Unit
                }
            }
        }
    }
}

@Composable
private fun Centered(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { content() }
}

@Composable
private fun Overlay(content: @Composable () -> Unit) {
    Box(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background.copy(alpha = 0.94f)),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            Modifier.padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) { content() }
    }
}


/** Which WebView the phone uses, e.g. "com.google.android.webview 157.0.8103.50". */
private fun webViewProvider(): String = runCatching {
    WebView.getCurrentWebViewPackage()?.let { "${it.packageName} ${it.versionName}" } ?: "none"
}.getOrElse { "unknown (${it.javaClass.simpleName})" }
