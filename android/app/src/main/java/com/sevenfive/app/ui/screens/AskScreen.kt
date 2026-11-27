package com.sevenfive.app.ui.screens

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.asPaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.sevenfive.app.ui.AppViewModel
import com.sevenfive.app.ui.ChatTurn
import com.sevenfive.app.ui.components.EmptyState
import com.sevenfive.app.ui.components.GlassPill
import com.sevenfive.app.ui.components.PushScaffold
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable

private val suggestions = listOf(
    "Can I skip Friday?",
    "What's due this week?",
    "How is my DBMS attendance?",
    "What's my CGPA?",
    "What classes do I have tomorrow?",
    "Any OS notes?",
)

/**
 * Ask your semester: questions in plain words, answered from the student's own data through
 * the same gateway an AI client uses over MCP. Each answer says how it was answered and which
 * tools it called, so the audience can see the gateway at work.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AskScreen(vm: AppViewModel, onBack: () -> Unit) {
    val chat by vm.chat.collectAsStateWithLifecycle()
    var draft by rememberSaveable { mutableStateOf("") }
    val list = rememberLazyListState()
    val app = LocalAppColors.current
    val bottom = WindowInsets.navigationBars.asPaddingValues().calculateBottomPadding()

    LaunchedEffect(chat.size, chat.lastOrNull()?.answer) {
        if (chat.isNotEmpty()) list.animateScrollToItem(chat.size)
    }

    fun send(text: String) {
        vm.ask(text)
        draft = ""
    }

    PushScaffold("Ask", onBack) { padding ->
        Box(Modifier.fillMaxSize().imePadding()) {
            LazyColumn(
                state = list,
                contentPadding = PaddingValues(
                    start = 16.dp,
                    end = 16.dp,
                    top = padding.calculateTopPadding(),
                    bottom = 96.dp + bottom,
                ),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                item(key = "intro") {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(
                            "Ask about your semester in plain words. Answers come only from your " +
                                "own data, through the same gateway your AI uses: it can read, set " +
                                "a reminder, or ask you before it writes anywhere else.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = app.secondaryLabel,
                            modifier = Modifier.padding(horizontal = 4.dp),
                        )
                        if (chat.isEmpty()) {
                            EmptyState(Icons.Outlined.AutoAwesome, "Try one of these")
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                suggestions.forEach { s ->
                                    GlassPill(s, onClick = { send(s) }, tint = MaterialTheme.colorScheme.onSurface)
                                }
                            }
                        }
                    }
                }
                itemsIndexed(chat, key = { i, _ -> i }) { _, turn -> Turn(turn) }
            }

            // The input, floating over the conversation like iMessage's.
            Row(
                Modifier
                    .align(Alignment.BottomCenter)
                    .padding(start = 12.dp, end = 12.dp, bottom = 10.dp + bottom)
                    .fillMaxWidth()
                    .glassSurface(shape = RoundedCornerShape(26.dp), strong = true)
                    .padding(start = 4.dp, end = 6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextField(
                    value = draft,
                    onValueChange = { draft = it.take(500) },
                    placeholder = { Text("Ask anything about your semester") },
                    maxLines = 4,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(onSend = { if (draft.isNotBlank()) send(draft) }),
                    textStyle = MaterialTheme.typography.bodyLarge,
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = Color.Transparent,
                        unfocusedContainerColor = Color.Transparent,
                        focusedIndicatorColor = Color.Transparent,
                        unfocusedIndicatorColor = Color.Transparent,
                        cursorColor = MaterialTheme.colorScheme.primary,
                    ),
                    modifier = Modifier.weight(1f),
                )
                val can = draft.isNotBlank()
                Box(
                    Modifier
                        .size(38.dp)
                        .pressable(enabled = can, haptic = true) { send(draft) }
                        .background(
                            if (can) MaterialTheme.colorScheme.primary else app.hairline,
                            CircleShape,
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Ask", tint = Color.White,
                        modifier = Modifier.size(18.dp))
                }
            }
        }
    }
}

@Composable
private fun Turn(turn: ChatTurn) {
    val app = LocalAppColors.current
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        // The question: a brand-coloured bubble on the right.
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
            Text(
                turn.question,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onPrimary,
                modifier = Modifier
                    .widthIn(max = 300.dp)
                    .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(20.dp, 20.dp, 6.dp, 20.dp))
                    .padding(horizontal = 14.dp, vertical = 9.dp),
            )
        }
        // The answer: glass on the left, with how it was answered underneath.
        Column(
            Modifier
                .widthIn(max = 330.dp)
                .glassSurface(shape = RoundedCornerShape(20.dp, 20.dp, 20.dp, 6.dp))
                .padding(horizontal = 14.dp, vertical = 10.dp),
        ) {
            when {
                turn.error != null -> Text(turn.error, style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.error)
                turn.answer == null -> Thinking()
                else -> {
                    Text(turn.answer.answer, style = MaterialTheme.typography.bodyLarge)
                    val via = if (turn.answer.route == "claude") "Claude" else "offline answers"
                    val tools = turn.answer.tools.distinct().joinToString(", ")
                    Text(
                        "via $via" + if (tools.isNotEmpty()) " · gateway: $tools" else "",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Medium,
                        color = app.tertiaryLabel,
                        modifier = Modifier.padding(top = 6.dp),
                    )
                }
            }
        }
    }
}

/** Three dots breathing in turn while the answer is on its way. */
@Composable
private fun Thinking() {
    val t = rememberInfiniteTransition(label = "thinking")
    Row(horizontalArrangement = Arrangement.spacedBy(5.dp), modifier = Modifier.padding(vertical = 6.dp)) {
        repeat(3) { i ->
            val a by t.animateFloat(
                initialValue = 0.25f,
                targetValue = 1f,
                animationSpec = infiniteRepeatable(tween(520, delayMillis = i * 160), RepeatMode.Reverse),
                label = "dot$i",
            )
            Box(Modifier.size(8.dp).alpha(a).background(LocalAppColors.current.secondaryLabel, CircleShape))
        }
    }
}
