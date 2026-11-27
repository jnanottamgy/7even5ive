package com.sevenfive.app.ui.auth

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.sevenfive.app.AppContainer
import com.sevenfive.app.data.AccountState
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.AuthConfig
import com.sevenfive.app.data.ProfileForm
import com.sevenfive.app.data.ServerConfig
import com.sevenfive.app.data.SignUpResult
import com.sevenfive.app.data.UsernameCheck
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/** Where the signed-out flow is. */
sealed interface AuthStep {
    data object Login : AuthStep
    data object SignUp : AuthStep

    /** The 6-digit code Supabase emailed after sign-up. */
    data class Code(val email: String) : AuthStep

    data object Forgot : AuthStep

    /** The emailed code and the new password. */
    data class Reset(val email: String) : AuthStep

    companion object {
        /** The step as plain strings, for the [SavedStateHandle]: which one, and its email. */
        fun save(step: AuthStep): Pair<String, String?> = when (step) {
            Login -> "login" to null
            SignUp -> "signup" to null
            is Code -> "code" to step.email
            Forgot -> "forgot" to null
            is Reset -> "reset" to step.email
        }

        /** Back from [save]; a step that needs an email it doesn't have starts that part over. */
        fun restore(name: String?, email: String?): AuthStep = when (name) {
            "signup" -> SignUp
            "code" -> if (email.isNullOrBlank()) SignUp else Code(email)
            "forgot" -> Forgot
            "reset" -> if (email.isNullOrBlank()) Forgot else Reset(email)
            else -> Login
        }
    }
}

/** A username's state while it is typed. */
data class NameCheck(val name: String = "", val checking: Boolean = false, val result: UsernameCheck? = null)

/**
 * Signing up, in, out and the profile, for the screens before the main app. Each action runs
 * once at a time ([busy]), except Log out, which never waits; a refusal comes back as [error],
 * in the service's own words. The step (and its email) is kept in [saved], so a student who
 * leaves to read the emailed code finds the code screen again even if Android closed the app.
 */
class AuthViewModel(
    private val container: AppContainer,
    private val saved: SavedStateHandle = SavedStateHandle(),
) : ViewModel() {
    private val accounts = container.accounts
    val account: StateFlow<AccountState> = accounts.state
    val config: StateFlow<AuthConfig?> = accounts.config
    val server: StateFlow<ServerConfig> = container.servers.config

    private val _step = MutableStateFlow(AuthStep.restore(saved[STEP], saved[EMAIL]))
    val step: StateFlow<AuthStep> = _step.asStateFlow()

    private fun setStep(step: AuthStep) {
        _step.value = step
        val (name, email) = AuthStep.save(step)
        saved[STEP] = name
        saved[EMAIL] = email
    }

    private val _busy = MutableStateFlow(false)
    val busy: StateFlow<Boolean> = _busy.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _notice = MutableStateFlow<String?>(null)
    /** A quiet confirmation ("We sent a new code"). */
    val notice: StateFlow<String?> = _notice.asStateFlow()

    private val _loadingConfig = MutableStateFlow(false)
    val loadingConfig: StateFlow<Boolean> = _loadingConfig.asStateFlow()

    private val _name = MutableStateFlow(NameCheck())
    val name: StateFlow<NameCheck> = _name.asStateFlow()
    private var nameJob: Job? = null

    private var configJob: Job? = null
    /** The action in flight ([run]), so Log out can drop it. */
    private var job: Job? = null

    init {
        // This server's sign-in settings, unless someone is signed in already and they are known
        // (remembered from an earlier start): opening the app then asks the server for nothing
        // extra. The login screen always gets fresh ones (below), and so does a new server.
        loadConfig {
            val first = accounts.state.first { it != AccountState.Starting }
            val known = first !is AccountState.SignedOut && accounts.hasConfigFor(container.servers.config.value.coreUrl)
            if (!known) accounts.loadConfig()
        }
        // A session saved on this phone whose profile hasn't been confirmed yet: ask now.
        if (accounts.state.value is AccountState.Checking) retryProfile()
        viewModelScope.launch {
            var last: AccountState = accounts.state.value
            accounts.state.collect { state ->
                // Signed out after using the app: the login screen asks for current settings.
                if (state is AccountState.SignedOut && last !is AccountState.SignedOut && last != AccountState.Starting) {
                    reloadConfig()
                }
                last = state
                // Once someone is in, the next time the login flow shows it starts at Log in again.
                if (state.usesApp || state is AccountState.NeedsProfile) {
                    setStep(AuthStep.Login)
                    _error.value = null
                    _notice.value = null
                }
            }
        }
    }

    /** Asks the server for its sign-in settings. [force]: a load already under way (perhaps to
     * the previous address) is replaced. */
    fun reloadConfig(force: Boolean = false) {
        if (configJob?.isActive == true && !force) return
        configJob?.cancel()
        loadConfig { accounts.loadConfig() }
    }

    /** Runs [block] as the one config load, with [loadingConfig] on meanwhile. A load replaced by
     * a newer one leaves the flag to that one. */
    private fun loadConfig(block: suspend () -> Unit) {
        _loadingConfig.value = true
        lateinit var self: Job
        self = viewModelScope.launch(start = kotlinx.coroutines.CoroutineStart.LAZY) {
            try {
                block()
            } finally {
                if (configJob === self) _loadingConfig.value = false
            }
        }
        configJob = self
        self.start()
    }

    fun go(step: AuthStep) {
        _error.value = null
        _notice.value = null
        setStep(step)
    }

    fun clearError() {
        _error.value = null
    }

    // --- signing in and up ------------------------------------------------------------------------
    fun logIn(login: String, password: String) = run {
        try {
            accounts.signIn(login, password)
        } catch (e: ApiException) {
            if (e.code == "email_not_confirmed" && com.sevenfive.app.data.Accounts.isEmail(login)) {
                // Signed up but never entered the code: a new one, and the code screen.
                val email = login.trim().lowercase()
                runCatching { accounts.resendSignUpCode(email) }
                setStep(AuthStep.Code(email))
                _notice.value = "Confirm your email first: we sent you a new code."
                return@run
            }
            throw e
        }
    }

    fun signUp(email: String, password: String) = run {
        when (val result = accounts.signUp(email, password)) {
            is SignUpResult.CodeSent -> {
                setStep(AuthStep.Code(result.email))
                _notice.value = null
            }
            is SignUpResult.SignedIn -> Unit // the account state moves on by itself
        }
    }

    fun verify(email: String, code: String) = run { accounts.verifySignUp(email, code) }

    fun resend(email: String) = run {
        accounts.resendSignUpCode(email)
        _notice.value = "We sent a new code to $email."
    }

    fun sendResetCode(email: String) = run {
        accounts.sendPasswordCode(email)
        setStep(AuthStep.Reset(email.trim().lowercase()))
        _notice.value = "If $email has an account, a code is on its way."
    }

    fun resetPassword(email: String, code: String, password: String) = run {
        accounts.resetPassword(email, code, password)
        setStep(AuthStep.Login)
    }

    fun tryDemo() = run { accounts.useDemo() }

    /**
     * Never ignored and never held up: whatever else is in flight (a profile check on a slow
     * network) is dropped, the screen moves to Log in at once, and what needs the network
     * happens afterwards in the background (Accounts.signOut).
     */
    fun logOut() {
        job?.cancel()
        _busy.value = false
        _error.value = null
        _notice.value = null
        viewModelScope.launch {
            try {
                accounts.signOut()
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                // Signed out on this phone either way.
            }
            setStep(AuthStep.Login)
        }
    }

    fun retryProfile() = run { accounts.refreshMe() }

    /** A new server address (the laptop setup): its sign-in settings are asked for again. */
    fun useServer(input: String) {
        if (input.isBlank()) return
        container.servers.save(ServerConfig.parse(input))
        container.portmax.forget()
        viewModelScope.launch { container.cards.reset() }
        reloadConfig(force = true)
    }

    // --- the profile ----------------------------------------------------------------------------------
    /** Checks a username after a short pause in typing, so each keystroke isn't a request. */
    fun checkName(raw: String, mine: String? = null) {
        val name = raw.trim().removePrefix("@").lowercase()
        nameJob?.cancel()
        if (name.isEmpty()) {
            _name.value = NameCheck()
            return
        }
        if (name == mine?.lowercase()) {
            _name.value = NameCheck(name, false, UsernameCheck(name, true, null))
            return
        }
        val local = localProblem(name)
        if (local != null) {
            _name.value = NameCheck(name, false, UsernameCheck(name, false, local))
            return
        }
        _name.value = NameCheck(name, checking = true)
        nameJob = viewModelScope.launch {
            delay(400)
            val result = try {
                container.core.usernameCheck(name)
            } catch (e: ApiException) {
                null // can't check now: the server checks again when the profile is saved
            }
            _name.value = NameCheck(name, false, result)
        }
    }

    fun saveProfile(form: ProfileForm, done: () -> Unit = {}) = run {
        accounts.saveProfile(form)
        done()
    }

    private fun run(block: suspend () -> Unit) {
        if (_busy.value) return
        _busy.value = true
        _error.value = null
        job = viewModelScope.launch {
            try {
                block()
            } catch (e: ApiException) {
                _error.value = e.detail
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                // An answer this app can't read, a Keystore hiccup: say so, never close the app.
                _error.value = "Something went wrong. Try again."
            } finally {
                _busy.value = false
            }
        }
    }

    companion object {
        private const val STEP = "auth_step"
        private const val EMAIL = "auth_email"

        /** The server's rules, checked here first so a typo is pointed out at once. */
        fun localProblem(name: String): String? = when {
            name.length < 3 || name.length > 30 -> "Use 3 to 30 characters."
            !name.all { it in 'a'..'z' || it in '0'..'9' || it == '.' || it == '_' } ->
                "Use letters, numbers, dots or underscores."
            name.startsWith('.') || name.endsWith('.') || ".." in name ->
                "A username can't start or end with a dot, or have two in a row."
            name.none { it.isLetterOrDigit() } -> "A username needs a letter or a number."
            else -> null
        }

        fun emailProblem(email: String): String? {
            val e = email.trim()
            return if (Regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$").matches(e)) null else "Enter your email address."
        }

        fun passwordProblem(password: String, min: Int): String? = when {
            password.length < min -> "Use at least $min characters."
            password.isBlank() -> "Use at least $min characters."
            else -> null
        }
    }
}
