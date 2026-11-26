package com.sevenfive.app.portal

import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebView
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Sends the portal's own form POSTs (the login with its reCAPTCHA token, and the steps after it)
 * with an iPhone's headers instead of the WebView's.
 *
 * Why: Chromium adds headers to every request that page JavaScript can't change: Sec-CH-UA,
 * Sec-CH-UA-Mobile and Sec-CH-UA-Platform ("Android"), plus Chrome's long Accept list. An iPhone
 * sends no client hints at all, so the portal can tell an Android WebView from an iOS one by the
 * POST alone. Here the page's submit is caught in JavaScript, the fields come to Kotlin, OkHttp
 * posts them with Safari's headers and the WebView's own cookies, and the answer is loaded back
 * into the WebView. Cookies the portal sets go back into the WebView's CookieManager.
 *
 * Only POSTs to the portal's own site are sent this way; anything else is refused and the page
 * is left alone. Field values are held in memory for the one request and never logged or stored.
 * Not covered: the TLS handshake is OkHttp's, not Safari's.
 */
/**
 * What one iPhone-style POST did, for the test screen. Names and counts only: never a field's
 * value, a cookie's value or a query string.
 */
data class SubmitReport(
    val code: Int,
    /** Where the portal redirected (host + path), or null when it answered with a page. */
    val redirect: String?,
    val millis: Long,
    val fieldCount: Int,
    val emptyFields: List<String>,
    /** null: the form had no reCAPTCHA field; true/false: its token was filled in or not. */
    val captchaToken: Boolean?,
    val cookiesSent: List<String>,
    /** Each cookie the portal set: name to "kept", "replaced" or "new". */
    val cookiesSet: List<Pair<String, String>>,
)

class IosFormSubmitter(
    private val web: WebView,
    private val portalHost: String,
    /** What each POST did, on the main thread. */
    private val report: (SubmitReport) -> Unit = {},
) {
    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()
    private val client = OkHttpClient.Builder()
        .followRedirects(false)
        .followSslRedirects(false)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(45, TimeUnit.SECONDS)
        .build()

    /**
     * Every GET to the portal's own site, sent with iPhone headers instead of the WebView's.
     *
     * Why: a login sent as an iPhone and the very next page fetched with Chromium's headers
     * (Sec-CH-UA-Platform "Android" and the rest) look like two devices on one session, and the
     * portal drops it. So in iPhone mode the WebView makes no request to the portal itself: page
     * loads, scripts and images all come through here, with the WebView's cookies, and cookies the
     * portal sets are copied back (the WebView ignores Set-Cookie on a response it didn't fetch).
     * Call from WebViewClient.shouldInterceptRequest (a background thread). Returns null for
     * anything that isn't a same-site GET, which the WebView then fetches as usual (Google's
     * reCAPTCHA included).
     */
    fun interceptGet(request: android.webkit.WebResourceRequest): android.webkit.WebResourceResponse? {
        val url = request.url
        if (!request.method.equals("GET", ignoreCase = true)) return null
        if (!PortalCheck.sameSite(portalHost, url.host, url.scheme)) return null
        val cookies = CookieManager.getInstance()
        val asked = request.requestHeaders.entries.associate { it.key.lowercase() to it.value }
        val builder = Request.Builder().url(url.toString()).get()
            .header("User-Agent", IOS_USER_AGENT)
            .header("Accept-Language", "en-IN,en-GB;q=0.9,en;q=0.8")
        if (request.isForMainFrame) {
            builder.header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                .header("Sec-Fetch-Site", "same-origin")
                .header("Sec-Fetch-Mode", "navigate")
                .header("Sec-Fetch-Dest", "document")
        } else {
            builder.header("Accept", asked["accept"] ?: "*/*")
        }
        asked["referer"]?.let { builder.header("Referer", it) }
        cookies.getCookie(url.toString())?.let { builder.header("Cookie", it) }
        return try {
            val r = client.newCall(builder.build()).execute()
            r.headers("Set-Cookie").forEach { cookies.setCookie(url.toString(), it) }
            val location = r.header("Location")
            if (r.isRedirect && location != null) {
                r.close()
                val next = java.net.URI(url.toString()).resolve(location).toString()
                if (!request.isForMainFrame) return null  // a redirected script or image: let the WebView fetch it
                // WebResourceResponse can't carry a 3xx, so a tiny page moves the frame on; the
                // next load comes back through here.
                val page = "<html><head><script>location.replace(${kotlinx.serialization.json.JsonPrimitive(next)})</script></head></html>"
                return android.webkit.WebResourceResponse("text/html", "utf-8", 200, "OK",
                    mapOf("Cache-Control" to "no-store"), page.byteInputStream())
            }
            val body = r.body ?: return null
            val type = body.contentType()
            val mime = type?.let { "${it.type}/${it.subtype}" } ?: "application/octet-stream"
            val charset = type?.charset()?.name() ?: if (type?.type == "text") "utf-8" else null
            val headers = r.headers.names()
                .filter { it.lowercase() !in setOf("set-cookie", "content-encoding", "content-length", "transfer-encoding", "content-type") }
                .associateWith { r.header(it).orEmpty() }
            android.webkit.WebResourceResponse(mime, charset, r.code, r.message.ifBlank { "OK" }, headers, body.byteStream())
        } catch (e: Exception) {
            null  // the WebView tries itself, which is no worse than before
        }
    }

    @JavascriptInterface
    fun post(action: String, fieldsJson: String, referer: String) {
        val target = Uri.parse(action)
        if (!PortalCheck.sameSite(portalHost, target.host, target.scheme)) return
        io.execute { send(action, fieldsJson, referer) }
    }

    private fun send(rawAction: String, fieldsJson: String, referer: String) {
        val cookies = CookieManager.getInstance()
        // An http action on an https page would leave out the Secure session cookie, so the
        // portal would start a new session and refuse the login. Browsers upgrade it; so do we.
        val action = Uri.parse(rawAction).let { a ->
            if (a.scheme == "http" && Uri.parse(referer).scheme == "https" && a.host == Uri.parse(referer).host)
                a.buildUpon().scheme("https").build().toString() else rawAction
        }
        val sentCookie = cookies.getCookie(action).orEmpty()
        val sent = sentCookie.split(';').map { it.trim() }.filter { '=' in it }
            .associate { it.substringBefore('=') to it.substringAfter('=') }
        val form = FormBody.Builder()
        val fields = mutableListOf<Pair<String, Boolean>>()  // name to "has a value"
        runCatching { Json.parseToJsonElement(fieldsJson) as JsonArray }.getOrNull()?.forEach { pair ->
            val p = pair as? JsonArray ?: return@forEach
            if (p.size == 2) {
                val name = p[0].jsonPrimitive.content
                val value = p[1].jsonPrimitive.content
                form.add(name, value)
                fields += name to value.isNotBlank()
            }
        }
        val captcha = fields.filter { it.first.contains("recaptcha", true) || it.first.contains("captcha-response", true) }
        val started = System.currentTimeMillis()
        val origin = Uri.parse(action).let { "${it.scheme}://${it.authority}" }
        val request = Request.Builder().url(action).post(form.build())
            .header("User-Agent", IOS_USER_AGENT)
            .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            .header("Accept-Language", "en-IN,en-GB;q=0.9,en;q=0.8")
            .header("Origin", origin)
            .header("Referer", referer)
            .header("Sec-Fetch-Site", if (sameOriginStr(referer, origin)) "same-origin" else "same-site")
            .header("Sec-Fetch-Mode", "navigate")
            .header("Sec-Fetch-Dest", "document")
            .apply { if (sentCookie.isNotEmpty()) header("Cookie", sentCookie) }
            .build()
        try {
            client.newCall(request).execute().use { r ->
                val setCookies = r.headers("Set-Cookie")
                val location = r.header("Location")
                val next = if (r.isRedirect && location != null) java.net.URI(action).resolve(location).toString() else null
                val type = r.body?.contentType()
                val html = if (next == null) r.body?.string().orEmpty() else ""
                val charset = type?.charset()?.name() ?: "utf-8"
                // Each cookie the portal set: "kept" if it's the value we sent, "replaced" if it
                // swapped it (a new session), "new" if we had none. Names only, never values.
                val set = setCookies.map { c ->
                    val name = c.substringBefore('=').trim()
                    val value = c.substringAfter('=').substringBefore(';').trim()
                    name to when (sent[name]) { null -> "new"; value -> "kept"; else -> "replaced" }
                }.distinct()
                val summary = SubmitReport(
                    code = r.code,
                    redirect = next?.let { Uri.parse(it) }?.let { "${it.host}${it.path.orEmpty()}" },
                    millis = System.currentTimeMillis() - started,
                    fieldCount = fields.size,
                    emptyFields = fields.filter { !it.second }.map { it.first },
                    captchaToken = if (captcha.isEmpty()) null else captcha.any { it.second },
                    cookiesSent = sent.keys.toList(),
                    cookiesSet = set,
                )
                // setCookie is asynchronous: load the next page only once every cookie has landed,
                // or the portal sees a request without its new session and shows the login again.
                // Its callback needs a Looper, so this runs on the main thread.
                main.post {
                    report(summary)
                    val load = {
                        cookies.flush()
                        if (next != null) web.loadUrl(next)
                        else web.loadDataWithBaseURL(action, html, "text/html", charset, action)
                    }
                    if (setCookies.isEmpty()) { load(); return@post }
                    var left = setCookies.size
                    setCookies.forEach { c ->
                        cookies.setCookie(action, c) { left -= 1; if (left == 0) load() }
                    }
                }
            }
        } catch (e: Exception) {
            main.post {
                web.evaluateJavascript("alert('Couldn\\'t reach the portal. Check your connection and try again.')", null)
            }
        }
    }

    private fun sameOriginStr(a: String, origin: String): Boolean =
        Uri.parse(a).let { "${it.scheme}://${it.authority}" }.equals(origin, ignoreCase = true)

    companion object {
        const val NAME = "SevenFiveIosSubmit"

        /**
         * Catches form POSTs before the WebView sends them, on window in the bubbling phase so every
         * handler the page has (on the form or on document, e.g. the one that adds the reCAPTCHA
         * token or builds the password) runs first; one that cancels the submit is left alone. Forms
         * with files, and GET forms, go through the WebView as normal. form.submit() is routed the
         * same way, since it fires no submit event.
         */
        const val INTERCEPT_JS =
            "(function(){if(window.__sfIos)return;window.__sfIos=1;var B=window." + NAME + ";if(!B)return;" +
                "function go(f,sub){if((f.getAttribute('method')||'get').toLowerCase()!=='post')return false;" +
                "var fd;try{fd=new FormData(f,sub||undefined);}catch(e){fd=new FormData(f);}" +
                "var out=[],file=false;fd.forEach(function(v,k){if(typeof v==='string')out.push([k,v]);else file=true;});" +
                "if(file)return false;var a=new URL(f.getAttribute('action')||location.href,location.href).href;" +
                "B.post(a,JSON.stringify(out),location.href);return true;}" +
                "window.addEventListener('submit',function(e){if(e.defaultPrevented)return;" +
                "if(go(e.target,e.submitter))e.preventDefault();},false);" +
                "var s=HTMLFormElement.prototype.submit;" +
                "HTMLFormElement.prototype.submit=function(){if(!go(this,null))return s.call(this);};" +
                "})();"
    }
}

/**
 * In iPhone mode, routes the portal's form POSTs through [IosFormSubmitter]. Only the portal's own
 * origins get the intercept script; reCAPTCHA's frames are left untouched.
 */
@android.annotation.SuppressLint("JavascriptInterface")
fun WebView.sendPortalFormsAsIphone(portalHost: String, report: (SubmitReport) -> Unit = {}): IosFormSubmitter? {
    if (PortalSettings.identity != PortalIdentity.IPHONE || portalHost.isBlank()) return null
    if (!androidx.webkit.WebViewFeature.isFeatureSupported(androidx.webkit.WebViewFeature.DOCUMENT_START_SCRIPT)) return null
    val submitter = IosFormSubmitter(this, portalHost, report)
    addJavascriptInterface(submitter, IosFormSubmitter.NAME)
    androidx.webkit.WebViewCompat.addDocumentStartJavaScript(
        this, IosFormSubmitter.INTERCEPT_JS, setOf("https://$portalHost", "http://$portalHost"),
    )
    return submitter
}
