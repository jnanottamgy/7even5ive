package com.sevenfive.app.ui.auth

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Visibility
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.AccountState
import com.sevenfive.app.data.AuthConfig
import com.sevenfive.app.ui.components.GlassPill
import com.sevenfive.app.ui.components.PrimaryPill
import com.sevenfive.app.ui.theme.AuroraBackground
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable
import kotlinx.coroutines.delay

/**
 * Everything before the main app, Instagram's way: one clean column, the wordmark on top, the
 * main action full width, the way to the other screen at the bottom. Sign-in happens with
 * Supabase from the phone; the server only ever sees the session it issues.
 */
@Composable
fun AuthFlow(vm: AuthViewModel) {
    val step by vm.step.collectAsStateWithLifecycle()
    AnimatedContent(
        targetState = step,
        transitionSpec = {
            val forward = initialState is AuthStep.Login
            (slideInHorizontally { if (forward) it / 5 else -it / 5 } + fadeIn()) togetherWith
                (slideOutHorizontally { if (forward) -it / 5 else it / 5 } + fadeOut())
        },
        label = "auth step",
    ) { current ->
        when (current) {
            AuthStep.Login -> LoginScreen(vm)
            AuthStep.SignUp -> SignUpScreen(vm)
            is AuthStep.Code -> CodeScreen(vm, current.email)
            AuthStep.Forgot -> ForgotScreen(vm)
            is AuthStep.Reset -> ResetScreen(vm, current.email)
        }
    }
}

/** A blank moment at start, while the phone reads who was signed in. */
@Composable
fun StartingScreen() {
    AuthScaffold { Spacer(Modifier.height(120.dp)); Wordmark() }
}

/** Signed in, but the profile couldn't be confirmed (no network): try again, or log out. */
@Composable
fun CheckingScreen(vm: AuthViewModel, state: AccountState.Checking) {
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    AuthScaffold {
        Spacer(Modifier.height(96.dp))
        Wordmark()
        Spacer(Modifier.height(28.dp))
        if (state.problem == null && error == null) {
            com.sevenfive.app.ui.components.BrandRing(size = 28.dp, spinning = true)
            Spacer(Modifier.height(12.dp))
            Quiet("Opening your account…")
        } else {
            Problem(error ?: state.problem)
            Spacer(Modifier.height(16.dp))
            WideButton("Try again", busy = busy) { vm.retryProfile() }
            Spacer(Modifier.height(10.dp))
            Link("Log out") { vm.logOut() }
        }
    }
}

@Composable
private fun LoginScreen(vm: AuthViewModel) {
    val config by vm.config.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val notice by vm.notice.collectAsStateWithLifecycle()
    val loading by vm.loadingConfig.collectAsStateWithLifecycle()
    val account by vm.account.collectAsStateWithLifecycle()
    val server by vm.server.collectAsStateWithLifecycle()
    var login by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var serverDialog by rememberSaveable { mutableStateOf(false) }
    val focus = LocalFocusManager.current
    val accounts = config?.usable == true
    val canLogIn = accounts && login.isNotBlank() && password.isNotEmpty() && !busy

    AuthScaffold(
        bottom = {
            if (accounts) {
                BottomSwitch("Don't have an account?", "Sign up") { vm.go(AuthStep.SignUp) }
            }
            ServerLine(server.coreUrl) { serverDialog = true }
        },
    ) {
        Spacer(Modifier.height(64.dp))
        Wordmark()
        Spacer(Modifier.height(6.dp))
        Quiet("Your college week, sorted.")
        Spacer(Modifier.height(36.dp))
        (account as? AccountState.SignedOut)?.reason?.let {
            Notice(it)
            Spacer(Modifier.height(12.dp))
        }
        when {
            config == null && loading -> {
                CircularProgressIndicator(Modifier.size(28.dp), color = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.height(20.dp))
            }
            config == null -> {
                Problem("Can't reach 7even5ive. Check your connection.")
                Spacer(Modifier.height(10.dp))
                Link("Try again") { vm.reloadConfig() }
                Spacer(Modifier.height(18.dp))
            }
            !accounts -> {
                Notice("Accounts aren't set up on this server yet. You can try the app with the demo student.")
                Spacer(Modifier.height(18.dp))
            }
            else -> {
                AuthField(
                    login, { login = it; vm.clearError() },
                    label = if (config?.usernameLogin == true) "Username or email" else "Email",
                    keyboard = KeyboardType.Email,
                    ime = ImeAction.Next,
                    onIme = { focus.moveFocus(androidx.compose.ui.focus.FocusDirection.Down) },
                )
                Spacer(Modifier.height(10.dp))
                PasswordField(password, { password = it; vm.clearError() }, "Password", ImeAction.Done) {
                    if (canLogIn) {
                        focus.clearFocus()
                        vm.logIn(login, password)
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    Link("Forgot password?", Modifier.padding(top = 10.dp)) { vm.go(AuthStep.Forgot) }
                }
                Spacer(Modifier.height(16.dp))
                error?.let { Problem(it); Spacer(Modifier.height(10.dp)) }
                notice?.let { Notice(it); Spacer(Modifier.height(10.dp)) }
                WideButton("Log in", enabled = canLogIn, busy = busy) {
                    focus.clearFocus()
                    vm.logIn(login, password)
                }
                Spacer(Modifier.height(22.dp))
                OrDivider()
                Spacer(Modifier.height(22.dp))
            }
        }
        if (!accounts) error?.let { Problem(it); Spacer(Modifier.height(10.dp)) }
        WideButton("Try the demo", primary = !accounts, enabled = !busy && config != null, busy = busy && !accounts) {
            vm.tryDemo()
        }
        Spacer(Modifier.height(8.dp))
        Quiet("An invented student's week: no account needed.", small = true)
    }
    if (serverDialog) {
        ServerDialog(server.coreUrl, onDismiss = { serverDialog = false }) {
            serverDialog = false
            vm.useServer(it)
        }
    }
}

@Composable
private fun SignUpScreen(vm: AuthViewModel) {
    val config by vm.config.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    var email by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var tried by rememberSaveable { mutableStateOf(false) }
    val focus = LocalFocusManager.current
    val min = config?.passwordMinLength ?: 8
    val emailProblem = AuthViewModel.emailProblem(email)
    val passwordProblem = AuthViewModel.passwordProblem(password, min)

    fun submit() {
        tried = true
        if (emailProblem == null && passwordProblem == null) {
            focus.clearFocus()
            vm.signUp(email, password)
        }
    }

    AuthScaffold(bottom = { BottomSwitch("Have an account?", "Log in") { vm.go(AuthStep.Login) } }) {
        Spacer(Modifier.height(56.dp))
        Wordmark()
        Spacer(Modifier.height(18.dp))
        Title("Create your account")
        Quiet("Your deadlines, attendance and college mail, in one place. We'll email you a code to check it's you.")
        Spacer(Modifier.height(24.dp))
        AuthField(email, { email = it.trim(); vm.clearError() }, "Email", KeyboardType.Email, ImeAction.Next,
            problem = if (tried) emailProblem else null,
            onIme = { focus.moveFocus(androidx.compose.ui.focus.FocusDirection.Down) })
        Spacer(Modifier.height(10.dp))
        PasswordField(password, { password = it; vm.clearError() }, "Password", ImeAction.Done,
            problem = if (tried) passwordProblem else null, hint = "At least $min characters") { submit() }
        Spacer(Modifier.height(18.dp))
        error?.let { Problem(it); Spacer(Modifier.height(10.dp)) }
        WideButton("Sign up", enabled = !busy && email.isNotBlank() && password.isNotEmpty(), busy = busy) { submit() }
        Spacer(Modifier.height(14.dp))
        Quiet("7even5ive only reads what you connect, and you can delete your account at any time in Settings.", small = true)
    }
}

@Composable
private fun CodeScreen(vm: AuthViewModel, email: String) {
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val notice by vm.notice.collectAsStateWithLifecycle()
    var code by rememberSaveable { mutableStateOf("") }
    var wait by rememberSaveable { mutableIntStateOf(RESEND_SECONDS) }
    LaunchedEffect(wait) {
        if (wait > 0) {
            delay(1000)
            wait -= 1
        }
    }
    val ready = code.length in 6..10 && !busy

    AuthScaffold(bottom = { BottomSwitch("Wrong address?", "Change email") { vm.go(AuthStep.SignUp) } }) {
        Spacer(Modifier.height(72.dp))
        Title("Enter the code")
        Quiet("We sent a code to $email. It can take a minute; check spam too.")
        Spacer(Modifier.height(26.dp))
        CodeField(code, { code = it.filter(Char::isDigit).take(10); vm.clearError() }) { if (ready) vm.verify(email, code) }
        Spacer(Modifier.height(16.dp))
        error?.let { Problem(it); Spacer(Modifier.height(10.dp)) }
        notice?.let { Notice(it); Spacer(Modifier.height(10.dp)) }
        WideButton("Confirm", enabled = ready, busy = busy) { vm.verify(email, code) }
        Spacer(Modifier.height(16.dp))
        if (wait > 0) {
            Quiet("Send a new code in ${wait}s", small = true)
        } else {
            Link("Send a new code") {
                wait = RESEND_SECONDS
                vm.resend(email)
            }
        }
    }
}

@Composable
private fun ForgotScreen(vm: AuthViewModel) {
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    var email by rememberSaveable { mutableStateOf("") }
    var tried by rememberSaveable { mutableStateOf(false) }
    val problem = AuthViewModel.emailProblem(email)

    AuthScaffold(bottom = { BottomSwitch("Remembered it?", "Log in") { vm.go(AuthStep.Login) } }) {
        Spacer(Modifier.height(72.dp))
        Title("Trouble logging in?")
        Quiet("Enter your email and we'll send you a code to choose a new password.")
        Spacer(Modifier.height(24.dp))
        AuthField(email, { email = it.trim(); vm.clearError() }, "Email", KeyboardType.Email, ImeAction.Send,
            problem = if (tried) problem else null,
            onIme = { tried = true; if (problem == null) vm.sendResetCode(email) })
        Spacer(Modifier.height(18.dp))
        error?.let { Problem(it); Spacer(Modifier.height(10.dp)) }
        WideButton("Send code", enabled = !busy && email.isNotBlank(), busy = busy) {
            tried = true
            if (problem == null) vm.sendResetCode(email)
        }
    }
}

@Composable
private fun ResetScreen(vm: AuthViewModel, email: String) {
    val config by vm.config.collectAsStateWithLifecycle()
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val notice by vm.notice.collectAsStateWithLifecycle()
    var code by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var tried by rememberSaveable { mutableStateOf(false) }
    val min = config?.passwordMinLength ?: 8
    val passwordProblem = AuthViewModel.passwordProblem(password, min)

    fun submit() {
        tried = true
        if (code.length in 6..10 && passwordProblem == null) vm.resetPassword(email, code, password)
    }

    AuthScaffold(bottom = { BottomSwitch("Didn't get a code?", "Start again") { vm.go(AuthStep.Forgot) } }) {
        Spacer(Modifier.height(72.dp))
        Title("Choose a new password")
        Quiet("Enter the code we sent to $email, then your new password.")
        Spacer(Modifier.height(24.dp))
        notice?.let { Notice(it); Spacer(Modifier.height(12.dp)) }
        CodeField(code, { code = it.filter(Char::isDigit).take(10); vm.clearError() }) {}
        Spacer(Modifier.height(12.dp))
        PasswordField(password, { password = it; vm.clearError() }, "New password", ImeAction.Done,
            problem = if (tried) passwordProblem else null, hint = "At least $min characters") { submit() }
        Spacer(Modifier.height(18.dp))
        error?.let { Problem(it); Spacer(Modifier.height(10.dp)) }
        WideButton("Save and log in", enabled = !busy && code.length >= 6 && password.isNotEmpty(), busy = busy) { submit() }
    }
}

// --- pieces ---------------------------------------------------------------------------------------
@Composable
fun AuthScaffold(bottom: (@Composable ColumnScope.() -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    Box(Modifier.fillMaxSize()) {
        AuroraBackground()
        Column(Modifier.fillMaxSize().safeDrawingPadding().imePadding()) {
            Column(
                Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                // Neo-minimal: one left edge for everything, like the rest of the app.
                Column(Modifier.widthIn(max = 420.dp).fillMaxWidth(), horizontalAlignment = Alignment.Start) {
                    content()
                    Spacer(Modifier.height(24.dp))
                }
            }
            if (bottom != null) {
                Box(Modifier.fillMaxWidth().height(0.6.dp).background(LocalAppColors.current.hairline))
                Column(
                    Modifier.fillMaxWidth().padding(vertical = 14.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                    content = bottom,
                )
            }
        }
    }
}

@Composable
fun Wordmark() {
    Column {
        com.sevenfive.app.ui.components.BrandRing(size = 40.dp)
        Text(
            buildAnnotatedString {
                append("7even")
                withStyle(SpanStyle(color = com.sevenfive.app.ui.theme.Orange)) { append("5") }
                append("ive")
            },
            style = MaterialTheme.typography.displaySmall,
            color = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.padding(top = 18.dp).semantics { contentDescription = "7even5ive" },
        )
    }
}

@Composable
fun Title(text: String) {
    Text(text, style = MaterialTheme.typography.headlineLarge, textAlign = TextAlign.Start,
        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp))
}

@Composable
fun Quiet(text: String, small: Boolean = false) {
    Text(
        text,
        style = if (small) MaterialTheme.typography.bodySmall else MaterialTheme.typography.bodyMedium,
        color = LocalAppColors.current.secondaryLabel,
        textAlign = TextAlign.Start,
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
fun Problem(text: String?) {
    if (text == null) return
    Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error,
        textAlign = TextAlign.Start, modifier = Modifier.fillMaxWidth())
}

@Composable
fun Notice(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurface,
        textAlign = TextAlign.Start,
        modifier = Modifier.fillMaxWidth().glassSurface(shape = MaterialTheme.shapes.medium).padding(14.dp),
    )
}

@Composable
fun Link(text: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Text(
        text,
        style = MaterialTheme.typography.labelLarge.copy(textDecoration = androidx.compose.ui.text.style.TextDecoration.Underline),
        color = MaterialTheme.colorScheme.onSurface,
        modifier = modifier.clip(RoundedCornerShape(8.dp)).pressable(onClick = onClick).padding(4.dp),
    )
}

@Composable
fun WideButton(text: String, primary: Boolean = true, enabled: Boolean = true, busy: Boolean = false, onClick: () -> Unit) {
    if (primary) {
        PrimaryPill(text, onClick, Modifier.fillMaxWidth().height(54.dp), enabled = enabled, busy = busy)
    } else {
        GlassPill(text, onClick, Modifier.fillMaxWidth().height(54.dp), enabled = enabled, busy = busy)
    }
}

@Composable
private fun OrDivider() {
    val line = LocalAppColors.current.hairline
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        Box(Modifier.weight(1f).height(0.8.dp).background(line))
        Text("OR", style = MaterialTheme.typography.labelMedium, color = LocalAppColors.current.secondaryLabel,
            modifier = Modifier.padding(horizontal = 14.dp))
        Box(Modifier.weight(1f).height(0.8.dp).background(line))
    }
}

@Composable
private fun BottomSwitch(question: String, action: String, onClick: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(question, style = MaterialTheme.typography.bodyMedium, color = LocalAppColors.current.secondaryLabel)
        Spacer(Modifier.size(4.dp))
        Link(action, onClick = onClick)
    }
}

@Composable
private fun ServerLine(url: String, onClick: () -> Unit) {
    Text(
        "Server: ${url.substringAfter("://")}",
        style = MaterialTheme.typography.labelSmall,
        color = LocalAppColors.current.tertiaryLabel,
        modifier = Modifier.clip(RoundedCornerShape(6.dp)).pressable(onClick = onClick).padding(4.dp),
    )
}

@Composable
private fun ServerDialog(current: String, onDismiss: () -> Unit, onSave: (String) -> Unit) {
    var value by rememberSaveable { mutableStateOf(current) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Server") },
        text = {
            Column {
                Text("The online address, or a laptop's IP on this Wi-Fi.", style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(value, { value = it.trim() }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri))
            }
        },
        confirmButton = { TextButton(onClick = { onSave(value) }, enabled = value.isNotBlank()) { Text("Connect") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun fieldColors() = TextFieldDefaults.colors(
    focusedContainerColor = LocalAppColors.current.glassFill,
    unfocusedContainerColor = LocalAppColors.current.glassFill,
    disabledContainerColor = LocalAppColors.current.glassFill,
    errorContainerColor = LocalAppColors.current.glassFill,
    focusedIndicatorColor = Color.Transparent,
    unfocusedIndicatorColor = Color.Transparent,
    disabledIndicatorColor = Color.Transparent,
    errorIndicatorColor = Color.Transparent,
    focusedLabelColor = MaterialTheme.colorScheme.onSurface,
    unfocusedLabelColor = LocalAppColors.current.secondaryLabel,
    cursorColor = com.sevenfive.app.ui.theme.Orange,
)

@Composable
fun AuthField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    keyboard: KeyboardType = KeyboardType.Text,
    ime: ImeAction = ImeAction.Next,
    problem: String? = null,
    hint: String? = null,
    prefix: String? = null,
    trailing: (@Composable () -> Unit)? = null,
    onIme: () -> Unit = {},
) {
    Column(Modifier.fillMaxWidth()) {
        TextField(
            value = value,
            onValueChange = onChange,
            label = { Text(label) },
            singleLine = true,
            isError = problem != null,
            prefix = prefix?.let { { Text(it, color = LocalAppColors.current.secondaryLabel) } },
            trailingIcon = trailing,
            keyboardOptions = KeyboardOptions(
                keyboardType = keyboard,
                imeAction = ime,
                autoCorrectEnabled = false,
                capitalization = if (keyboard == KeyboardType.Text) androidx.compose.ui.text.input.KeyboardCapitalization.Words
                else androidx.compose.ui.text.input.KeyboardCapitalization.None,
            ),
            keyboardActions = KeyboardActions(onAny = { onIme() }),
            shape = RoundedCornerShape(18.dp),
            colors = fieldColors(),
            modifier = Modifier.fillMaxWidth(),
        )
        FieldNote(problem, hint)
    }
}

@Composable
fun PasswordField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    ime: ImeAction,
    problem: String? = null,
    hint: String? = null,
    onIme: () -> Unit,
) {
    var shown by rememberSaveable { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth()) {
        TextField(
            value = value,
            onValueChange = onChange,
            label = { Text(label) },
            singleLine = true,
            isError = problem != null,
            visualTransformation = if (shown) VisualTransformation.None else PasswordVisualTransformation(),
            trailingIcon = {
                IconButton(onClick = { shown = !shown }) {
                    Icon(if (shown) Icons.Outlined.VisibilityOff else Icons.Outlined.Visibility,
                        contentDescription = if (shown) "Hide password" else "Show password",
                        tint = LocalAppColors.current.secondaryLabel)
                }
            },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ime, autoCorrectEnabled = false),
            keyboardActions = KeyboardActions(onAny = { onIme() }),
            shape = RoundedCornerShape(18.dp),
            colors = fieldColors(),
            modifier = Modifier.fillMaxWidth(),
        )
        FieldNote(problem, hint)
    }
}

@Composable
private fun CodeField(value: String, onChange: (String) -> Unit, onDone: () -> Unit) {
    TextField(
        value = value,
        onValueChange = onChange,
        placeholder = {
            Text("123456", modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center,
                style = MaterialTheme.typography.headlineSmall.copy(letterSpacing = 8.sp),
                color = LocalAppColors.current.tertiaryLabel)
        },
        singleLine = true,
        textStyle = MaterialTheme.typography.headlineSmall.copy(letterSpacing = 8.sp, textAlign = TextAlign.Center),
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword, imeAction = ImeAction.Done),
        keyboardActions = KeyboardActions(onAny = { onDone() }),
        shape = RoundedCornerShape(18.dp),
        colors = fieldColors(),
        modifier = Modifier.fillMaxWidth().semantics { contentDescription = "Code from the email" },
    )
}

@Composable
private fun FieldNote(problem: String?, hint: String?) {
    AnimatedVisibility(problem != null || hint != null) {
        Text(
            problem ?: hint.orEmpty(),
            style = MaterialTheme.typography.bodySmall,
            color = if (problem != null) MaterialTheme.colorScheme.error else LocalAppColors.current.secondaryLabel,
            modifier = Modifier.padding(start = 14.dp, top = 4.dp),
        )
    }
}

/** True when this server offers real accounts (else only the demo). */
fun AuthConfig?.offersAccounts(): Boolean = this?.usable == true

private const val RESEND_SECONDS = 60
