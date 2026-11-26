package com.sevenfive.app

import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.Http
import com.sevenfive.app.data.ServerConfig
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class CoreApiTest {
    private lateinit var server: MockWebServer
    private lateinit var api: CoreApi

    @Before
    fun start() {
        server = MockWebServer()
        server.start()
        val base = server.url("/").toString().trimEnd('/')
        api = CoreApi(Http("demo-student-token")) { base }
    }

    @After
    fun stop() = server.shutdown()

    @Test
    fun `every call carries the bearer token`() = runTest {
        server.enqueue(MockResponse().setBody("{}"))
        api.cards()
        val request = server.takeRequest()
        assertEquals("/api/cards", request.path)
        assertEquals("Bearer demo-student-token", request.getHeader("Authorization"))
    }

    @Test
    fun `set_reminder goes through the tools route with args`() = runTest {
        server.enqueue(MockResponse().setBody(
            """{"status":"ok","result":{"reminder_id":4,"fires_at":"2026-11-27T22:59+05:30","title":"DBMS Assignment 3"}}"""
        ))
        val r = api.setReminder(itemId = 1, beforeMinutes = 60)
        assertEquals(4, r.id)
        val request = server.takeRequest()
        assertEquals("/api/tools/set_reminder", request.path)
        assertEquals("""{"args":{"item_id":1,"before_minutes":60,"channel":"push"}}""", request.body.readUtf8())
    }

    @Test
    fun `a call reminder says so and comes back as a call`() = runTest {
        server.enqueue(MockResponse().setBody(
            """{"status":"ok","result":{"reminder_id":5,"fires_at":"2026-11-27T21:59+05:30","title":"Lab","channel":"call"}}"""
        ))
        val r = api.setReminder(itemId = 2, beforeMinutes = 120, channel = "call")
        assertEquals("call", r.channel)
        assertEquals("""{"args":{"item_id":2,"before_minutes":120,"channel":"call"}}""", server.takeRequest().body.readUtf8())
    }

    @Test
    fun `mark done and reopen are gateway tools`() = runTest {
        server.enqueue(MockResponse().setBody("""{"status":"ok","result":{"item_id":3,"status":"done"}}"""))
        server.enqueue(MockResponse().setBody("""{"status":"ok","result":{"item_id":3,"status":"filed"}}"""))
        api.markDone(3)
        api.reopen(3)
        assertEquals("/api/tools/mark_done", server.takeRequest().path)
        assertEquals("/api/tools/reopen", server.takeRequest().path)
    }

    @Test
    fun `the voice assistant's tool answer is the gateway's own text`() = runTest {
        server.enqueue(MockResponse().setBody("""{"status":"ok","result":[]}"""))
        val text = api.toolText("due_this_week", kotlinx.serialization.json.JsonObject(emptyMap()))
        assertEquals("""{"status":"ok","result":[]}""", text)
        server.enqueue(MockResponse().setResponseCode(403).setBody("""{"detail":"send_email is not allowed"}"""))
        try {
            api.toolText("send_email", kotlinx.serialization.json.JsonObject(emptyMap()))
            fail("expected a refusal")
        } catch (e: ApiException) {
            assertEquals("send_email is not allowed", e.detail)
        }
    }

    @Test
    fun `check now's cooldown arrives as the server's words`() = runTest {
        server.enqueue(MockResponse().setResponseCode(429).setBody("""{"detail":"Checked a moment ago: try again in a few minutes."}"""))
        try {
            api.checkMail()
            fail("expected the cooldown")
        } catch (e: ApiException) {
            assertEquals(429, e.status)
            assertEquals("Checked a moment ago: try again in a few minutes.", e.detail)
        }
    }

    @Test
    fun `the briefing's audio is bytes and its absence a reason`() = runTest {
        server.enqueue(MockResponse().setBody(okio.Buffer().write(byteArrayOf(73, 68, 51))))
        assertEquals(3, api.briefingAudio().size)
        server.enqueue(MockResponse().setResponseCode(503).setBody("""{"detail":"no ElevenLabs key: the phone reads it instead"}"""))
        try {
            api.briefingAudio()
            fail("expected 503")
        } catch (e: ApiException) {
            assertEquals(503, e.status)
        }
    }

    @Test
    fun `a refused approval carries the gateway's own reason`() = runTest {
        server.enqueue(MockResponse().setResponseCode(403).setBody("""{"detail":"approval already used"}"""))
        try {
            api.approve("tok")
            fail("expected a refusal")
        } catch (e: ApiException) {
            assertEquals(403, e.status)
            assertEquals("approval already used", e.detail)
        }
        assertEquals("""{"token":"tok"}""", server.takeRequest().body.readUtf8())
    }

    @Test
    fun `an unreachable server says which host`() = runTest {
        val dead = CoreApi(Http("t")) { "http://127.0.0.1:9" }
        try {
            dead.cards()
            fail("expected a failure")
        } catch (e: ApiException) {
            assertEquals(0, e.status)
            assertTrue(e.detail, e.detail.contains("127.0.0.1:9"))
        }
    }

    @Test
    fun `one laptop IP fills in all three servers`() {
        val c = ServerConfig.forHost(" http://192.168.1.20:8000/ ")
        assertEquals("http://192.168.1.20:8000", c.coreUrl)
        assertEquals("http://192.168.1.20:8002", c.portmaxUrl)
        assertEquals("http://192.168.1.20:8765", c.portalUrl)
    }

    @Test
    fun `an online address serves everything from one place`() {
        val c = ServerConfig.parse("7even5ive.onrender.com/")
        assertEquals("https://7even5ive.onrender.com", c.coreUrl)
        assertEquals(c.coreUrl, c.portmaxUrl)
        assertEquals(c.coreUrl, c.portalUrl)
        assertTrue(c.isOnline)
        assertEquals(c, ServerConfig.parse("https://7even5ive.onrender.com"))
    }

    @Test
    fun `a laptop IP still means the three local ports`() {
        val c = ServerConfig.parse("10.72.161.15")
        assertEquals("http://10.72.161.15:8000", c.coreUrl)
        assertEquals("http://10.72.161.15:8765", c.portalUrl)
        assertTrue(!c.isOnline)
        assertEquals(c, ServerConfig.parse("http://10.72.161.15:8000"))
    }

    @Test
    fun `a server's own HTTP address without a port is one address too`() {
        val c = ServerConfig.parse("http://13.233.1.2")
        assertEquals("http://13.233.1.2", c.portalUrl)
        assertTrue(c.isOnline)
    }

    @Test
    fun `the demo tour's forward reads the card it became`() = runTest {
        server.enqueue(MockResponse().setBody(
            """{"kind":"quiz","webhook_status":200,"webhook_reply":{"ok":true},
               "filed":{"id":9,"kind":"exam","title":"DAA Quiz 2 (greedy + DP)","route":"bot"}}"""
        ))
        val out = api.demoForward("quiz")
        assertEquals(200, out.webhookStatus)
        assertEquals("bot", out.filed?.route)
        val request = server.takeRequest()
        assertEquals("/demo/forward/quiz", request.path)
        assertEquals("POST", request.method)
        assertEquals("Bearer demo-student-token", request.getHeader("Authorization"))
    }

    @Test
    fun `a call with no token reports the gateway's refusal`() = runTest {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"unknown caller"}"""))
        assertEquals(401, api.statusWithoutToken())
        assertEquals(null, server.takeRequest().getHeader("Authorization"))
    }
}
