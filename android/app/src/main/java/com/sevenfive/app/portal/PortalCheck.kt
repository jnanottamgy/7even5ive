package com.sevenfive.app.portal

import java.net.URI

/**
 * The portal test: opens a college's real portal in the app's ordinary WebView so the student
 * can log in themselves and see whether the college accepts a login from an app at all.
 *
 * It is a test and nothing more: no runner is injected, nothing on the page is read, nothing is
 * uploaded, and the background refresh never uses it. The WebView is the same unmodified one the
 * portal login uses; if the college refuses app logins, the test shows that and we stop there.
 */
object PortalCheck {
    const val DEFAULT_URL = "https://parents.msrit.edu/"

    /** A web address from what someone typed ("parents.msrit.edu" → "https://parents.msrit.edu"), or null. */
    fun normalise(input: String): String? {
        val t = input.trim()
        if (t.isEmpty() || t.any { it.isWhitespace() }) return null
        val withScheme = if (t.startsWith("https://") || t.startsWith("http://")) t else "https://$t"
        val host = runCatching { URI(withScheme).host }.getOrNull() ?: return null
        return if ('.' in host) withScheme else null
    }

    /** The site a host belongs to: its last two labels, so "parents.msrit.edu" → "msrit.edu". */
    fun site(host: String): String =
        host.lowercase().trimEnd('.').split('.').takeLast(2).joinToString(".")

    /**
     * True if a page may open inside the test: a web page on the same site as the portal
     * (parents.msrit.edu → exam.msrit.edu is fine; anything else stays out).
     */
    fun sameSite(portalHost: String, targetHost: String?, targetScheme: String?): Boolean =
        !targetHost.isNullOrBlank() &&
            (targetScheme == "https" || targetScheme == "http") &&
            site(portalHost) == site(targetHost)
}
