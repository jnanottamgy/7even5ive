package com.sevenfive.app

import com.sevenfive.app.data.Discovery
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** Real time on purpose (runBlocking): runTest's virtual clock fires the scan timeout at once. */
class DiscoveryTest {
    private lateinit var server: MockWebServer

    @Before
    fun start() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest) =
                if (request.path == "/api/health") MockResponse().setBody("""{"service":"7even5ive","version":1}""")
                else MockResponse().setResponseCode(404)
        }
        server.start(java.net.InetAddress.getByName("127.0.0.1"), 0)
    }

    @After
    fun stop() = server.shutdown()

    @Test
    fun `only 7even5ive's own health answer counts`() {
        assertTrue(Discovery.isHealth("""{"service":"7even5ive","version":1}"""))
        assertFalse(Discovery.isHealth("""{"service":"something-else"}"""))
        assertFalse(Discovery.isHealth("<html>router login</html>"))
        assertFalse(Discovery.isHealth(""))
    }

    @Test
    fun `scans every host of each network once`() {
        val hosts = Discovery.candidates(listOf("10.72.161", "192.168.1"))
        assertEquals(508, hosts.size)
        assertEquals("10.72.161.1", hosts.first())
        assertTrue("10.72.161.15" in hosts && "192.168.1.254" in hosts)
        assertFalse("10.72.161.0" in hosts || "10.72.161.255" in hosts)
    }

    @Test
    fun `finds the laptop that answers on the network`() = runBlocking {
        val found = Discovery(port = server.port).find(listOf("127.0.0"))
        assertEquals("127.0.0.1", found)
    }

    @Test
    fun `finds nothing when nobody answers`() = runBlocking {
        server.shutdown()
        assertNull(Discovery(port = 9).find(listOf("127.0.0")))
    }

    @Test
    fun `no network means no scan`() = runBlocking {
        assertNull(Discovery().find(emptyList()))
    }
}
