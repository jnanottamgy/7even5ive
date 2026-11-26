package com.sevenfive.app.data

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

/** Where the app is with the person using it; the screens follow this. */
sealed interface AccountState {
    /** Before the saved session has been read (a moment at start). */
    data object Starting : AccountState

    /** Signed in, but the profile hasn't been confirmed yet (no answer from the server). */
    data class Checking(val problem: String? = null) : AccountState

    data class SignedOut(val reason: String? = null) : AccountState

    /** Signed in at Supabase; the 7even5ive profile (username, college...) comes next. */
    data class NeedsProfile(val email: String?) : AccountState

    data class Ready(val me: Me) : AccountState

    data object Demo : AccountState

    /** The main app (cards, tabs) is for these two. */
    val usesApp: Boolean get() = this is Ready || this is Demo
}

/**
 * The token for every request, as the server asks for it ([Http] calls [token] and, when the
 * server refuses one, [rejected]). The demo has a fixed public token; an account, its Supabase
 * access token, refreshed shortly before it expires.
 */
interface TokenSource {
    /** The token for the next request, or null when no one is signed in (nothing is sent). */
    suspend fun token(): String?

    /** Our server refused [used] with [status] and [code]: a token to try once more, or null. */
    suspend fun rejected(used: String, status: Int, code: String?): String? = null
}

/** One fixed token (tests, and the one call made for someone leaving: [Accounts.onLeft]). */
class FixedToken(private val value: String) : TokenSource {
    override suspend fun token(): String = value
}

/**
 * Signing up, in and out, and staying signed in. Supabase Auth is called from the phone itself
 * ([SupabaseAuth]); our server checks each access token and keeps the profile.
 *
 * Refreshing: an access token lasts about an hour. It is swapped for a new one a minute before
 * it ends, and once more if the server says it has ended; one refresh at a time (Supabase rotates
 * refresh tokens). Only a refresh Supabase refuses with one of its "this session is over" codes
 * signs the student out; being offline, a busy Supabase or a changed key never does.
 *
 * Who is signed in changes only under [lock], and each change bumps [epoch]. Anything that
 * started for one person (a refresh, a request) and comes back after a change is dropped: a late
 * refresh can't bring back a session that was logged out, and a late answer meant for one student
 * is never applied to the next. A change of person ([adopt], [useDemo], [signOut]) runs to the
 * end even if the screen that asked is gone ([durable]), and the clean-up it runs ([onSwitch],
 * [onLeft]) never calls back into this class, so nothing here can wait on itself. What needs the
 * network for whoever left runs afterwards in the background ([leaveLater]): a slow network
 * never holds up the screen or the next person.
 */
class Accounts(
    private val store: SavedAccount,
    private val supabase: SupabaseAuth,
    private val demoToken: String,
    private val now: () -> Long = { System.currentTimeMillis() / 1000 },
    private val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Default),
    private val disk: kotlinx.coroutines.CoroutineDispatcher = Dispatchers.IO,
    /** Where the last sign-in settings are remembered across starts (null: nowhere). */
    private val configCache: ConfigCache? = null,
) : TokenSource {
    lateinit var core: CoreApi

    /**
     * Runs when the person using the app changes, after the new state is in place: clears what
     * belonged to [leaving] on this phone (cards, the portal login, notifications). Needs no
     * network.
     */
    var onSwitch: suspend (leaving: Saved) -> Unit = {}

    /**
     * Then, in the background and best effort, the one last call for whoever left: unregistering
     * this phone from their wake-ups on [server], the one they used. [token] is a live token of
     * theirs and must be used as it is (FixedToken), never through this class. Not called when
     * no live token could be had.
     */
    var onLeft: suspend (token: String, server: String) -> Unit = { _, _ -> }

    /** Runs when someone can use the app (an account with its profile, or the demo): registers
     * this phone for their wake-ups. */
    var onArrive: suspend () -> Unit = {}

    private val _state = MutableStateFlow<AccountState>(AccountState.Starting)
    val state: StateFlow<AccountState> = _state.asStateFlow()

    private val _config = MutableStateFlow<AuthConfig?>(null)
    val config: StateFlow<AuthConfig?> = _config.asStateFlow()
    @Volatile
    private var configFrom: String? = null

    private val lock = Any()
    private var saved: Saved = Saved.Nobody
    private var epoch = 0L
    /** The current session's earlier access tokens: answers to requests sent with them still
     * belong to this person. Cleared when the person changes. */
    private val earlier = ArrayDeque<String>()
    private val refreshing = Mutex()
    private val changing = Mutex()
    private var recovering: Pair<String, Session>? = null
    /** Done once [start] has read the saved session: a request made earlier (a wake-up that
     * started the process) waits for it a moment instead of going out as no one. */
    private val started = CompletableDeferred<Unit>()

    /**
     * Reads what this phone remembers. Called off the main thread: the Keystore is slow.
     * [movedFrom]: the server the app used before this build's own took over
     * (ServerSettings.movedFrom). An account belongs to the server it was made on, so it is
     * signed out (and its session ended); the demo moves along with the app.
     */
    fun start(movedFrom: String? = null) {
        var loaded = store.load()
        val stranded = if (movedFrom != null) loaded as? Saved.Account else null
        if (stranded != null) {
            loaded = Saved.Nobody
            try {
                store.save(Saved.Nobody)
            } catch (e: Exception) {
                // The store keeps the session in memory only (SessionStore says why).
            }
        }
        val cached = try {
            configCache?.load()
        } catch (e: Exception) {
            null
        }
        val checking = synchronized(lock) {
            if (cached != null && _config.value == null) {
                _config.value = cached.second
                configFrom = cached.first
            }
            saved = loaded
            _state.value = if (stranded != null) AccountState.SignedOut(MOVED) else stateOf(loaded)
            _state.value is AccountState.Checking
        }
        started.complete(Unit)
        if (stranded != null && movedFrom != null) {
            scope.launch { forgetHere(stranded) }
            leaveLater(stranded, movedFrom)
        }
        if (checking) scope.launch { refreshMe() }
        if (loaded == Saved.Demo || _state.value is AccountState.Ready) scope.launch { arrive() }
    }

    val session: Session? get() = synchronized(lock) { (saved as? Saved.Account)?.session }

    private fun stateOf(s: Saved): AccountState = when (s) {
        Saved.Nobody -> AccountState.SignedOut()
        Saved.Demo -> AccountState.Demo
        is Saved.Account -> when {
            s.me == null -> AccountState.Checking()
            s.me.onboarded -> AccountState.Ready(s.me)
            else -> AccountState.NeedsProfile(s.session.email)
        }
    }

    /** Writes whatever is current now, on the disk dispatcher: writes can't land out of order
     * (each one writes the latest state, whichever runs last). */
    private suspend fun persist() {
        withContext(disk) {
            val current = synchronized(lock) { saved }
            try {
                store.save(current)
            } catch (e: Exception) {
                // The store keeps the session in memory only (SessionStore says why).
            }
        }
    }

    /** Runs [block] to the end even if the caller is cancelled (the screen went away). */
    private suspend fun <T> durable(block: suspend () -> T): T = scope.async { block() }.await()

    private suspend fun arrive() {
        try {
            onArrive()
        } catch (e: Exception) {
            // Registered on the next start.
        }
    }

    // --- tokens ---------------------------------------------------------------------------------
    override suspend fun token(): String? {
        if (!started.isCompleted) withTimeoutOrNull(START_WAIT_MILLIS) { started.await() }
        val s = synchronized(lock) { saved }
        return when (s) {
            Saved.Nobody -> null
            Saved.Demo -> demoToken
            is Saved.Account ->
                if (s.session.expiresAt - now() > EARLY_SECONDS) s.session.accessToken
                else refreshed(s.session.accessToken, force = false)
        }
    }

    private fun owns(token: String): Boolean = synchronized(lock) {
        val s = saved as? Saved.Account ?: return false
        token == s.session.accessToken || token in earlier
    }

    override suspend fun rejected(used: String, status: Int, code: String?): String? {
        // A request sent for someone who has since logged out: nothing to do with the current one.
        if (!owns(used)) return null
        return when (code) {
            "profile_required" -> {
                markNeedsProfile()
                null
            }
            "session_expired" -> refreshed(used, force = true)
            "account_deleted" -> {
                val s = session ?: return null
                endSession(s.refreshToken, "This account was deleted.")
                null
            }
            else -> null
        }
    }

    /** A fresh access token, or null when the session is over (then signed out). */
    private suspend fun refreshed(used: String, force: Boolean): String? {
        var ended: Session? = null
        val token = refreshing.withLock {
            val (s, at) = synchronized(lock) { (saved as? Saved.Account) to epoch }
            if (s == null) return@withLock null
            // Another request refreshed while this one waited: its token, if it is this person's.
            if (s.session.accessToken != used) return@withLock if (owns(used)) s.session.accessToken else null
            if (!force && s.session.expiresAt - now() > EARLY_SECONDS) return@withLock s.session.accessToken
            try {
                val fresh = supabase.refresh(s.session.copy(key = keyFor(s.session)))
                val applied = synchronized(lock) {
                    val current = saved as? Saved.Account
                    if (epoch != at || current == null || current.session.refreshToken != s.session.refreshToken) {
                        false // logged out (or someone else came in) meanwhile: these tokens go nowhere
                    } else {
                        earlier.addLast(current.session.accessToken)
                        while (earlier.size > 4) earlier.removeFirst()
                        saved = current.copy(session = fresh)
                        true
                    }
                }
                if (!applied) return@withLock null
                persist()
                fresh.accessToken
            } catch (e: ApiException) {
                if (SupabaseAuth.ended(e)) {
                    ended = s.session
                    null
                } else {
                    // A 401 or 403 here can be a publishable key the project no longer accepts
                    // (rotated): this server's current settings are asked for, for the next try.
                    if (e.status == 401 || e.status == 403) scope.launch { runCatching { loadConfig() } }
                    s.session.accessToken // offline or Supabase busy: the server decides
                }
            }
        }
        ended?.let { endSession(it.refreshToken, "Your session ended. Log in again.") }
        return token
    }

    /** The session is over at Supabase (or deleted): forget it, if it is still the current one.
     * Nothing more is sent with it, so this never waits for anything but the disk. */
    private suspend fun endSession(refreshToken: String, reason: String) {
        val leaving = synchronized(lock) {
            val current = saved as? Saved.Account ?: return
            if (current.session.refreshToken != refreshToken) return
            saved = Saved.Nobody
            epoch++
            earlier.clear()
            _state.value = AccountState.SignedOut(reason)
            current
        }
        persist()
        forgetHere(leaving)
    }

    /** The publishable key to refresh with: the server's current one for this project (keys can
     * be rotated), else the one it was signed in with. */
    private fun keyFor(session: Session): String =
        _config.value?.takeIf { it.supabaseUrl?.trimEnd('/') == session.project }?.publishableKey ?: session.key

    /** A token good for one last call as [session] (ending it at Supabase, unregistering this
     * phone): refreshed first if it is about to expire. Null if that can't be done. */
    private suspend fun liveToken(session: Session): Session? {
        if (session.expiresAt - now() > EARLY_SECONDS) return session
        return try {
            supabase.refresh(session.copy(key = keyFor(session)))
        } catch (e: ApiException) {
            null
        }
    }

    // --- the server's sign-in settings -------------------------------------------------------------
    /** Asks the server how to sign in. If it can't be reached, the last answer is kept only if
     * it came from this same server: another server's Supabase project is never used. Each
     * answer is remembered ([configCache]) for the next start. */
    suspend fun loadConfig(): AuthConfig? {
        val from = core.baseUrl()
        val answer = try {
            core.authConfig()
        } catch (e: ApiException) {
            // A server from before accounts: it answers, it just has only the demo.
            if (e.status == 404) AuthConfig(enabled = false, demo = true) else null
        }
        synchronized(lock) {
            if (answer != null) {
                _config.value = answer
                configFrom = from
            } else if (configFrom != from) {
                _config.value = null
                configFrom = null
            }
        }
        if (answer != null) {
            try {
                configCache?.save(from, answer)
            } catch (e: Exception) {
                // Asked for again at the next start.
            }
        }
        return _config.value
    }

    /** Whether [server]'s sign-in settings are known already (asked for, or remembered from an
     * earlier start): someone signed in opens the app without asking for them again. */
    fun hasConfigFor(server: String): Boolean = synchronized(lock) { _config.value != null && configFrom == server }

    private suspend fun requireConfig(): AuthConfig {
        val config = _config.value?.takeIf { it.usable && configFrom == core.baseUrl() } ?: loadConfig()
        if (config == null) throw ApiException(0, "Can't reach 7even5ive. Check your connection.")
        if (!config.usable) throw ApiException(503, "Accounts aren't set up on this server yet. Try the demo.", "auth_unavailable")
        return config
    }

    // --- signing up and in -----------------------------------------------------------------------
    suspend fun signUp(email: String, password: String): SignUpResult {
        val result = supabase.signUp(requireConfig(), email.trim().lowercase(), password)
        if (result is SignUpResult.SignedIn) adopt(result.session)
        return result
    }

    suspend fun verifySignUp(email: String, code: String) =
        adopt(supabase.verifySignUp(requireConfig(), email.trim().lowercase(), code.trim()))

    suspend fun resendSignUpCode(email: String) = supabase.resendSignUpCode(requireConfig(), email.trim().lowercase())

    /** [login] is an email, or a username (our server finds its email: Supabase knows only emails). */
    suspend fun signIn(login: String, password: String) {
        val config = requireConfig()
        val who = login.trim().removePrefix("@")
        val session = if (isEmail(who)) {
            supabase.signIn(config, who.lowercase(), password)
        } else {
            supabase.sessionFrom(config, core.loginWithUsername(who, password))
        }
        adopt(session)
    }

    suspend fun sendPasswordCode(email: String) = supabase.sendPasswordCode(requireConfig(), email.trim().lowercase())

    /** The emailed code proves the address; then the new password is set, and the student is in.
     * A new password the service refuses (too weak) can be tried again without a new code; a new
     * code, or a recovery session the service no longer accepts, starts over with that code. */
    suspend fun resetPassword(email: String, code: String, password: String) {
        val config = requireConfig()
        val key = "${email.trim().lowercase()}|${code.trim()}"
        val session = recovering?.takeIf { it.first == key }?.second
            ?: supabase.verifyPasswordCode(config, email.trim().lowercase(), code.trim()).also { recovering = key to it }
        try {
            supabase.setPassword(session, password)
        } catch (e: ApiException) {
            if (e.status == 401 || e.status == 403 || SupabaseAuth.ended(e)) recovering = null
            throw e
        }
        recovering = null
        adopt(session)
    }

    /** "Try the demo": everyone shares one invented student. */
    suspend fun useDemo() = durable {
        changing.withLock {
            val leaving = synchronized(lock) { saved }
            if (leaving == Saved.Demo) return@withLock
            val server = core.baseUrl()
            synchronized(lock) {
                saved = Saved.Demo
                epoch++
                earlier.clear()
                _state.value = AccountState.Demo
            }
            persist()
            forgetHere(leaving)
            leaveLater(leaving, server)
        }
        arrive()
    }

    private suspend fun adopt(session: Session) = durable {
        changing.withLock {
            val leaving = synchronized(lock) { saved }
            val same = leaving is Saved.Account && leaving.session.userId == session.userId
            val server = core.baseUrl()
            synchronized(lock) {
                if (!same) {
                    epoch++
                    earlier.clear()
                }
                val me = (leaving as? Saved.Account)?.me.takeIf { same }
                saved = Saved.Account(session, me)
                // Until the profile is confirmed: never "signed out" with a live session behind it.
                _state.value = if (me != null) stateOf(saved) else AccountState.Checking()
            }
            persist()
            if (!same) {
                forgetHere(leaving)
                leaveLater(leaving, server)
            }
        }
        refreshMe()
    }

    /** Clears this phone of whoever left ([onSwitch]). Best effort. */
    private suspend fun forgetHere(leaving: Saved) {
        if (leaving == Saved.Nobody) return
        try {
            onSwitch(leaving)
        } catch (e: Exception) {
            // Clean-up is best effort.
        }
    }

    /**
     * What needs a live token of whoever left, in the app's own scope so it never holds up the
     * screen or the next person: unregistering this phone on [server] ([onLeft]), then ending the
     * session at Supabase (refreshed first if it is about to expire, so Supabase really ends it).
     * Best effort: offline, it simply doesn't happen.
     */
    private fun leaveLater(leaving: Saved, server: String) {
        if (leaving == Saved.Nobody) return
        scope.launch {
            try {
                val last = (leaving as? Saved.Account)?.let { liveToken(it.session) }
                val token = when (leaving) {
                    Saved.Demo -> demoToken
                    is Saved.Account -> last?.accessToken
                    Saved.Nobody -> null
                }
                if (token != null) {
                    try {
                        onLeft(token, server)
                    } catch (e: Exception) {
                        // Their session may be over already; the next sign-in moves this phone anyway.
                    }
                }
                last?.let { supabase.signOut(it) }
            } catch (e: Exception) {
                // Best effort: never a crash for someone who has already left.
            }
        }
    }

    /** Asks the server for the profile and moves to Ready or NeedsProfile. Offline: Checking
     * (with the reason), and the app offers to try again. */
    suspend fun refreshMe(): Me? {
        val (s, at) = synchronized(lock) { (saved as? Saved.Account) to epoch }
        if (s == null) return null
        return try {
            val me = core.me()
            if (!applyMe(at, s.session.userId, me)) return null
            me
        } catch (e: ApiException) {
            synchronized(lock) {
                if (epoch == at && (saved as? Saved.Account)?.me == null) _state.value = AccountState.Checking(e.detail)
            }
            null
        }
    }

    suspend fun saveProfile(form: ProfileForm): Me {
        val (s, at) = synchronized(lock) { (saved as? Saved.Account) to epoch }
        val me = core.saveProfile(form)
        if (s != null) applyMe(at, s.session.userId, me)
        return me
    }

    /** The profile [me] for [userId], if that person is still the one signed in. Becoming able
     * to use the app registers this phone for them. */
    private suspend fun applyMe(at: Long, userId: String, me: Me): Boolean {
        val arrived = synchronized(lock) {
            val current = saved as? Saved.Account
            if (epoch != at || current == null || current.session.userId != userId) return false
            val before = _state.value
            saved = current.copy(me = me)
            _state.value = stateOf(saved)
            !before.usesApp && _state.value.usesApp
        }
        persist()
        if (arrived) arrive()
        return true
    }

    private suspend fun markNeedsProfile() {
        synchronized(lock) {
            val current = saved as? Saved.Account ?: return
            saved = current.copy(me = Me(onboarded = false, email = current.session.email))
            _state.value = AccountState.NeedsProfile(current.session.email)
        }
        persist()
    }

    // --- leaving ---------------------------------------------------------------------------------
    /** Log out: the state flips first, before anything touches the network (the screen moves to
     * the login at once and nothing more is sent as them), and this phone forgets everything of
     * theirs. Ending the session at Supabase and unregistering this phone follow in the
     * background ([leaveLater]). */
    suspend fun signOut() = durable {
        changing.withLock {
            val server = core.baseUrl()
            val leaving = synchronized(lock) {
                val leaving = saved
                if (leaving != Saved.Nobody) {
                    saved = Saved.Nobody
                    epoch++
                    earlier.clear()
                }
                _state.value = AccountState.SignedOut()
                leaving
            }
            if (leaving == Saved.Nobody) return@withLock
            persist()
            forgetHere(leaving)
            leaveLater(leaving, server)
        }
    }

    /** Deletes the account on the server (every row, then the login), then forgets it here. */
    suspend fun deleteAccount() = durable {
        val s = session ?: throw ApiException(403, "Only your own account can be deleted.", "demo_account")
        core.deleteAccount()
        changing.withLock {
            val leaving = synchronized(lock) {
                val current = saved as? Saved.Account
                if (current == null || current.session.userId != s.userId) return@withLock
                saved = Saved.Nobody
                epoch++
                earlier.clear()
                _state.value = AccountState.SignedOut("Your account was deleted.")
                current
            }
            persist()
            // The server already removed its devices with the account; nothing more to send.
            forgetHere(leaving)
        }
    }

    companion object {
        /** Refresh this long before the access token ends: requests in flight must not carry a dead one. */
        const val EARLY_SECONDS = 60L

        /** How long a request made while the app is starting waits for the saved session. */
        const val START_WAIT_MILLIS = 5_000L

        /** Why someone was signed out when a new build of the app moved to another server. */
        const val MOVED = "This version of the app uses a different server. Log in again."

        /** "asha@example.com" is an email; "asha.k" and "@asha.k" are usernames. */
        fun isEmail(login: String): Boolean = '@' in login.trim().removePrefix("@")
    }
}
