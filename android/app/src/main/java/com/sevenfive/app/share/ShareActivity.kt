package com.sevenfive.app.share

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Base64
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.automirrored.outlined.ShortText
import androidx.compose.material3.CircularProgressIndicator
import androidx.lifecycle.lifecycleScope
import java.io.ByteArrayOutputStream
import java.io.InputStream
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.IntentCompat
import com.sevenfive.app.SevenFiveApp
import com.sevenfive.app.data.ApiException
import com.sevenfive.app.ui.components.GlassPill
import com.sevenfive.app.ui.components.GroupField
import com.sevenfive.app.ui.components.IconTile
import com.sevenfive.app.ui.components.PrimaryPill
import com.sevenfive.app.ui.components.SectionHeader
import com.sevenfive.app.ui.components.kindColor
import com.sevenfive.app.ui.components.kindStyle
import com.sevenfive.app.ui.theme.AuroraBackground
import com.sevenfive.app.ui.theme.LocalAppColors
import com.sevenfive.app.ui.theme.LocalStatusColors
import com.sevenfive.app.ui.theme.SevenFiveTheme
import com.sevenfive.app.ui.theme.glassSurface
import com.sevenfive.app.ui.theme.pressable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.LocalDate
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

private const val MAX_BYTES = 4 * 1024 * 1024

/** What was shared: some text, a file, or both. */
private data class Shared(val text: String?, val name: String?, val bytes: ByteArray?, val tooBig: Boolean)

/**
 * "Share to 7even5ive" from any app: a WhatsApp message, a PDF from Files. The student can say
 * what it is (filed as they say, after the same checks as a bot decision), or let 7even5ive
 * read it like any forwarded message.
 */
class ShareActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.light(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
        )
        // Read off the main thread: a file from a cloud drive can take a while to open.
        val shared = mutableStateOf<Shared?>(null)
        lifecycleScope.launch { shared.value = withContext(Dispatchers.IO) { read(intent) } }
        setContent {
            SevenFiveTheme {
                val ready = shared.value
                if (ready == null) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        AuroraBackground()
                        CircularProgressIndicator()
                    }
                } else {
                    ShareSheet(ready, onDone = { finish() })
                }
            }
        }
    }

    private fun read(intent: Intent): Shared {
        val text = intent.getStringExtra(Intent.EXTRA_TEXT)?.trim()?.takeIf { it.isNotEmpty() }
        val uri = IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
            ?: return Shared(text, null, null, false)
        var name: String? = null
        var size = -1L
        runCatching {
            contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
                if (c.moveToFirst()) {
                    name = c.getString(0)
                    if (!c.isNull(1)) size = c.getLong(1)
                }
            }
        }
        if (size > MAX_BYTES) return Shared(text, name, null, true)
        val bytes = runCatching {
            contentResolver.openInputStream(uri)?.use { input -> readAtMost(input, MAX_BYTES) }
        }.getOrNull()
        return Shared(text, name ?: "shared-file", bytes, bytes == null)
    }

    /** At most [max] bytes, or null past that: a file whose size the app didn't say (a video,
     * a cloud file) is never read into memory whole. */
    private fun readAtMost(input: InputStream, max: Int): ByteArray? {
        val out = ByteArrayOutputStream()
        val buffer = ByteArray(64 * 1024)
        while (true) {
            val n = input.read(buffer)
            if (n < 0) return out.toByteArray()
            if (out.size() + n > max) return null
            out.write(buffer, 0, n)
        }
    }

    @OptIn(ExperimentalLayoutApi::class)
    @Composable
    private fun ShareSheet(shared: Shared, onDone: () -> Unit) {
        val container = (application as SevenFiveApp).container
        val subjects = (container.cards.cached()?.subjects.orEmpty() + "Miscellaneous").distinct()
        val app = LocalAppColors.current
        val scope = rememberCoroutineScope()
        var kind by remember { mutableStateOf<String?>(null) }
        var subject by remember { mutableStateOf(subjects.firstOrNull() ?: "Miscellaneous") }
        var title by remember { mutableStateOf(shared.name ?: shared.text?.lineSequence()?.firstOrNull()?.take(90).orEmpty()) }
        val today = remember { LocalDate.now() }
        var date by remember { mutableStateOf(today.plusDays(1)) }
        var time by remember { mutableStateOf(LocalTime.of(23, 59)) }
        var busy by remember { mutableStateOf(false) }
        var done by remember { mutableStateOf<String?>(null) }
        var problem by remember { mutableStateOf<String?>(null) }
        val dated = kind in setOf("deadline", "exam", "event")

        fun send() {
            busy = true
            problem = null
            scope.launch {
                try {
                    val body = buildJsonObject {
                        shared.text?.let { put("text", it) }
                        if (shared.bytes != null) {
                            put("file_name", shared.name ?: "shared-file")
                            put("file_b64", withContext(Dispatchers.Default) { Base64.encodeToString(shared.bytes, Base64.NO_WRAP) })
                        } else if (shared.name != null && shared.text == null) {
                            put("text", shared.name)
                        }
                        kind?.let { k ->
                            put("kind", k)
                            put("subject", subject)
                            if (title.isNotBlank()) put("title", title.trim())
                            if (k in setOf("deadline", "exam", "event")) {
                                put("due_at", ZonedDateTime.of(date, time, ZoneId.systemDefault()).toOffsetDateTime().toString())
                            }
                        }
                    }
                    val result = container.core.share(body)
                    done = when (result.status) {
                        "filed" -> "Added: ${result.item?.title ?: "filed"}, under ${result.item?.subject ?: subject}."
                        "needs_review" -> "Saved under “Couldn't read these”: open the app to sort it."
                        "filtered" -> "Filtered out as spam."
                        else -> "Nothing to file in that one."
                    }
                    container.cards.refresh()
                    delay(1_400)
                    onDone()
                } catch (e: ApiException) {
                    problem = e.detail
                } finally {
                    busy = false
                }
            }
        }

        Box(Modifier.fillMaxSize()) {
            AuroraBackground()
            Column(
                Modifier
                    .fillMaxSize()
                    .safeDrawingPadding()
                    .imePadding()
                    .verticalScroll(rememberScrollState())
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text("Add to 7even5ive", style = MaterialTheme.typography.headlineMedium)
                // What came in.
                Row(
                    Modifier.fillMaxWidth().glassSurface().padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    IconTile(if (shared.name != null) Icons.Outlined.Description else Icons.AutoMirrored.Outlined.ShortText, app.material)
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(shared.name ?: "Message", style = MaterialTheme.typography.titleMedium, maxLines = 1,
                            overflow = TextOverflow.Ellipsis)
                        Text(
                            when {
                                shared.tooBig -> "Too large to send (4 MB at most): only the name goes."
                                shared.text != null -> shared.text
                                shared.bytes != null -> "${shared.bytes.size / 1024} KB"
                                else -> "Nothing readable came through."
                            },
                            style = MaterialTheme.typography.bodySmall,
                            color = if (shared.tooBig) MaterialTheme.colorScheme.error else app.secondaryLabel,
                            maxLines = 3,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }

                if (done != null) {
                    Row(Modifier.fillMaxWidth().glassSurface().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        IconTile(Icons.Outlined.CheckCircle, LocalStatusColors.current.safe)
                        Spacer(Modifier.width(12.dp))
                        Text(done!!, style = MaterialTheme.typography.bodyLarge)
                    }
                    return@Column
                }

                SectionHeader("What is it?")
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Choice("Let 7even5ive read it", kind == null, MaterialTheme.colorScheme.primary) { kind = null }
                    listOf("deadline", "exam", "material", "event", "notice").forEach { k ->
                        Choice(kindStyle(k).label, kind == k, kindColor(k)) { kind = k }
                    }
                }
                if (kind == null) {
                    Text(
                        "7even5ive reads it the way it reads a forwarded message.",
                        style = MaterialTheme.typography.bodySmall,
                        color = app.secondaryLabel,
                        modifier = Modifier.padding(horizontal = 6.dp),
                    )
                } else {
                    SectionHeader("Subject")
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        subjects.forEach { s -> Choice(s, subject == s, MaterialTheme.colorScheme.primary) { subject = s } }
                    }
                    SectionHeader("Title")
                    Column(Modifier.fillMaxWidth().glassSurface()) {
                        GroupField(title, { title = it.take(90) }, "Title", keyboardType = androidx.compose.ui.text.input.KeyboardType.Text)
                    }
                    if (dated) {
                        SectionHeader("When")
                        val chip = DateTimeFormatter.ofPattern("EEE d", Locale.ENGLISH)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            (0..7).map { today.plusDays(it.toLong()) }.forEach { d ->
                                val label = when (d) {
                                    today -> "Today"
                                    today.plusDays(1) -> "Tomorrow"
                                    else -> d.format(chip)
                                }
                                Choice(label, date == d, MaterialTheme.colorScheme.primary) { date = d }
                            }
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            listOf(LocalTime.of(9, 0), LocalTime.of(13, 0), LocalTime.of(17, 0), LocalTime.of(23, 59)).forEach { t ->
                                Choice(t.format(DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH)), time == t,
                                    MaterialTheme.colorScheme.primary) { time = t }
                            }
                        }
                    }
                }
                problem?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error) }
                Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    GlassPill("Cancel", onClick = onDone, tint = MaterialTheme.colorScheme.onSurface)
                    Spacer(Modifier.weight(1f))
                    PrimaryPill(
                        "Add",
                        onClick = { send() },
                        busy = busy,
                        enabled = shared.text != null || shared.name != null,
                    )
                }
            }
        }
    }

    @Composable
    private fun Choice(text: String, selected: Boolean, color: Color, onClick: () -> Unit) {
        val fill by animateColorAsState(if (selected) color else Color.Transparent, label = "choice")
        Text(
            text,
            style = MaterialTheme.typography.labelLarge,
            color = if (selected) Color.White else MaterialTheme.colorScheme.onSurface,
            modifier = Modifier
                .pressable(scaleTo = 0.94f, haptic = true, onClick = onClick)
                .glassSurface(shape = CircleShape, strong = true)
                .background(fill, CircleShape)
                .padding(horizontal = 14.dp, vertical = 8.dp),
        )
    }
}
