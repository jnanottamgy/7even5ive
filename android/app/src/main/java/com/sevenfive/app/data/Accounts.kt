package com.sevenfive.app.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

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

/** One fixed token (tests, tools). */
class FixedToken(private val value: String) : TokenSource {
    override suspend fun token(): String = value
}

/**
 * Signing up, in and out, and staying signed in. Supabase Auth is called from the phone itself
 * ([SupabaseAuth]); our server checks each access token and keeps the profile.
 *
 * Refreshing: an access token lasts about an hour. It is swapped for a new one a minute before
 * it ends, and once more if the server says it has ended; one refresh at a time (Supabase rotates
 * refresh tokens, and two racing refreshes could end the session). A refresh Supabase refuses
 * means the session is over (signed out elsewhere, password changed): back to the login screen.
 * A refresh that can't reach Supabase keeps the session: being offline never signs anyone out.
 */
class Accounts(
    private val store: SavedAccount,
    private val supabase: SupabaseAuth,
    private val demoToken: String,
    private val now: () -> Long = { System.currentTimeMillis() / 1000 },
) : TokenSource {
    lateinit var core: CoreApi

    /** Runs when the person using the app changes, before the next one's data loads: clears
     * what belonged to [leaving] (cards, the portal login, notifications). */
    var onSwitch: suspend (leaving: Saved) -> Unit = {}

    /** Runs after someone new is in (an account or the demo): registers this phone for them. */
    var onArrive: suspend () -> Unit = {}

    private val _state = MutableStateFlow<AccountState>(AccountState.Starting)
    val state: StateFlow<AccountState> = _state.asStateFlow()

    private val _config = MutableStateFlow<AuthConfig?>(null)
    val config: StateFlow<AuthConfig?> = _config.asStateFlow()

    @Volatile
    private var saved: Saved = Saved.Nobody
    private val refreshing = Mutex()
    private val changing = Mutex()

    /** Reads what this phone remembers. Quick: no network. */
    fun start() {
        saved = store.load()
        _state.value = stateOf(saved)
    }

    val session: Session? get() = (saved as? Saved.Account)?.session

    private fun stateOf(s: Saved): AccountState = when (s) {
        Saved.Nobody -> AccountState.SignedOut()
        Saved.Demo -> AccountState.Demo
        is Saved.Account -> when {
            s.me == null -> AccountState.Checking()
            s.me.onboarded -> AccountState.Ready(s.me)
            else -> AccountState.NeedsProfile(s.session.email)
        }
    }

    // --- tokens ---------------------------------------------------------------------------------
    override suspend fun token(): String? = when (val s = saved) {
        Saved.Nobody -> null
        Saved.Demo -> demoToken
        is Saved.Account ->
            if (s.session.expiresAt - now() > EARLY_SECONDS) s.session.accessToken
            else refreshed(s.session.accessToken, force = false)
    }

    override suspend fun rejected(used: String, status: Int, code: String?): String? {
        if (saved !is Saved.Account) return null
        return when (code) {
            "profile_required" -> {
                markNeedsProfile()
                null
            }
            "session_expired" -> refreshed(used, force = true)
            else -> null
        }
    }

    /** A fresh access token, or null when the session is over (then signed out). */
    private suspend fun refreshed(used: String, force: Boolean): String? {
        var ended = false
        val token = refreshing.withLock {
            val s = saved as? Saved.Account ?: return@withLock null
            // Another request refreshed while this one waited: use its token.
            if (s.session.accessToken != used) return@withLock s.session.accessToken
            if (!force && s.session.expiresAt - now() > EARLY_SECONDS) return@withLock s.session.accessToken
            try {
                val fresh = supabase.refresh(s.session)
                val next = s.copy(session = fresh)
                saved = next
                store.save(next)
                fresh.accessToken
            } catch (e: ApiException) {
                if (SupabaseAuth.ended(e)) {
                    ended = true
                    null
                } else {
                    s.session.accessToken // offline or Supabase busy: the server decides
                }
            }
        }
        if (ended) signOutHere("Your session ended. Log in again.", alive = false)
        return token
    }

    // --- the server's sign-in settings -------------------------------------------------------------
    /** Asks the server how to sign in; keeps the last answer if it can't be reached. */
    suspend fun loadConfig(): AuthConfig? {
        try {
            _config.value = core.authConfig()
        } catch (e: ApiException) {
            // The login screen says the server can't be reached; the demo needs it too.
        }
        return _config.value
    }

    private suspend fun requireConfig(): AuthConfig {
        val config = _config.value?.takeIf { it.usable } ?: loadConfig()
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

    private var recovering: Session? = null

    /** The emailed code proves the address; then the new password is set, and the student is in.
     * A new password the service refuses (too weak) can be tried again without a new code. */
    suspend fun resetPassword(email: String, code: String, password: String) {
        val config = requireConfig()
        val session = recovering?.takeIf { it.email.equals(email.trim(), ignoreCase = true) }
            ?: supabase.verifyPasswordCode(config, email.trim().lowercase(), code.trim()).also { recovering = it }
        supabase.setPassword(session, password)
        recovering = null
        adopt(session)
    }

    /** "Try the demo": everyone shares one invented student. */
    suspend fun useDemo() = changing.withLock {
        val leaving = saved
        if (leaving == Saved.Demo) return@withLock
        onSwitch(leaving)
        endAtSupabase(leaving)
        saved = Saved.Demo
        store.save(Saved.Demo)
        _state.value = AccountState.Demo
        onArrive()
    }

    private suspend fun adopt(session: Session) {
        changing.withLock {
            val leaving = saved
            val same = leaving is Saved.Account && leaving.session.userId == session.userId
            if (!same) {
                onSwitch(leaving)
                endAtSupabase(leaving)
            }
            saved = Saved.Account(session, (leaving as? Saved.Account)?.me.takeIf { same })
            store.save(saved)
        }
        refreshMe()
        if (saved is Saved.Account) onArrive()
    }

    /** Asks the server for the profile and moves to Ready or NeedsProfile. Offline: Checking
     * (with the reason), and the app offers to try again. */
    suspend fun refreshMe(): Me? {
        val s = saved as? Saved.Account ?: return null
        return try {
            val me = core.me()
            val current = saved as? Saved.Account ?: return null
            if (current.session.userId != s.session.userId) return null
            val next = current.copy(me = me)
            saved = next
            store.save(next)
            _state.value = stateOf(next)
            me
        } catch (e: ApiException) {
            if (saved is Saved.Account && (saved as Saved.Account).me == null) {
                _state.value = AccountState.Checking(e.detail)
            }
            null
        }
    }

    suspend fun saveProfile(form: ProfileForm): Me {
        val me = core.saveProfile(form)
        val current = saved as? Saved.Account ?: return me
        val next = current.copy(me = me)
        saved = next
        store.save(next)
        _state.value = stateOf(next)
        return me
    }

    private fun markNeedsProfile() {
        val current = saved as? Saved.Account ?: return
        val next = current.copy(me = Me(onboarded = false, email = current.session.email))
        saved = next
        store.save(next)
        _state.value = AccountState.NeedsProfile(current.session.email)
    }

    // --- leaving ---------------------------------------------------------------------------------
    /** Log out: the session ends at Supabase too, and this phone forgets everything of theirs. */
    suspend fun signOut() = signOutHere(null)

    /** [alive] false: Supabase already refused this session, so nothing more is sent with it
     * (no refresh, no logout call): the phone just forgets it. */
    private suspend fun signOutHere(reason: String?, alive: Boolean = true) = changing.withLock {
        val leaving = saved
        if (leaving == Saved.Nobody) {
            _state.value = AccountState.SignedOut(reason)
            return@withLock
        }
        if (!alive) saved = Saved.Nobody
        onSwitch(leaving)
        if (alive) endAtSupabase(leaving)
        saved = Saved.Nobody
        store.save(Saved.Nobody)
        _state.value = AccountState.SignedOut(reason)
    }

    /** Deletes the account on the server (every row, then the login), then signs out here. */
    suspend fun deleteAccount() {
        if (saved !is Saved.Account) throw ApiException(403, "Only your own account can be deleted.", "demo_account")
        core.deleteAccount()
        signOutHere("Your account was deleted.")
    }

    private suspend fun endAtSupabase(leaving: Saved) {
        if (leaving is Saved.Account) supabase.signOut(leaving.session)
    }

    companion object {
        /** Refresh this long before the access token ends: requests in flight must not carry a dead one. */
        const val EARLY_SECONDS = 60L

        /** "asha@example.com" is an email; "asha.k" and "@asha.k" are usernames. */
        fun isEmail(login: String): Boolean = '@' in login.trim().removePrefix("@")
    }
}
