package com.sevenfive.app.ui.auth

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
}

/** A username's state while it is typed. */
data class NameCheck(val name: String = "", val checking: Boolean = false, val result: UsernameCheck? = null)

/**
 * Signing up, in, out and the profile, for the screens before the main app. Each action runs
 * once at a time ([busy]); a refusal comes back as [error], in the service's own words.
 */
class AuthViewModel(private val container: AppContainer) : ViewModel() {
    private val accounts = container.accounts
    val account: StateFlow<AccountState> = accounts.state
    val config: StateFlow<AuthConfig?> = accounts.config
    val server: StateFlow<ServerConfig> = container.servers.config

    private val _step = MutableStateFlow<AuthStep>(AuthStep.Login)
    val step: StateFlow<AuthStep> = _step.asStateFlow()

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

    init {
        reloadConfig()
        // A session saved on this phone whose profile hasn't been confirmed yet: ask now.
        if (accounts.state.value is AccountState.Checking) retryProfile()
        // Once someone is in, the next time the login flow shows it starts at Log in again.
        viewModelScope.launch {
            accounts.state.collect { state ->
                if (state.usesApp || state is AccountState.NeedsProfile) {
                    _step.value = AuthStep.Login
                    _error.value = null
                    _notice.value = null
                }
            }
        }
    }

    private var configJob: Job? = null

    /** Asks the server for its sign-in settings. [force]: a load already under way (perhaps to
     * the previous address) is replaced. */
    fun reloadConfig(force: Boolean = false) {
        if (configJob?.isActive == true && !force) return
        configJob?.cancel()
        _loadingConfig.value = true
        configJob = viewModelScope.launch {
            try {
                accounts.loadConfig()
            } finally {
                _loadingConfig.value = false
            }
        }
    }

    fun go(step: AuthStep) {
        _error.value = null
        _notice.value = null
        _step.value = step
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
                _step.value = AuthStep.Code(email)
                _notice.value = "Confirm your email first: we sent you a new code."
                return@run
            }
            throw e
        }
    }

    fun signUp(email: String, password: String) = run {
        when (val result = accounts.signUp(email, password)) {
            is SignUpResult.CodeSent -> {
                _step.value = AuthStep.Code(result.email)
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
        _step.value = AuthStep.Reset(email.trim().lowercase())
        _notice.value = "If $email has an account, a code is on its way."
    }

    fun resetPassword(email: String, code: String, password: String) = run {
        accounts.resetPassword(email, code, password)
        _step.value = AuthStep.Login
    }

    fun tryDemo() = run { accounts.useDemo() }

    fun logOut() = run {
        accounts.signOut()
        _step.value = AuthStep.Login
    }

    fun retryProfile() = run { accounts.refreshMe() }

    /** A new server address (the laptop setup): its sign-in settings are asked for again. */
    fun useServer(input: String) {
        if (input.isBlank()) return
        container.servers.save(ServerConfig.parse(input))
        container.portmax.forget()
        container.cards.reset()
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
        viewModelScope.launch {
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
