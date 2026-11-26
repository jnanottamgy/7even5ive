package com.sevenfive.app.ui.screens

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.components.PrimaryPill
import com.sevenfive.app.ui.components.PushScaffold
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.voice.VoiceAssistant

/**
 * Talk to 7even5ive. ElevenLabs listens and speaks; every fact comes from a tool the phone runs
 * through the gateway, so the voice can do exactly what a tap can and nothing more. The microphone
 * is asked for when the student starts, and the conversation ends when they leave the screen.
 */
@Composable
fun VoiceScreen(vm: AppViewModel, onBack: () -> Unit) {
    val state by vm.voice.collectAsStateWithLifecycle()
    val app = LocalAppColors.current
    val mic = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) vm.startVoice() else vm.say("The voice assistant needs the microphone")
    }
    // The conversation ends when the student leaves this screen or the app, but not when the
    // phone turns or the theme changes (the activity is only being rebuilt then).
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val activity = context.findActivity()
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP && activity?.isChangingConfigurations != true) vm.stopVoice()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
            if (activity?.isChangingConfigurations != true) {
                vm.stopVoice()
                vm.clearVoice()
            }
        }
    }
    val list = rememberLazyListState()
    LaunchedEffect(state.lines.size) {
        if (state.lines.isNotEmpty()) list.animateScrollToItem(state.lines.size - 1)
    }

    PushScaffold("Ask 7even5ive", onBack) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Orb(state.phase)
            Text(
                statusLine(state),
                style = MaterialTheme.typography.titleMedium,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
            )
            state.working?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = app.secondaryLabel,
                    textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
            }
            Spacer(Modifier.height(12.dp))
            LazyColumn(
                state = list,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (state.lines.isEmpty() && !state.active) {
                    item(key = "hints") { Hints() }
                }
                items(state.lines, key = { it.id }) { line -> Bubble(line) }
            }
            Spacer(Modifier.height(12.dp))
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                if (state.active) {
                    PrimaryPill("End", onClick = { vm.stopVoice() }, icon = Icons.Filled.CallEnd)
                } else {
                    PrimaryPill(
                        if (state.lines.isEmpty()) "Start talking" else "Talk again",
                        onClick = {
                            vm.clearVoice()
                            if (vm.container.voice.hasMicPermission()) vm.startVoice()
                            else mic.launch(Manifest.permission.RECORD_AUDIO)
                        },
                        icon = Icons.Filled.Mic,
                    )
                }
            }
            Text(
                "Nothing you say is stored by 7even5ive. Adding to your calendar still waits for your tap.",
                style = MaterialTheme.typography.labelSmall,
                color = app.tertiaryLabel,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
            )
        }
    }
}

private fun statusLine(state: VoiceAssistant.State): String = when (state.phase) {
    VoiceAssistant.Phase.IDLE -> "Tap to talk about your week"
    VoiceAssistant.Phase.CONNECTING -> "Connecting…"
    VoiceAssistant.Phase.LISTENING -> "Listening…"
    VoiceAssistant.Phase.SPEAKING -> "Speaking…"
    VoiceAssistant.Phase.ENDED -> state.message ?: "Conversation ended"
    VoiceAssistant.Phase.UNAVAILABLE -> state.message ?: "The voice assistant isn't set up yet"
    VoiceAssistant.Phase.ERROR -> state.message ?: "Something went wrong"
}

@Composable
private fun Orb(phase: VoiceAssistant.Phase) {
    val primary = MaterialTheme.colorScheme.primary
    val live = phase == VoiceAssistant.Phase.LISTENING || phase == VoiceAssistant.Phase.SPEAKING
    val pulse = rememberInfiniteTransition(label = "orb")
    val scale by pulse.animateFloat(
        initialValue = 1f,
        targetValue = if (phase == VoiceAssistant.Phase.SPEAKING) 1.14f else if (live) 1.06f else 1f,
        animationSpec = infiniteRepeatable(tween(if (phase == VoiceAssistant.Phase.SPEAKING) 420 else 900), RepeatMode.Reverse),
        label = "orb scale",
    )
    Box(Modifier.fillMaxWidth().padding(top = 12.dp), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .size(132.dp)
                .scale(scale)
                .background(
                    Brush.radialGradient(listOf(primary.copy(alpha = if (live) 0.95f else 0.55f), primary.copy(alpha = 0.18f))),
                    CircleShape,
                ),
            contentAlignment = Alignment.Center,
        ) {
            Icon(Icons.Filled.Mic, contentDescription = null, tint = Color.White, modifier = Modifier.size(44.dp))
        }
    }
}

@Composable
private fun Hints() {
    val app = LocalAppColors.current
    Column(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        listOf(
            "“What's due this week?”",
            "“Can I skip Database Management Systems tomorrow?”",
            "“What's my first class today?”",
            "“Remind me an hour before the quiz.”",
            "“Any placements in my mail?”",
        ).forEach {
            Text(it, style = MaterialTheme.typography.bodyMedium, color = app.secondaryLabel,
                modifier = Modifier.padding(vertical = 3.dp))
        }
    }
}

@Composable
private fun Bubble(line: VoiceAssistant.Line) {
    val primary = MaterialTheme.colorScheme.primary
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (line.fromAgent) Arrangement.Start else Arrangement.End) {
        Text(
            line.text,
            style = MaterialTheme.typography.bodyMedium,
            color = if (line.fromAgent) MaterialTheme.colorScheme.onSurface else Color.White,
            modifier = Modifier
                .widthIn(max = 300.dp)
                .then(
                    if (line.fromAgent) Modifier.glassSurface(shape = RoundedCornerShape(18.dp))
                    else Modifier.background(primary, RoundedCornerShape(18.dp)),
                )
                .padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }
}

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}
