package com.sevenfive.app.data

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelChildren
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import java.net.Inet4Address
import java.net.NetworkInterface
import java.util.concurrent.TimeUnit

/**
 * Finds the laptop running 7even5ive on this phone's own network (its hotspot, or the Wi-Fi it
 * shares with the laptop), so nobody types an IP: every address in the phone's /24 is asked for
 * GET /api/health, and the first that answers {"service":"7even5ive"} wins. ~254 tiny requests,
 * 48 at a time, a couple of seconds in all. Mobile-data interfaces are skipped.
 */
class Discovery(private val port: Int = 8000) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(500, TimeUnit.MILLISECONDS)
        .readTimeout(800, TimeUnit.MILLISECONDS)
        .callTimeout(1200, TimeUnit.MILLISECONDS)
        .build()

    /** The host that answered, e.g. "10.72.161.15", or null if none did. */
    suspend fun find(prefixes: List<String> = localPrefixes()): String? {
        val hosts = candidates(prefixes)
        if (hosts.isEmpty()) return null
        return withTimeoutOrNull(SCAN_TIMEOUT_MILLIS) {
            coroutineScope {
                val found = CompletableDeferred<String?>()
                val gate = Semaphore(PARALLEL)
                val jobs = hosts.map { host ->
                    launch(Dispatchers.IO) {
                        gate.withPermit { if (!found.isCompleted && probe(host)) found.complete(host) }
                    }
                }
                launch {
                    jobs.forEach { it.join() }
                    found.complete(null)
                }
                found.await().also { coroutineContext.cancelChildren() }
            }
        }
    }

    /** True if [host] runs 7even5ive's core on [port]. */
    suspend fun probe(host: String): Boolean = withContext(Dispatchers.IO) {
        runCatching {
            client.newCall(Request.Builder().url("http://$host:$port/api/health").build()).execute().use { r ->
                r.isSuccessful && isHealth(r.body?.string().orEmpty())
            }
        }.getOrDefault(false)
    }

    companion object {
        private const val PARALLEL = 48
        private const val SCAN_TIMEOUT_MILLIS = 15_000L
        /** Cellular and VPN interfaces: never where the laptop is, and not worth a scan. */
        private val SKIP = listOf("rmnet", "ccmni", "pdp", "v4-", "dummy", "tun", "ipsec", "clat")

        fun isHealth(body: String): Boolean = runCatching {
            (AppJson.parseToJsonElement(body) as JsonObject)["service"]?.jsonPrimitive?.content == "7even5ive"
        }.getOrDefault(false)

        /** "10.72.161" for each private IPv4 network this phone is on, hotspot first. */
        fun localPrefixes(): List<String> = runCatching {
            NetworkInterface.getNetworkInterfaces().toList()
                .filter { it.isUp && !it.isLoopback && SKIP.none { s -> it.name.startsWith(s) } }
                .sortedBy { if (it.name.startsWith("swlan") || it.name.startsWith("ap")) 0 else 1 }
                .flatMap { it.inetAddresses.toList() }
                .filterIsInstance<Inet4Address>()
                .filter { it.isSiteLocalAddress }
                .mapNotNull { it.hostAddress?.substringBeforeLast('.') }
                .distinct()
        }.getOrDefault(emptyList())

        /** Every host in each /24, nearest-likely first (.1 and the phone's neighbours are as good as any). */
        fun candidates(prefixes: List<String>): List<String> =
            prefixes.flatMap { prefix -> (1..254).map { "$prefix.$it" } }.distinct()
    }
}
