package com.sevenfive.app

import com.sevenfive.app.data.AccountState
import com.sevenfive.app.data.Accounts
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.AuthConfig
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.Http
import com.sevenfive.app.data.ProfileForm
import com.sevenfive.app.data.Saved
import com.sevenfive.app.data.SavedAccount
import com.sevenfive.app.data.Session
import com.sevenfive.app.data.SignUpResult
import com.sevenfive.app.data.SupabaseAuth
import com.sevenfive.app.data.toJson
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
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
    private var coreBase = ""
    private lateinit var accounts: Accounts
    private val store = MemoryStore()
    private var now = 1_000_000L
    private val refreshes = AtomicInteger()
    private val seen = CopyOnWriteArrayList<RecordedRequest>()

    /** What the fake answers, changed per test. */
    @Volatile private var refreshDelay = 50L
    @Volatile private var refreshAnswer: () -> MockResponse = { tokens("access-2", "refresh-2") }
    @Volatile private var meAnswer: () -> MockResponse = { MockResponse().setBody(ME_READY) }
    @Volatile private var passwordUser = "u-1"
    @Volatile private var setPasswordAnswer: () -> MockResponse = { MockResponse().setBody("""{"id":"u-1"}""") }
    private var signupAnswer: () -> MockResponse = {
        MockResponse().setBody("""{"id":"u-1","email":"asha@example.com","identities":[{"id":"i1","provider":"email"}]}""")
    }

    private fun tokens(access: String, refresh: String, user: String = "u-1") = MockResponse().setBody(
        """{"access_token":"$access","refresh_token":"$refresh","expires_in":3600,"expires_at":${now + 3600},
           "token_type":"bearer","user":{"id":"$user","email":"${if (user == "u-1") "asha" else user}@example.com"}}""",
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
                        Thread.sleep(refreshDelay) // long enough for racing requests to queue up behind it
                        refreshAnswer()
                    }
                    path.startsWith("/auth/v1/token?grant_type=password") ->
                        tokens("access-$passwordUser", "refresh-$passwordUser", passwordUser)
                    path == "/auth/v1/signup" -> signupAnswer()
                    path == "/auth/v1/verify" -> tokens("access-1", "refresh-1")
                    path == "/auth/v1/user" -> setPasswordAnswer()
                    path.startsWith("/auth/v1/logout") -> MockResponse().setResponseCode(204)
                    path == "/api/auth/login" -> tokens("access-u", "refresh-u")
                    path == "/api/me" -> meAnswer()
                    path == "/api/devices/remove" -> MockResponse().setBody("""{"removed":true}""")
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
        coreBase = base
        accounts = Accounts(store, SupabaseAuth(OkHttpClient()) { now }, "demo-student-token", { now })
        accounts.core = CoreApi(Http(accounts)) { coreBase }
    }

    @After
    fun stop() = server.shutdown()

    private fun session(expiresIn: Long = 3600, user: String = "u-1", access: String = "access-1", refresh: String = "refresh-1") =
        Session(access, refresh, now + expiresIn, user, "asha@example.com", base, "sb_publishable_x")

    private fun requests(prefix: String) = seen.filter { it.path.orEmpty().startsWith(prefix) }

    private suspend fun waitFor(check: () -> Boolean) = withContext(Dispatchers.Default) {
        withTimeout(5_000) { while (!check()) delay(10) }
    }

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
        waitFor { (store.saved as? Saved.Account)?.session?.refreshToken == "refresh-2" } // the rotated one is kept
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
    fun `only Supabase's own session-over codes sign out`() = runTest {
        store.saved = Saved.Account(session(expiresIn = 10))
        accounts.start()
        for (answer in listOf(
            MockResponse().setResponseCode(503),
            MockResponse().setResponseCode(401).setBody("""{"message":"Invalid API key"}"""), // a rotated key
            MockResponse().setResponseCode(403).setBody("<html>edge</html>"),
        )) {
            refreshAnswer = { answer }
            assertEquals("access-1", accounts.token())
            assertTrue(accounts.state.value !is AccountState.SignedOut)
        }
        refreshAnswer = {
            MockResponse().setResponseCode(400)
                .setBody("""{"error_code":"refresh_token_not_found","msg":"Invalid Refresh Token"}""")
        }
        assertNull(accounts.token())
        assertEquals(AccountState.SignedOut("Your session ended. Log in again."), accounts.state.value)
        waitFor { store.saved == Saved.Nobody }
        assertTrue(requests("/auth/v1/logout").isEmpty()) // nothing more is sent with a dead session
    }

    @Test
    fun `logging out while a refresh is on the network never brings the session back`() = runTest {
        refreshDelay = 400
        store.saved = Saved.Account(session())
        accounts.start()
        // The server said the session ended: a refresh starts, and is slow.
        val pending = CoroutineScope(Dispatchers.Default).async { accounts.rejected("access-1", 401, "session_expired") }
        waitFor { refreshes.get() == 1 }
        accounts.signOut() // done before the refresh comes back
        assertEquals(AccountState.SignedOut(null), accounts.state.value)
        assertNull(pending.await()) // it came back for someone who had left: dropped
        assertEquals(AccountState.SignedOut(null), accounts.state.value)
        assertNull(accounts.token())
        delay(100)
        assertEquals(Saved.Nobody, store.saved)
    }

    @Test
    fun `logging out a session Supabase already ended never hangs, with a phone to unregister`() = runTest {
        refreshAnswer = {
            MockResponse().setResponseCode(400).setBody("""{"error_code":"session_not_found"}""")
        }
        store.saved = Saved.Account(session(expiresIn = 10))
        accounts.start()
        accounts.onSwitch = { _, token -> if (token != null) accounts.core.removeDeviceAs(token, "phone-1") }
        withContext(Dispatchers.Default) {
            withTimeout(5_000) {
                accounts.signOut()
                accounts.useDemo()
            }
        }
        assertEquals(AccountState.Demo, accounts.state.value)
        assertTrue(requests("/api/devices/remove").isEmpty()) // no live token for the ended session
    }

    @Test
    fun `the phone is unregistered with the leaving student's own token`() = runTest {
        store.saved = Saved.Account(session())
        accounts.start()
        accounts.onSwitch = { _, token -> if (token != null) accounts.core.removeDeviceAs(token, "phone-1") }
        accounts.signOut()
        val remove = requests("/api/devices/remove").single()
        assertEquals("Bearer access-1", remove.getHeader("Authorization"))
        assertEquals("Bearer access-1", requests("/auth/v1/logout").single().getHeader("Authorization"))
    }

    @Test
    fun `logging out just before the token ends refreshes it so Supabase really ends the session`() = runTest {
        store.saved = Saved.Account(session(expiresIn = 20))
        accounts.start()
        accounts.signOut()
        assertEquals("Bearer access-2", requests("/auth/v1/logout").single().getHeader("Authorization"))
    }

    @Test
    fun `an answer meant for the last student never touches the next`() = runTest {
        store.saved = Saved.Account(session())
        accounts.start()
        accounts.loadConfig()
        val theirs = accounts.token()!!
        accounts.signOut()
        passwordUser = "u-2"
        accounts.signIn("ravi@example.com", "pw")
        assertTrue(accounts.state.value is AccountState.Ready)
        assertNull(accounts.rejected(theirs, 403, "profile_required"))
        assertNull(accounts.rejected(theirs, 401, "session_expired"))
        assertTrue(accounts.state.value is AccountState.Ready)
        assertEquals("access-u-2", accounts.token())
        assertEquals(0, refreshes.get())
    }

    @Test
    fun `a new reset code is checked again after a refused password`() = runTest {
        accounts.start()
        accounts.loadConfig()
        setPasswordAnswer = { MockResponse().setResponseCode(422).setBody("""{"error_code":"weak_password"}""") }
        try {
            accounts.resetPassword("asha@example.com", "111111", "short")
            fail("a weak password is refused")
        } catch (e: ApiException) {
            assertEquals("weak_password", e.code)
        }
        setPasswordAnswer = { MockResponse().setResponseCode(401).setBody("""{"error_code":"bad_jwt"}""") }
        try {
            accounts.resetPassword("asha@example.com", "111111", "long enough now")
            fail("an expired recovery session is refused")
        } catch (e: ApiException) {
            assertEquals(401, e.status)
        }
        assertEquals(1, requests("/auth/v1/verify").size) // the same code: no second check
        setPasswordAnswer = { MockResponse().setBody("""{"id":"u-1"}""") }
        accounts.resetPassword("asha@example.com", "222222", "long enough now")
        assertEquals(2, requests("/auth/v1/verify").size) // the new code was checked
        assertTrue(accounts.state.value is AccountState.Ready)
    }

    @Test
    fun `a sign-in whose screen went away still finishes`() = runTest {
        accounts.start()
        accounts.loadConfig()
        val arrived = AtomicInteger()
        accounts.onArrive = { arrived.incrementAndGet() }
        meAnswer = { Thread.sleep(300); MockResponse().setBody(ME_READY) }
        val screen = CoroutineScope(Dispatchers.Default)
        screen.launch { accounts.signIn("asha@example.com", "pw") }
        waitFor { requests("/api/me").isNotEmpty() }
        screen.coroutineContext[kotlinx.coroutines.Job]!!.cancel()
        assertTrue(accounts.state.value is AccountState.Checking) // never "signed out" with a session behind it
        waitFor { accounts.state.value is AccountState.Ready }
        waitFor { arrived.get() == 1 }
    }

    @Test
    fun `finishing the profile registers the phone for the new student`() = runTest {
        meAnswer = { MockResponse().setBody("""{"onboarded":false,"email":"asha@example.com"}""") }
        accounts.start()
        accounts.loadConfig()
        val arrived = AtomicInteger()
        accounts.onArrive = { arrived.incrementAndGet() }
        accounts.verifySignUp("asha@example.com", "123456")
        assertEquals(0, arrived.get()) // no profile yet: the server would refuse the phone
        meAnswer = { MockResponse().setBody(ME_READY) }
        accounts.saveProfile(ProfileForm(username = "asha.k", name = "Asha K"))
        assertTrue(accounts.state.value is AccountState.Ready)
        waitFor { arrived.get() == 1 }
    }

    @Test
    fun `another server's sign-in settings are never used`() = runTest {
        accounts.start()
        assertEquals(base, accounts.loadConfig()?.supabaseUrl)
        coreBase = "http://127.0.0.1:9" // a laptop that isn't answering
        assertNull(accounts.loadConfig())
        try {
            accounts.signIn("asha@example.com", "pw")
            fail("no sign-in without this server's own settings")
        } catch (e: ApiException) {
            assertEquals(0, e.status)
        }
        assertTrue(requests("/auth/v1/token").isEmpty())
    }

    @Test
    fun `a server from before accounts still offers the demo`() = runTest {
        accounts.start()
        coreBase = "$base/older" // answers 404 to /api/auth/config, as servers before accounts do
        val config = accounts.loadConfig()
        assertTrue(config != null && !config.usable && config.demo)
        accounts.useDemo()
        assertEquals("demo-student-token", accounts.token())
    }

    @Test
    fun `profile_required from the server sends the student to set it up`() = runTest {
        store.saved = Saved.Account(session(), me = null)
        meAnswer = {
            MockResponse().setResponseCode(403)
                .setBody("""{"detail":"Finish setting up your account first.","code":"profile_required"}""")
        }
        accounts.start()
        waitFor { accounts.state.value is AccountState.NeedsProfile }
        assertEquals(AccountState.NeedsProfile("asha@example.com"), accounts.state.value)
    }

    @Test
    fun `a deleted account's session is signed out`() = runTest {
        store.saved = Saved.Account(session())
        accounts.start()
        val token = accounts.token()!!
        assertNull(accounts.rejected(token, 401, "account_deleted"))
        assertEquals(AccountState.SignedOut("This account was deleted."), accounts.state.value)
    }

    @Test
    fun `the demo uses its public token, and leaving it signs out`() = runTest {
        accounts.start()
        assertNull(accounts.token())
        accounts.useDemo()
        assertEquals("demo-student-token", accounts.token())
        assertEquals(AccountState.Demo, accounts.state.value)
        waitFor { store.saved == Saved.Demo }
        accounts.signOut()
        assertNull(accounts.token())
        waitFor { store.saved == Saved.Nobody }
    }

    @Test
    fun `logging out ends the session at Supabase and forgets the person here`() = runTest {
        store.saved = Saved.Account(session())
        accounts.start()
        val left = mutableListOf<Saved>()
        accounts.onSwitch = { leaving, _ -> left += leaving }
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
        assertTrue(SupabaseAuth.ended(SupabaseAuth.problem(400, """{"error":"invalid_grant"}""")))
        assertTrue(!SupabaseAuth.ended(SupabaseAuth.problem(429, """{"error_code":"over_request_rate_limit"}""")))
        assertTrue(!SupabaseAuth.ended(SupabaseAuth.problem(401, """{"message":"Invalid API key"}""")))
        assertTrue(!SupabaseAuth.ended(ApiException(0, "offline")))
    }

    @Test
    fun `the profile form can clear the year`() {
        assertEquals("""{"name":"A","year":null}""", ProfileForm(name = "A", sendYear = true).toJson().toString())
        assertEquals("""{"name":"A"}""", ProfileForm(name = "A").toJson().toString())
    }

    @Test
    fun `a config without a key offers only the demo`() {
        assertTrue(!AuthConfig(enabled = true, supabaseUrl = "https://x.supabase.co").usable)
        assertTrue(AuthConfig(enabled = true, supabaseUrl = "https://x.supabase.co", publishableKey = "k").usable)
    }

    private class MemoryStore : SavedAccount {
        @Volatile var saved: Saved = Saved.Nobody
        override fun load(): Saved = saved
        override fun save(saved: Saved) {
            this.saved = saved
        }
    }

    private companion object {
        const val ME_READY = """{"onboarded":true,"email":"asha@example.com","profile":{"username":"asha.k","name":"Asha K"}}"""
    }
}
