package com.sevenfive.app

import com.sevenfive.app.data.CardsRepository
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.FixedToken
import com.sevenfive.app.data.Http
import com.sevenfive.app.data.Reminder
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Before
import org.junit.Test

/**
 * What a tap shows before the server has it (CardsRepository's overlay): at once, through polls
 * that haven't seen it yet, taken back when refused, and handed over to the server's own cards
 * once an answer has seen it.
 */
class CardsOverlayTest {
    private lateinit var server: MockWebServer
    private lateinit var repo: CardsRepository

    @Before
    fun start() {
        server = MockWebServer()
        server.start()
        val base = server.url("/").toString().trimEnd('/')
        repo = CardsRepository(CoreApi(Http(FixedToken("t"), pause = {})) { base })
    }

    @After
    fun stop() = server.shutdown()

    private fun answer(vararg ids: Int, reminders: String = "[]") = server.enqueue(MockResponse().setBody(
        """{"due_this_week":[${ids.joinToString { """{"id":$it,"kind":"deadline","title":"T$it","due_at":"2030-01-0${it}T10:00+05:30"}""" }}],"reminders":$reminders}""",
    ))

    private fun shown() = repo.state.value.cards!!.dueThisWeek.map { it.id }
    private fun item(id: Int) = repo.state.value.cards!!.dueThisWeek.first { it.id == id }

    @Test
    fun `Done hides at once and through polls that haven't seen it, then the server's cards take over`() = runTest {
        answer(1, 2, 3)
        repo.refresh()
        val change = repo.showDone(item(2), done = true)
        assertEquals(listOf(1, 3), shown())

        answer(1, 2, 3) // a poll asked for before the server took it
        repo.refresh()
        assertEquals(listOf(1, 3), shown())

        repo.confirm(change)
        answer(1, 3) // the first answer asked for after it
        repo.refresh()
        assertEquals(listOf(1, 3), shown())

        answer(1, 2, 3) // back on the server's list (reopened elsewhere): the server's word now
        repo.refresh()
        assertEquals(listOf(1, 2, 3), shown())
    }

    @Test
    fun `a change the server refuses is taken back at once`() = runTest {
        answer(1, 2, 3)
        repo.refresh()
        val change = repo.showDone(item(2), done = true)
        repo.takeBack(change)
        assertEquals(listOf(1, 2, 3), shown())
    }

    @Test
    fun `Undo after the server has dropped it puts it back where it was`() = runTest {
        answer(1, 2, 3)
        repo.refresh()
        val two = item(2)
        repo.confirm(repo.showDone(two, done = true))
        answer(1, 3)
        repo.refresh()
        assertEquals(listOf(1, 3), shown())

        repo.showDone(two, done = false)
        assertEquals(listOf(1, 2, 3), shown())
    }

    @Test
    fun `a reminder cancelled before the server had it stays gone when it arrives with its own id`() = runTest {
        answer(1)
        repo.refresh()
        val provisional = Reminder(id = -1, firesAt = "2030-01-01T09:00+05:30", title = "T1", itemId = 1)
        repo.showReminder(provisional, added = true)
        assertEquals(listOf(-1), repo.state.value.cards!!.reminders.map { it.id })
        repo.showReminder(provisional, added = false)
        assertEquals(emptyList<Int>(), repo.state.value.cards!!.reminders.map { it.id })

        answer(1, reminders = """[{"reminder_id":7,"fires_at":"2030-01-01T09:00+05:30","item_id":1,"title":"T1"}]""")
        repo.refresh()
        assertEquals(emptyList<Int>(), repo.state.value.cards!!.reminders.map { it.id })
    }

    @Test
    fun `a done item's reminders leave with it`() = runTest {
        answer(1, 2, reminders = """[{"reminder_id":7,"fires_at":"2030-01-01T09:00+05:30","item_id":1,"title":"T1"}]""")
        repo.refresh()
        repo.showDone(item(1), done = true)
        assertEquals(emptyList<Int>(), repo.state.value.cards!!.reminders.map { it.id })
    }

    @Test
    fun `with nothing pending, screens get the server's very object`() = runTest {
        answer(1, 2)
        repo.refresh()
        val served = repo.state.value.cards
        repo.takeBack(repo.showDone(item(1), done = true))
        assertSame("nothing to recompose", served, repo.state.value.cards)
    }
}
