# Android WebView hardening (getting past "WebView not allowed")

Why: Android WebView identifies itself (`; wv` in the UA, the `X-Requested-With` header, "Android WebView" in client hints, no `window.chrome`). iOS WKWebView looks like Safari, so it gets through.

Dependency:
```kotlin
implementation("androidx.webkit:webkit:1.12.1")
```

## 1. Basic settings and cookies
```kotlin
val s = webView.settings
s.javaScriptEnabled = true
s.domStorageEnabled = true
s.databaseEnabled = true
s.javaScriptCanOpenWindowsAutomatically = true
s.setSupportMultipleWindows(false)
s.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE

CookieManager.getInstance().apply {
    setAcceptCookie(true)
    setAcceptThirdPartyCookies(webView, true)
}
```

## 2. Make the User-Agent look like Chrome
```kotlin
s.userAgentString = s.userAgentString
    .replace("; wv", "")
    .replace(Regex("Version/\\d+\\.\\d+ "), "")
```

## 3. Remove `X-Requested-With`
```kotlin
if (WebViewFeature.isFeatureSupported(WebViewFeature.REQUESTED_WITH_HEADER_ALLOW_LIST)) {
    WebSettingsCompat.setRequestedWithHeaderOriginAllowList(s, emptySet())
}
```

## 4. Stub `window.chrome` before page scripts run
```kotlin
if (WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
    WebViewCompat.addDocumentStartJavaScript(webView, """
        if (!window.chrome) {
          window.chrome = { runtime: {}, app: { isInstalled: false }, csi(){}, loadTimes(){} };
        }
    """.trimIndent(), setOf("*"))
}
```

## 5. Keep navigation inside the app
```kotlin
webView.webViewClient = object : WebViewClient() {
    override fun shouldOverrideUrlLoading(v: WebView, r: WebResourceRequest) = false
}
webView.webChromeClient = WebChromeClient()
```

## 6. Keep the session across restarts
```kotlin
CookieManager.getInstance().flush()   // after login and in onPause
```

## 7. Google SSO (only if the portal uses it)
WebView can't do Google sign-in, so use a Custom Tab instead:
```kotlin
implementation("androidx.browser:browser:1.8.0")
CustomTabsIntent.Builder().build().launchUrl(context, Uri.parse(loginUrl))
```
Cookies in a Custom Tab don't carry over to your WebView, so you'd need a deep-link redirect that brings a token back to the app. Skip this step if the portal uses its own username and password.

## 8. Debug by comparing headers
Connect the phone over USB, open `chrome://inspect` on your PC and inspect the WebView. Compare its request headers on the Network tab with a login from real Chrome. Whatever differs is what the portal checks.

## Other things that sometimes matter
- **`Sec-CH-UA`** still says "Android WebView" and an app can't change it. If the portal checks it, fetch with OkHttp and set your own headers.
- **Remove `addJavascriptInterface` bridges** from the login page, because they're visible on `window`.
- **Captcha and Cloudflare pages** usually pass once steps 2 and 3 are done.
