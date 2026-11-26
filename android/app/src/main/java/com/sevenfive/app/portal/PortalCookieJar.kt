package com.sevenfive.app.portal

import android.webkit.CookieManager
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl

/**
 * The portal's cookies for the iPhone path, held here so every request sees the previous answer's
 * cookies at once.
 *
 * Why: CookieManager.setCookie is asynchronous. After the login's 303 the very next GET read the
 * store before the new session cookie had landed, went out with no cookies at all, and the portal
 * started a fresh session and showed the login again (seen in the log: "cookies-sent 0").
 * Every cookie is still copied to CookieManager, so the WebView's own requests (reCAPTCHA, XHR)
 * carry it too. Cookies the WebView already had (from before iPhone mode) seed the jar once.
 */
class PortalCookieJar : CookieJar {
    private val cookies = mutableListOf<Cookie>()
    private val seededNames = mutableSetOf<String>()
    private var seededHosts = mutableSetOf<String>()

    @Synchronized
    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        val manager = CookieManager.getInstance()
        for (c in cookies) {
            // A cookie the portal sets replaces any of the same name we only guessed at (seeded
            // from CookieManager, which doesn't tell us domain or path).
            if (c.name in seededNames) {
                this.cookies.removeAll { it.name == c.name && it.name in seededNames }
                seededNames.remove(c.name)
            }
            this.cookies.removeAll { it.name == c.name && it.domain == c.domain && it.path == c.path }
            if (c.expiresAt > System.currentTimeMillis()) this.cookies += c
            manager.setCookie(url.toString(), c.toString())
            PortalLog.add("jar: ${if (c.expiresAt > System.currentTimeMillis()) "set" else "deleted"} ${c.name} " +
                "domain=${c.domain}${if (c.hostOnly) "(host-only)" else ""} path=${c.path}" +
                "${if (c.secure) " secure" else ""}${if (c.httpOnly) " httponly" else ""}" +
                "${if (c.persistent) " persistent" else " session"} -> ${this.cookies.size} in jar")
        }
        manager.flush()
    }

    @Synchronized
    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        seedFrom(url)
        val now = System.currentTimeMillis()
        this.cookies.removeAll { it.expiresAt <= now }
        return this.cookies.filter { it.matches(url) }
    }

    /** Takes the WebView's cookies for this host once, as host-only cookies on "/". */
    private fun seedFrom(url: HttpUrl) {
        if (!seededHosts.add(url.host)) return
        val header = CookieManager.getInstance().getCookie(url.toString()) ?: return
        header.split(';').map { it.trim() }.filter { '=' in it }.forEach { pair ->
            val name = pair.substringBefore('=')
            if (cookies.any { it.name == name }) return@forEach
            val c = Cookie.Builder().name(name).value(pair.substringAfter('=')).hostOnlyDomain(url.host).path("/").build()
            cookies += c
            seededNames += name
        }
        PortalLog.add("jar: seeded ${seededNames.size} cookie(s) from the WebView for ${url.host}")
    }

    /** Names of the cookies that would go to [url], for the log. */
    @Synchronized
    fun namesFor(url: HttpUrl): List<String> = cookies.filter { it.matches(url) }.map { it.name }
}
