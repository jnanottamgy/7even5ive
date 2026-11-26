package com.sevenfive.app.ui.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.InputChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.saveable.listSaver
import androidx.compose.runtime.toMutableStateList
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.data.Profile
import com.sevenfive.app.data.ProfileForm
import com.sevenfive.app.ui.components.PushScaffold
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors

/** After sign-up: the profile that makes the account a student of its own. */
@Composable
fun OnboardingScreen(vm: AuthViewModel, email: String?) {
    AuthScaffold(bottom = {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Quiet(if (email != null) "Signed in as $email ·" else "Signed in ·", small = true)
        }
        Link("Log out") { vm.logOut() }
    }) {
        Spacer(Modifier.height(40.dp))
        Wordmark()
        Spacer(Modifier.height(16.dp))
        Title("Set up your profile")
        Quiet("Pick a username your classmates will know. Everything else helps file your messages under the right subject.")
        Spacer(Modifier.height(22.dp))
        ProfileEditor(vm, initial = null, button = "Finish")
    }
}

/** Settings → Edit profile. */
@Composable
fun ProfileEditScreen(vm: AuthViewModel, profile: Profile?, onBack: () -> Unit) {
    PushScaffold("Edit profile", onBack) { padding ->
        Column(
            Modifier.fillMaxSize().imePadding().verticalScroll(rememberScrollState()).padding(padding),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Column(Modifier.widthIn(max = 460.dp).fillMaxWidth().padding(top = 8.dp)) {
                ProfileEditor(vm, initial = profile, button = "Save", onSaved = onBack)
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProfileEditor(vm: AuthViewModel, initial: Profile?, button: String, onSaved: () -> Unit = {}) {
    val busy by vm.busy.collectAsStateWithLifecycle()
    val error by vm.error.collectAsStateWithLifecycle()
    val check by vm.name.collectAsStateWithLifecycle()
    var username by rememberSaveable { mutableStateOf(initial?.username.orEmpty()) }
    var name by rememberSaveable { mutableStateOf(initial?.name.orEmpty()) }
    var college by rememberSaveable { mutableStateOf(initial?.college.orEmpty()) }
    var branch by rememberSaveable { mutableStateOf(initial?.branch.orEmpty()) }
    var year by rememberSaveable { mutableStateOf(initial?.year ?: 0) }
    var interests by rememberSaveable { mutableStateOf(initial?.interests.orEmpty()) }
    // Saved across rotation like the other fields.
    val subjects = rememberSaveable(saver = listSaver(save = { it.toList() }, restore = { it.toMutableStateList() })) {
        initial?.subjects.orEmpty().toMutableStateList()
    }
    var subject by rememberSaveable { mutableStateOf("") }
    var tried by rememberSaveable { mutableStateOf(false) }
    val focus = LocalFocusManager.current
    LaunchedEffect(Unit) { vm.clearError(); vm.checkName(username, mine = initial?.username) }

    val nameProblem = if (name.isBlank()) "Your name is needed." else null
    val handle = username.trim().removePrefix("@").lowercase()
    val handleProblem = when {
        handle.isEmpty() -> "Choose a username."
        check.name == handle && check.result?.available == false -> check.result?.message
        else -> AuthViewModel.localProblem(handle)
    }
    val waiting = check.checking && check.name == handle

    fun addSubject() {
        val clean = subject.trim().replace(Regex("\\s+"), " ")
        if (clean.isNotEmpty() && subjects.none { it.equals(clean, ignoreCase = true) } && subjects.size < 20) {
            subjects.add(clean.take(60))
        }
        subject = ""
    }

    fun save() {
        tried = true
        if (subject.isNotBlank()) addSubject()
        if (handleProblem != null || nameProblem != null || waiting) return
        focus.clearFocus()
        vm.saveProfile(
            ProfileForm(
                username = handle,
                name = name.trim(),
                college = college.trim(),
                branch = branch.trim(),
                year = year.takeIf { it in 1..6 },
                interests = interests.trim(),
                subjects = subjects.toList(),
                sendYear = true, // so that clearing it clears it
            ),
            done = onSaved,
        )
    }

    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        AuthField(
            username,
            { username = it.trim().removePrefix("@").lowercase().take(30); vm.checkName(username, mine = initial?.username) },
            label = "Username",
            keyboard = KeyboardType.Ascii,
            prefix = "@",
            problem = if (tried || handle.length >= 3) handleProblem else null,
            hint = if (handleProblem == null && check.result?.available == true && check.name == handle) "@$handle is yours to take" else null,
            trailing = {
                when {
                    waiting -> CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    handle.isEmpty() -> Unit
                    handleProblem == null && check.name == handle && check.result?.available == true ->
                        Icon(Icons.Outlined.CheckCircle, "Available", tint = LocalStatusColors.current.safe)
                    handleProblem != null && handle.length >= 3 ->
                        Icon(Icons.Outlined.ErrorOutline, "Not available", tint = MaterialTheme.colorScheme.error)
                }
            },
        )
        AuthField(name, { name = it.take(60) }, "Full name", KeyboardType.Text, problem = if (tried) nameProblem else null)
        AuthField(college, { college = it.take(80) }, "College (optional)", KeyboardType.Text)
        AuthField(branch, { branch = it.take(40) }, "Branch, e.g. CSE (optional)", KeyboardType.Text)

        Text("Year", style = MaterialTheme.typography.labelLarge, color = LocalAppColors.current.secondaryLabel,
            modifier = Modifier.padding(start = 4.dp, top = 6.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            (1..5).forEach { y ->
                FilterChip(
                    selected = year == y,
                    onClick = { year = if (year == y) 0 else y },
                    label = { Text("$y") },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = MaterialTheme.colorScheme.primary,
                        selectedLabelColor = MaterialTheme.colorScheme.onPrimary,
                    ),
                )
            }
        }

        Text("Subjects (optional)", style = MaterialTheme.typography.labelLarge, color = LocalAppColors.current.secondaryLabel,
            modifier = Modifier.padding(start = 4.dp, top = 6.dp))
        if (subjects.isNotEmpty()) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                subjects.toList().forEach { s ->
                    InputChip(
                        selected = false,
                        onClick = { subjects.remove(s) },
                        label = { Text(s) },
                        trailingIcon = { Icon(Icons.Outlined.Close, "Remove $s", Modifier.size(16.dp)) },
                    )
                }
            }
        }
        AuthField(subject, { subject = it.take(60) }, "Add a subject", KeyboardType.Text, ImeAction.Done,
            hint = "Your college portal's subjects are added on their own once it's connected.",
            onIme = { addSubject() })
        AuthField(interests, { interests = it.take(200) }, "Interests, e.g. hackathons (optional)", KeyboardType.Text, ImeAction.Done)

        Spacer(Modifier.height(6.dp))
        error?.let { Problem(it) }
        WideButton(button, enabled = !busy && !waiting, busy = busy) { save() }
        Spacer(Modifier.height(4.dp))
    }
}
