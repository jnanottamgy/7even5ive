package com.sevenfive.app

import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.BAD_ANSWER
import com.sevenfive.app.data.BUSY_TRY_AGAIN
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.FixedToken
import com.sevenfive.app.data.Http
import com.sevenfive.app.data.Retry
import com.sevenfive.app.data.ServerConfig
import com.sevenfive.app.data.library
import com.sevenfive.app.ui.screens.claudeCodeCommand
import com.sevenfive.app.ui.screens.codexCommand
import com.sevenfive.app.ui.screens.connectionDetail
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.time.ZoneId
import kotlin.random.Random

class CoreApiTest {
    private lateinit var server: MockWebServer
    private lateinit var api: CoreApi
    /** The waits between tries, recorded instead of waited. */
    private val waits = mutableListOf<Long>()

    @Before
    fun start() {
        server = MockWebServer()
        server.start()
        val base = server.url("/").toString().trimEnd('/')
        api = CoreApi(Http(FixedToken("demo-student-token"), pause = { waits += it })) { base }
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
        // A 503 is asked again twice (it may be a busy server); the reason comes through after.
        repeat(3) {
            server.enqueue(MockResponse().setResponseCode(503).setBody("""{"detail":"no ElevenLabs key: the phone reads it instead"}"""))
        }
        try {
            api.briefingAudio()
            fail("expected 503")
        } catch (e: ApiException) {
            assertEquals(503, e.status)
            assertEquals("no ElevenLabs key: the phone reads it instead", e.detail)
        }
        assertEquals(4, server.requestCount)
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
        val dead = CoreApi(Http(FixedToken("t"))) { "http://127.0.0.1:9" }
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

    // --- a busy or failing server -------------------------------------------------------------------
    @Test
    fun `a read meets a busy server, waits a little and asks again`() = runTest {
        server.enqueue(MockResponse().setResponseCode(503).setBody("""{"message":"Service Unavailable"}"""))
        server.enqueue(MockResponse().setResponseCode(429).setBody("""{"message":"Too Many Requests"}"""))
        server.enqueue(MockResponse().setBody("""{"filtered":3}"""))
        assertEquals(3, api.cards().filtered)
        assertEquals(3, server.requestCount)
        assertEquals(2, waits.size)
        assertTrue("about half a second: ${waits[0]}", waits[0] in 375L..625L)
        assertTrue("then about a second and a half: ${waits[1]}", waits[1] in 1_125L..1_875L)
    }

    @Test
    fun `after two retries a 5xx without words is a friendly sentence, never HTTP 502`() = runTest {
        repeat(3) { server.enqueue(MockResponse().setResponseCode(502).setBody("""{"message":"Internal server error"}""")) }
        try {
            api.settings()
            fail("expected the gateway's 502")
        } catch (e: ApiException) {
            assertEquals(502, e.status)
            assertEquals(BUSY_TRY_AGAIN, e.detail)
            assertTrue(e.busy)
        }
        assertEquals(3, server.requestCount)
    }

    @Test
    fun `a change is never sent twice when the server failed on it`() = runTest {
        server.enqueue(MockResponse().setResponseCode(500).setBody("Internal Server Error"))
        try {
            api.approve("tok")
            fail("expected the 500")
        } catch (e: ApiException) {
            assertEquals(500, e.status)
            assertEquals(BUSY_TRY_AGAIN, e.detail)
        }
        assertEquals(1, server.requestCount)
        assertTrue(waits.isEmpty())
    }

    @Test
    fun `a change is not sent again once it may have reached the server`() = runTest {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
        try {
            api.markDone(3)
            fail("expected the dropped connection")
        } catch (e: ApiException) {
            assertEquals(0, e.status)
        }
        assertEquals(1, server.requestCount)
        assertTrue(waits.isEmpty())
    }

    @Test
    fun `a read is asked again after a dropped connection`() = runTest {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AFTER_REQUEST))
        server.enqueue(MockResponse().setBody("""{"filtered":1}"""))
        assertEquals(1, api.cards().filtered)
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `a change that never left the phone is sent again`() = runTest {
        val dead = CoreApi(Http(FixedToken("t"), pause = { waits += it })) { "http://127.0.0.1:9" }
        try {
            dead.approve("tok")
            fail("expected a failure")
        } catch (e: ApiException) {
            assertEquals(0, e.status)
        }
        assertEquals(2, waits.size) // refused before anything was sent: safe to try again
    }

    @Test
    fun `Retry-After is honoured, and a long one means no retry now`() = runTest {
        server.enqueue(MockResponse().setResponseCode(503).setHeader("Retry-After", "2"))
        server.enqueue(MockResponse().setBody("{}"))
        api.cards()
        assertEquals(listOf(2_000L), waits)
        server.enqueue(MockResponse().setResponseCode(429).setHeader("Retry-After", "120").setBody("""{"message":"slow down"}"""))
        try {
            api.cards()
            fail("expected the 429")
        } catch (e: ApiException) {
            assertEquals(429, e.status)
        }
        assertEquals(3, server.requestCount)
        assertEquals(1, waits.size)
    }

    @Test
    fun `a refusal with only API Gateway's message says that message`() = runTest {
        server.enqueue(MockResponse().setResponseCode(403).setBody("""{"message":"Missing Authentication Token"}"""))
        try {
            api.settings()
            fail("expected the 403")
        } catch (e: ApiException) {
            assertEquals(403, e.status)
            assertEquals("Missing Authentication Token", e.detail)
            assertFalse(e.busy)
        }
        assertEquals(1, server.requestCount)
    }

    @Test
    fun `an answer the app can't read is a failure like any other, never a crash`() = runTest {
        server.enqueue(MockResponse().setBody("<html>Sign in to the Wi-Fi</html>"))
        try {
            api.cards()
            fail("expected an unreadable answer")
        } catch (e: ApiException) {
            assertEquals(BAD_ANSWER, e.code)
        }
        server.enqueue(MockResponse().setBody("""{"status":"ok","result":{"subjects":"not a list"}}"""))
        try {
            api.library()
            fail("expected an unreadable result")
        } catch (e: ApiException) {
            assertEquals(BAD_ANSWER, e.code)
        }
    }

    @Test
    fun `the retry rules`() {
        val r = Random(7)
        assertEquals(null, Retry.wait(1, idempotent = true, status = 404, sent = true, retryAfterMillis = null, random = r))
        assertEquals(null, Retry.wait(1, idempotent = false, status = 503, sent = true, retryAfterMillis = null, random = r))
        assertEquals(null, Retry.wait(1, idempotent = false, status = 0, sent = true, retryAfterMillis = null, random = r))
        assertTrue(Retry.wait(1, idempotent = false, status = 0, sent = false, retryAfterMillis = null, random = r) != null)
        assertTrue(Retry.wait(2, idempotent = true, status = 504, sent = true, retryAfterMillis = null, random = r) != null)
        assertEquals(null, Retry.wait(3, idempotent = true, status = 504, sent = true, retryAfterMillis = null, random = r))
        assertEquals(3_000L, Retry.wait(1, idempotent = true, status = 429, sent = true, retryAfterMillis = 3_000L, random = r))
        assertEquals(null, Retry.wait(1, idempotent = true, status = 429, sent = true, retryAfterMillis = 3_001L, random = r))
        assertEquals(5_000L, Retry.afterMillis("5"))
        assertEquals(10_000L, Retry.afterMillis("Wed, 21 Oct 2015 07:28:10 GMT", now = 1_445_412_480_000L))
        assertEquals(null, Retry.afterMillis("soon"))
        assertEquals(null, Retry.afterMillis(null))
    }

    // --- AI apps connected with OAuth ------------------------------------------------------------
    @Test
    fun `the connected apps read, with a name or a last use missing`() = runTest {
        server.enqueue(MockResponse().setBody(
            """{"mcp_url":"https://x.example/mcp","connections":[
               {"id":12,"name":"Claude Code","connected_at":"2026-11-27T10:15+05:30","last_used_at":"2026-11-27T11:02+05:30"},
               {"id":13,"name":null,"connected_at":"2026-11-26T09:00+05:30","last_used_at":null}]}"""
        ))
        val out = api.connections()
        assertEquals("https://x.example/mcp", out.mcpUrl)
        assertEquals(listOf(12, 13), out.connections.map { it.id })
        assertEquals("Claude Code", out.connections[0].label)
        assertNull(out.connections[1].name)
        assertEquals("An AI app", out.connections[1].label)
        assertNull(out.connections[1].lastUsedAt)
        val india = ZoneId.of("Asia/Kolkata")
        assertEquals("connected Fri 27 Nov, 10:15 AM · last used Fri 27 Nov, 11:02 AM", connectionDetail(out.connections[0], india))
        assertEquals("connected Thu 26 Nov, 9:00 AM · last used never", connectionDetail(out.connections[1], india))
        val request = server.takeRequest()
        assertEquals("GET", request.method)
        assertEquals("/api/me/connections", request.path)
        assertEquals("Bearer demo-student-token", request.getHeader("Authorization"))
    }

    @Test
    fun `the demo's list is empty`() = runTest {
        server.enqueue(MockResponse().setBody("""{"mcp_url":"https://x.example/mcp","connections":[]}"""))
        assertTrue(api.connections().connections.isEmpty())
    }

    @Test
    fun `disconnecting posts to that app's own address, and an unknown one says so`() = runTest {
        server.enqueue(MockResponse().setBody("""{"deleted":true}"""))
        assertTrue(api.disconnect(12))
        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/me/connections/12/delete", request.path)
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"detail":"That app isn't connected.","code":"not_found"}"""))
        try {
            api.disconnect(99)
            fail("expected not_found")
        } catch (e: ApiException) {
            assertEquals(404, e.status)
            assertEquals("not_found", e.code)
            assertEquals("That app isn't connected.", e.detail)
        }
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `the commands to paste on the computer`() {
        assertEquals("claude mcp add --transport http --scope user 7even5ive https://x.example/mcp",
            claudeCodeCommand("https://x.example/mcp"))
        assertEquals("codex mcp add 7even5ive --url https://x.example/mcp", codexCommand("https://x.example/mcp"))
    }
}
