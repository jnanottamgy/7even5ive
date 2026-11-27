package com.sevenfive.app

import com.sevenfive.app.data.AppJson
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.CardsRepository
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.FixedToken
import com.sevenfive.app.data.Http
import com.sevenfive.app.notify.Alerts
import com.sevenfive.app.notify.ShownReminders
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File
import java.util.concurrent.TimeUnit

/** One reminder, one notification; and nothing of the last person's comes back after they leave. */
class NotifyRulesTest {
    private val day = 24 * 60 * 60 * 1000L

    @Test
    fun `the alarm and the outbox show one reminder once, whichever comes first`() {
        var log = ShownReminders()
        val (first, afterFirst) = log.claim(42, now = 1_000)
        assertTrue(first)
        log = afterFirst
        val (second, afterSecond) = log.claim(42, now = 2_000)
        assertFalse("the second way to deliver it stays quiet", second)
        // Another reminder, even for the same deadline, is its own.
        assertTrue(afterSecond.claim(43, now = 3_000).first)
    }

    @Test
    fun `a phone offline for days still recognises the reminder its alarm showed`() {
        val log = ShownReminders().claim(42, now = 0).second
        assertFalse(log.claim(42, now = 6 * day).first)
        // After a week the entry is gone, and the log stays small.
        assertTrue(log.claim(42, now = 8 * day).first)
        var big = ShownReminders()
        repeat(ShownReminders.MAX + 50) { big = big.claim(it, now = it.toLong()).second }
        assertEquals(ShownReminders.MAX, big.entries.size)
        assertEquals(ShownReminders.MAX + 49, big.entries.last().first)
    }

    @Test
    fun `the log survives being stored, and a damaged one starts empty`() {
        val log = ShownReminders().claim(7, now = 10).second.claim(8, now = 20).second
        assertEquals(log, ShownReminders.parse(log.encode()))
        assertEquals(ShownReminders(), ShownReminders.parse(null))
        assertEquals(listOf(9 to 30L), ShownReminders.parse("junk,9@30,@,x@1,5@").entries)
    }

    @Test
    fun `the morning digest says what is due and never an attendance figure`() {
        val cards = AppJson.decodeFromString(Cards.serializer(), """{
            "due_this_week":[{"id":1,"title":"DBMS Assignment 3","due_at":"2030-01-04T23:59+05:30"}],
            "attendance":{"connected":true,"subjects":[{"subject_code":"CS51","subject_name":"DBMS","percent":62.0,
              "status":"short"}]}}""")
        val (head, lines) = Alerts.digestOf(cards)
        assertEquals("1 thing due this week", head)
        assertTrue(lines.single().startsWith("DBMS Assignment 3"))
        assertFalse((listOf(head) + lines).any { "%" in it || "62" in it })
    }
}

class CardsRepositoryTest {
    private lateinit var server: MockWebServer
    private lateinit var api: CoreApi
    private lateinit var cache: File

    @Before
    fun start() {
        server = MockWebServer()
        server.start()
        val base = server.url("/").toString().trimEnd('/')
        api = CoreApi(Http(FixedToken("demo-student-token"), pause = {})) { base }
        cache = File.createTempFile("cards", ".json").also { it.delete() }
    }

    @After
    fun stop() {
        server.shutdown()
        cache.delete()
    }

    @Test
    fun `an answer that lands after the student left is dropped, not shown, kept or alarmed`() = runTest {
        val repo = CardsRepository(api, cache)
        var applied = 0
        var resets = 0
        repo.onCards = { applied++ }
        repo.onReset = { resets++ }
        server.enqueue(MockResponse().setBody("{}").setHeadersDelay(400, TimeUnit.MILLISECONDS))
        val poll = launch(Dispatchers.Default) { repo.refresh() }
        assertNotNull("the poll asked", server.takeRequest(5, TimeUnit.SECONDS))
        repo.reset() // they sign out while the answer is on its way
        poll.join()
        assertNull(repo.state.value.cards)
        assertEquals(0, applied)
        assertFalse(cache.exists())
        assertEquals(1, resets)

        // The next person's answers are applied as usual.
        server.enqueue(MockResponse().setBody("{}"))
        repo.refresh()
        assertNotNull(repo.state.value.cards)
        assertEquals(1, applied)
        assertTrue(cache.exists())
    }

    @Test
    fun `an answer this app can't read is a banner, not a crash`() = runTest {
        val repo = CardsRepository(api, cache)
        server.enqueue(MockResponse().setBody("""{"due_this_week": "not a list"}"""))
        repo.refresh()
        assertNull(repo.state.value.cards)
        assertNotNull(repo.state.value.error)
        assertFalse(cache.exists())
    }
}
