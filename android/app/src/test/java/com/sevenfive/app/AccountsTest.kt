package com.sevenfive.app

import com.sevenfive.app.data.AccountState
import com.sevenfive.app.data.Accounts
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.AuthConfig
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.Http
import com.sevenfive.app.data.Saved
import com.sevenfive.app.data.SavedAccount
import com.sevenfive.app.data.Session
import com.sevenfive.app.data.SignUpResult
import com.sevenfive.app.data.SupabaseAuth
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.Dispatcher
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicInteger

/** Signing up, in and out, and staying signed in: Supabase and our server, both on one fake. */
class AccountsTest {
    private lateinit var server: MockWebServer
    private lateinit var base: String
    private lateinit var accounts: Accounts
    private val store = MemoryStore()
    private var now = 1_000_000L
    private val refreshes = AtomicInteger()
    private val seen = CopyOnWriteArrayList<RecordedRequest>()

    /** What the fake answers, changed per test. */
    private var refreshAnswer: () -> MockResponse = { tokens("access-2", "refresh-2") }
    private var meAnswer: () -> MockResponse = { MockResponse().setBody(ME_READY) }
    private var signupAnswer: () -> MockResponse = {
        MockResponse().setBody("""{"id":"u-1","email":"asha@example.com","identities":[{"id":"i1","provider":"email"}]}""")
    }

    private fun tokens(access: String, refresh: String, user: String = "u-1") = MockResponse().setBody(
        """{"access_token":"$access","refresh_token":"$refresh","expires_in":3600,"expires_at":${now + 3600},
           "token_type":"bearer","user":{"id":"$user","email":"asha@example.com"}}""",
    )

    @Before
    fun start() {
        server = MockWebServer()
        server.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                seen += request
                val path = request.path.orEmpty()
                return when {
                    path == "/api/auth/config" -> MockResponse().setBody(
                        """{"enabled":true,"supabase_url":"$base","publishable_key":"sb_publishable_x","username_login":true}""",
                    )
                    path.startsWith("/auth/v1/token?grant_type=refresh_token") -> {
                        refreshes.incrementAndGet()
                        Thread.sleep(50) // long enough for racing requests to queue up behind it
                        refreshAnswer()
                    }
                    path.startsWith("/auth/v1/token?grant_type=password") -> tokens("access-1", "refresh-1")
                    path == "/auth/v1/signup" -> signupAnswer()
                    path == "/auth/v1/verify" -> tokens("access-1", "refresh-1")
                    path.startsWith("/auth/v1/logout") -> MockResponse().setResponseCode(204)
                    path == "/api/auth/login" -> tokens("access-u", "refresh-u")
                    path == "/api/me" -> meAnswer()
                    path == "/api/cards" ->
                        if (request.getHeader("Authorization") == "Bearer access-2") MockResponse().setBody("{}")
                        else MockResponse().setResponseCode(401)
                            .setBody("""{"detail":"Your session expired. Sign in again.","code":"session_expired"}""")
                    else -> MockResponse().setResponseCode(404)
                }
            }
        }
        server.start()
        base = server.url("/").toString().trimEnd('/')
        accounts = Accounts(store, SupabaseAuth(OkHttpClient()) { now }, "demo-student-token") { now }
        accounts.core = CoreApi(Http(accounts)) { base }
    }

    @After
    fun stop() = server.shutdown()

    private fun session(expiresIn: Long = 3600) =
        Session("access-1", "refresh-1", now + expiresIn, "u-1", "asha@example.com", base, "sb_publishable_x")

    private fun requests(prefix: String) = seen.filter { it.path.orEmpty().startsWith(prefix) }

    @Test
    fun `signing up sends a code, and the code signs in and asks for the profile`() = runTest {
        meAnswer = { MockResponse().setBody("""{"onboarded":false,"email":"asha@example.com"}""") }
        accounts.start()
        accounts.loadConfig()
        val result = accounts.signUp(" Asha@Example.com ", "correct horse")
        assertEquals(SignUpResult.CodeSent("asha@example.com"), result)
        val signup = requests("/auth/v1/signup").single()
        assertEquals("sb_publishable_x", signup.getHeader("apikey"))
        assertNull(signup.getHeader("Authorization"))
        assertEquals("""{"email":"asha@example.com","password":"correct horse"}""", signup.body.readUtf8())

        accounts.verifySignUp("asha@example.com", "123456")
        assertEquals("""{"type":"signup","email":"asha@example.com","token":"123456"}""",
            requests("/auth/v1/verify").single().body.readUtf8())
        assertEquals(AccountState.NeedsProfile("asha@example.com"), accounts.state.value)
        assertEquals("Bearer access-1", requests("/api/me").single().getHeader("Authorization"))
        assertTrue(store.saved is Saved.Account)
    }

    @Test
    fun `an address that already has an account is told so, and nothing is saved`() = runTest {
        signupAnswer = { MockResponse().setBody("""{"id":"x","email":"asha@example.com","identities":[]}""") }
        accounts.start()
        accounts.loadConfig()
        try {
            accounts.signUp("asha@example.com", "correct horse")
            fail("an existing address must not look like a new sign-up")
        } catch (e: ApiException) {
            assertEquals("user_already_exists", e.code)
        }
        assertEquals(Saved.Nobody, store.saved)
    }

    @Test
    fun `an email logs in with Supabase and a username through the server`() = runTest {
        accounts.start()
        accounts.loadConfig()
        accounts.signIn("asha@example.com", "pw")
        assertEquals(1, requests("/auth/v1/token?grant_type=password").size)
        assertTrue(accounts.state.value is AccountState.Ready)
        accounts.signOut()
        accounts.signIn("@asha.k", "pw")
        val viaServer = requests("/api/auth/login").single()
        assertEquals("""{"login":"asha.k","password":"pw"}""", viaServer.body.readUtf8())
        assertNull(viaServer.getHeader("Authorization"))
        assertEquals("access-u", accounts.session?.accessToken)
    }

    @Test
    fun `a token about to expire is refreshed once however many requests ask at once`() = runTest {
        store.saved = Saved.Account(session(expiresIn = 30))
        accounts.start()
        val tokens = coroutineScope { (1..6).map { async { accounts.token() } }.awaitAll() }
        assertEquals(List(6) { "access-2" }, tokens)
        assertEquals(1, refreshes.get())
        val refresh = requests("/auth/v1/token?grant_type=refresh_token").single()
        assertEquals("""{"refresh_token":"refresh-1"}""", refresh.body.readUtf8())
        assertEquals("refresh-2", (store.saved as Saved.Account).session.refreshToken) // the rotated one is kept
    }

    @Test
    fun `the server saying the session ended refreshes once and sends the request again`() = runTest {
        store.saved = Saved.Account(session())
        accounts.start()
        accounts.core.cards()
        val cards = requests("/api/cards")
        assertEquals(listOf("Bearer access-1", "Bearer access-2"), cards.map { it.getHeader("Authorization") })
        assertEquals(1, refreshes.get())
    }

    @Test
    fun `a refresh Supabase refuses signs out, one that can't get through keeps the session`() = runTest {
        refreshAnswer = { MockResponse().setResponseCode(503) }
        store.saved = Saved.Account(session(expiresIn = 10))
        accounts.start()
        assertEquals("access-1", accounts.token()) // offline or busy: never signed out for it
        assertTrue(accounts.state.value !is AccountState.SignedOut)

        refreshAnswer = {
            MockResponse().setResponseCode(400)
                .setBody("""{"error_code":"refresh_token_not_found","msg":"Invalid Refresh Token"}""")
        }
        assertNull(accounts.token())
        assertEquals(AccountState.SignedOut("Your session ended. Log in again."), accounts.state.value)
        assertEquals(Saved.Nobody, store.saved)
        assertTrue(requests("/auth/v1/logout").isEmpty()) // nothing more is sent with a dead session
    }

    @Test
    fun `profile_required from the server sends the student to set it up`() = runTest {
        store.saved = Saved.Account(session(), me = null)
        accounts.start()
        assertTrue(accounts.state.value is AccountState.Checking)
        meAnswer = {
            MockResponse().setResponseCode(403)
                .setBody("""{"detail":"Finish setting up your account first.","code":"profile_required"}""")
        }
        accounts.refreshMe()
        assertEquals(AccountState.NeedsProfile("asha@example.com"), accounts.state.value)
    }

    @Test
    fun `the demo uses its public token, and leaving it signs out`() = runTest {
        accounts.start()
        assertNull(accounts.token())
        accounts.useDemo()
        assertEquals("demo-student-token", accounts.token())
        assertEquals(AccountState.Demo, accounts.state.value)
        assertEquals(Saved.Demo, store.saved)
        accounts.signOut()
        assertNull(accounts.token())
        assertEquals(Saved.Nobody, store.saved)
    }

    @Test
    fun `logging out ends the session at Supabase and forgets the person here`() = runTest {
        store.saved = Saved.Account(session())
        accounts.start()
        val left = mutableListOf<Saved>()
        accounts.onSwitch = { left += it }
        accounts.signOut()
        val logout = requests("/auth/v1/logout").single()
        assertEquals("Bearer access-1", logout.getHeader("Authorization"))
        assertEquals(listOf<Saved>(Saved.Account(session())), left)
        assertEquals(AccountState.SignedOut(null), accounts.state.value)
    }

    @Test
    fun `nothing is sent without someone signed in`() = runTest {
        accounts.start()
        try {
            accounts.core.cards()
            fail("signed out: no request")
        } catch (e: ApiException) {
            assertEquals("signed_out", e.code)
        }
        assertTrue(requests("/api/cards").isEmpty())
    }

    @Test
    fun `Supabase's refusals are said plainly`() {
        assertEquals("Wrong email or password.",
            SupabaseAuth.problem(400, """{"error_code":"invalid_credentials","msg":"Invalid login credentials"}""").detail)
        assertEquals("That code is wrong or has expired. Send a new one.",
            SupabaseAuth.problem(403, """{"error_code":"otp_expired"}""").detail)
        assertEquals("Too many tries. Wait a minute, then try again.", SupabaseAuth.problem(429, "").detail)
        assertTrue(SupabaseAuth.ended(SupabaseAuth.problem(400, """{"error_code":"refresh_token_already_used"}""")))
        assertTrue(!SupabaseAuth.ended(SupabaseAuth.problem(429, """{"error_code":"over_request_rate_limit"}""")))
        assertTrue(!SupabaseAuth.ended(ApiException(0, "offline")))
    }

    @Test
    fun `a config without a key offers only the demo`() {
        assertTrue(!AuthConfig(enabled = true, supabaseUrl = "https://x.supabase.co").usable)
        assertTrue(AuthConfig(enabled = true, supabaseUrl = "https://x.supabase.co", publishableKey = "k").usable)
    }

    private class MemoryStore : SavedAccount {
        var saved: Saved = Saved.Nobody
        override fun load(): Saved = saved
        override fun save(saved: Saved) {
            this.saved = saved
        }
    }

    private companion object {
        const val ME_READY = """{"onboarded":true,"email":"asha@example.com","profile":{"username":"asha.k","name":"Asha K"}}"""
    }
}
