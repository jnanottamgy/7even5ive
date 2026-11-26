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
class IosFormSubmitter(private val web: WebView, private val portalHost: String) {
    private val main = Handler(Looper.getMainLooper())
    private val io = Executors.newSingleThreadExecutor()
    private val client = OkHttpClient.Builder()
        .followRedirects(false)
        .followSslRedirects(false)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(45, TimeUnit.SECONDS)
        .build()

    @JavascriptInterface
    fun post(action: String, fieldsJson: String, referer: String) {
        val target = Uri.parse(action)
        if (!PortalCheck.sameSite(portalHost, target.host, target.scheme)) return
        io.execute { send(action, fieldsJson, referer) }
    }

    private fun send(action: String, fieldsJson: String, referer: String) {
        val cookies = CookieManager.getInstance()
        val form = FormBody.Builder()
        runCatching { Json.parseToJsonElement(fieldsJson) as JsonArray }.getOrNull()?.forEach { pair ->
            val p = pair as? JsonArray ?: return@forEach
            if (p.size == 2) form.add(p[0].jsonPrimitive.content, p[1].jsonPrimitive.content)
        }
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
            .apply { cookies.getCookie(action)?.let { header("Cookie", it) } }
            .build()
        try {
            client.newCall(request).execute().use { r ->
                r.headers("Set-Cookie").forEach { cookies.setCookie(action, it) }
                cookies.flush()
                val location = r.header("Location")
                if (r.isRedirect && location != null) {
                    val next = java.net.URI(action).resolve(location).toString()
                    main.post { web.loadUrl(next) }
                } else {
                    val type = r.body?.contentType()
                    val html = r.body?.string().orEmpty()
                    val charset = type?.charset()?.name() ?: "utf-8"
                    main.post { web.loadDataWithBaseURL(action, html, "text/html", charset, action) }
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
         * Catches form POSTs before the WebView sends them, in the bubbling phase so the page's own
         * handlers run first; one that cancels the submit (to send it by fetch) is left alone. Forms
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
                "document.addEventListener('submit',function(e){if(e.defaultPrevented)return;" +
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
fun WebView.sendPortalFormsAsIphone(portalHost: String) {
    if (PortalSettings.identity != PortalIdentity.IPHONE || portalHost.isBlank()) return
    if (!androidx.webkit.WebViewFeature.isFeatureSupported(androidx.webkit.WebViewFeature.DOCUMENT_START_SCRIPT)) return
    addJavascriptInterface(IosFormSubmitter(this, portalHost), IosFormSubmitter.NAME)
    androidx.webkit.WebViewCompat.addDocumentStartJavaScript(
        this, IosFormSubmitter.INTERCEPT_JS, setOf("https://$portalHost", "http://$portalHost"),
    )
}
