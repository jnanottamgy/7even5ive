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
        assertEquals("""{"args":{"item_id":1,"before_minutes":60}}""", request.body.readUtf8())
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
}
