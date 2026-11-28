package com.sevenfive.app

import com.sevenfive.app.data.ApiException
import com.sevenfive.app.data.AppJson
import com.sevenfive.app.data.AppSettings
import com.sevenfive.app.data.AskAnswer
import com.sevenfive.app.data.AuthConfig
import com.sevenfive.app.data.Briefing
import com.sevenfive.app.data.CallHistory
import com.sevenfive.app.data.CallOutcome
import com.sevenfive.app.data.CallSettings
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.CoreApi
import com.sevenfive.app.data.DemoForward
import com.sevenfive.app.data.Disconnected
import com.sevenfive.app.data.FilePage
import com.sevenfive.app.data.FixedToken
import com.sevenfive.app.data.GoogleDisconnect
import com.sevenfive.app.data.GoogleFinish
import com.sevenfive.app.data.GoogleStart
import com.sevenfive.app.data.Http
import com.sevenfive.app.data.LibraryTree
import com.sevenfive.app.data.MailCheckResult
import com.sevenfive.app.data.McpConnections
import com.sevenfive.app.data.Me
import com.sevenfive.app.data.OpenedFile
import com.sevenfive.app.data.Outbox
import com.sevenfive.app.data.PersonalToken
import com.sevenfive.app.data.ProfileForm
import com.sevenfive.app.data.SetReminderResult
import com.sevenfive.app.data.ShareResult
import com.sevenfive.app.data.ToolResponse
import com.sevenfive.app.data.UsernameCheck
import com.sevenfive.app.data.VoiceSession
import com.sevenfive.app.data.WhatsAppLink
import com.sevenfive.app.data.library
import com.sevenfive.app.data.libraryFiles
import com.sevenfive.app.data.openFile
import com.sevenfive.app.data.toJson
import com.sevenfive.app.ui.screens.latestCgpa
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.KSerializer
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.descriptors.StructureKind
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * The contract with the server, from the app's side. Each file in src/test/resources/contract is
 * one real exchange with the server: the request the server was sent and the answer it gave,
 * recorded on the demo morning by core/tests/test_contract.py, which also fails when the server
 * stops sending what these files hold.
 *
 * Here each answer is served back to the app's own CoreApi, through its real Http. Each test
 * checks three things. The request the app makes is the recorded one (method, path, token,
 * body). The answer reads into the app's models without the leniency hiding anything. And
 * every field the models read is one the server sends, so a renamed field can't quietly become
 * an empty screen.
 *
 * When the server changes an answer on purpose: UPDATE_CONTRACT=1 pytest tests/test_contract.py
 * in core/, then these tests.
 */
class ContractTest {
    private lateinit var server: MockWebServer
    private lateinit var api: CoreApi

    @Before
    fun start() {
        server = MockWebServer()
        server.start()
        val base = server.url("/").toString().trimEnd('/')
        api = CoreApi(Http(FixedToken("contract-token"), pause = {})) { base }
    }

    @After
    fun stop() = server.shutdown()

    /** Serves the recorded answer to [call], then checks the request the app made was the recorded one. */
    private suspend fun <T> exchange(name: String, call: suspend () -> T): T {
        val recorded = fixture(name)
        server.enqueue(
            MockResponse()
                .setResponseCode(recorded["status"]!!.jsonPrimitive.int)
                .setHeader("Content-Type", "application/json")
                .setBody(recorded["response"].toString()),
        )
        val out = try {
            call()
        } finally {
            val sent = server.takeRequest(5, TimeUnit.SECONDS) ?: throw AssertionError("$name: the app sent nothing")
            val want = recorded["request"]!!.jsonObject
            assertEquals("$name: method", want.text("method"), sent.method)
            assertEquals("$name: path", want.text("path"), sent.path)
            if (want.text("auth") == "none") {
                assertNull("$name: no token on a public call", sent.getHeader("Authorization"))
            } else {
                assertEquals("$name: token", "Bearer contract-token", sent.getHeader("Authorization"))
            }
            want["body"]?.let { body ->
                assertEquals("$name: body", body, AppJson.parseToJsonElement(sent.body.readUtf8()))
            }
        }
        return out
    }

    private fun body(name: String): JsonObject = fixture(name)["request"]!!.jsonObject["body"]!!.jsonObject
    private fun args(name: String): JsonObject = body(name)["args"]!!.jsonObject
    private fun JsonObject.text(key: String): String = this[key]!!.jsonPrimitive.content
    private fun JsonObject.number(key: String): Int = this[key]!!.jsonPrimitive.int

    // --- what every screen reads ------------------------------------------------------------------

    @Test
    fun `the cards of the demo morning fill every screen`() = runTest {
        val cards = exchange("cards") { api.cards() }
        assertEquals("Demo Student", cards.student?.name)
        assertEquals(6, cards.dueThisWeek.size)
        assertTrue(cards.dueThisWeek.all { it.id > 0 && !it.title.isNullOrBlank() && it.dueAt != null })
        assertTrue(cards.materials.isNotEmpty() && cards.opportunities.isNotEmpty())
        assertTrue("placement drives carry their details", cards.opportunities.any { !it.details.isNullOrBlank() })
        assertEquals(5, cards.classesToday.size) // a Monday
        assertTrue(cards.attendance.connected && cards.attendance.subjects.isNotEmpty())
        assertTrue(cards.attendance.subjects.all { it.name.isNotBlank() && it.held > 0 })
        assertTrue(cards.timetable.data.isNotEmpty() && cards.marks.data.isNotEmpty())
        assertNotNull("the What-if and placement screens need a CGPA", latestCgpa(cards))
        assertEquals("demo", cards.mail.mode)
        assertTrue(cards.subjects.isNotEmpty())
    }

    @Test
    fun `once the student has done things the cards show them`() = runTest {
        val cards = exchange("cards_busy") { api.cards() }
        assertEquals("add_to_calendar", cards.approvals.single().action)
        assertNotNull(cards.approvals.single().itemId)
        assertTrue(cards.approvals.single().token.isNotBlank())
        val reminder = cards.reminders.first()
        assertTrue(reminder.id > 0 && reminder.firesAt != null && reminder.itemId != null)
        assertEquals("needs_review", cards.needsReview.single().status)
        assertTrue(cards.audit.isNotEmpty() && cards.audit.all { it.tool.isNotBlank() && it.decision.isNotBlank() })
    }

    @Test
    fun `the briefing, settings and outbox read as sent`() = runTest {
        val briefing = exchange("briefing") { api.briefing() }
        assertTrue(briefing.greeting.startsWith("Good morning"))
        assertTrue(briefing.sections.isNotEmpty() && briefing.sections.all { it.title.isNotBlank() })
        assertTrue(briefing.text.isNotBlank())

        val settings = exchange("settings") { api.settings() }
        assertTrue(settings.voice.assistant)
        assertTrue(settings.google.configured)
        assertEquals("22:00", settings.calls.quietStart)

        val outbox = exchange("notifications") { api.notifications(after = 0) }
        assertTrue(outbox.notifications.all { it.id > 0 && it.title.isNotBlank() && it.body.isNotBlank() })
        val reminder = outbox.notifications.single { it.reminderId != null }
        assertEquals("reminder", reminder.kind)
        assertNotNull(reminder.itemId)
        assertEquals(outbox.notifications.maxOf { it.id }, outbox.latestId)
    }

    @Test
    fun `the library opens a shelf and a file`() = runTest {
        val tree = exchange("tool_list_library") { api.library() }
        assertTrue(tree.available && tree.subjects.any { it.total > 0 })
        val ask = args("tool_list_library_files")
        val page = exchange("tool_list_library_files") {
            api.libraryFiles(ask.number("subject_id"), ask.text("shelf"), unsorted = false, offset = 0)
        }
        assertTrue(page.files.isNotEmpty() && page.files.all { it.title.isNotBlank() })
        val opened = exchange("tool_open_file") { api.openFile(args("tool_open_file").number("file_id")) }
        assertTrue(opened.available && !opened.url.isNullOrBlank())
        val note = exchange("tool_open_note") { api.openFile(args("tool_open_note").number("file_id")) }
        assertEquals("note", note.kind)
        assertTrue(!note.title.isNullOrBlank() && !note.text.isNullOrBlank())
    }

    @Test
    fun `without the bot's library, Files says why`() = runTest {
        val tree = exchange("tool_list_library_unavailable") { api.library() }
        assertTrue(!tree.available && !tree.reason.isNullOrBlank())
        val ask = args("tool_list_library_files_unavailable")
        val page = exchange("tool_list_library_files_unavailable") {
            api.libraryFiles(ask.number("subject_id"), ask.text("shelf"), unsorted = false, offset = 0)
        }
        assertTrue(!page.available && page.reason == tree.reason)
        val file = exchange("tool_open_file_unavailable") { api.openFile(args("tool_open_file_unavailable").number("file_id")) }
        assertTrue(!file.available && file.reason == tree.reason)
    }

    @Test
    fun `ask and the voice assistant`() = runTest {
        val answer = exchange("ask") { api.ask(body("ask").text("question")) }
        assertTrue(answer.answer.startsWith("Due this week"))
        assertTrue(answer.route.isNotBlank() && answer.tools.isNotEmpty())

        val voice = exchange("voice_session") { api.voiceSession() }
        assertTrue(voice.available && voice.signedUrl!!.startsWith("wss://"))
        assertTrue(voice.tools.isNotEmpty() && "student_name" in voice.dynamicVariables)
        val off = exchange("voice_unavailable") { api.voiceSession() }
        assertTrue(!off.available && !off.reason.isNullOrBlank())
    }

    // --- what a tap changes ---------------------------------------------------------------------

    @Test
    fun `reminders, done and the calendar go through the gateway`() = runTest {
        val set = args("tool_set_reminder")
        val reminder = exchange("tool_set_reminder") {
            api.setReminder(set.number("item_id"), set.number("before_minutes"), set.text("channel"))
        }
        assertTrue(reminder.id > 0 && reminder.firesAt != null && !reminder.title.isNullOrBlank())
        exchange("tool_mark_done") { api.markDone(args("tool_mark_done").number("item_id")) }
        exchange("tool_reopen") { api.reopen(args("tool_reopen").number("item_id")) }
        exchange("tool_cancel_reminder") { api.cancelReminder(args("tool_cancel_reminder").number("reminder_id")) }
        val calendar = exchange("tool_add_to_calendar") { api.tool("add_to_calendar", args("tool_add_to_calendar")) }
        assertEquals("approval_needed", calendar.status)
        assertTrue(!calendar.message.isNullOrBlank())
    }

    @Test
    fun `sharing files what the student said, or leaves it to sort`() = runTest {
        val filed = exchange("share") { api.share(body("share")) }
        assertEquals("filed", filed.status)
        assertEquals("DBMS assignment 4", filed.item?.title)
        val unsorted = exchange("share_unsorted") { api.share(body("share_unsorted")) }
        assertEquals("needs_review", unsorted.status)
    }

    @Test
    fun `calls, mail and the demo tour`() = runTest {
        val calls = exchange("call_settings") { api.setCalls(enabled = true) }
        assertTrue(calls.enabled && calls.consentAt != null)
        val test = exchange("call_test") { api.testCall() }
        assertTrue(test.callId > 0 && test.status.isNotBlank())
        val quiet = exchange("call_quiet") { api.setCalls(quietStart = "08:00", quietEnd = "09:00") }
        assertEquals("08:00" to "09:00", quiet.quietStart to quiet.quietEnd)
        val refused = exchange("call_test_refused") { api.testCall() }
        assertEquals("refused" to "quiet_hours", refused.status to refused.reason)
        val history = exchange("calls") { api.callHistory() }
        assertEquals(listOf(refused.callId, test.callId), history.calls.map { it.id })
        assertEquals("quiet_hours", history.calls.first().reason)

        val mail = exchange("mail_check") { api.checkMail() }
        assertEquals("demo", mail.mode)
        assertTrue(mail.mail.checkedAt != null)

        val tour = exchange("demo_forward") { api.demoForward("quiz") }
        assertEquals(200, tour.webhookStatus)
        assertEquals("quiz", tour.kind)
        assertTrue(!tour.filed?.title.isNullOrBlank())
    }

    @Test
    fun `the server's refusals reach the student in its own words, with the code`() = runTest {
        for ((name, call) in listOf<Pair<String, suspend () -> Unit>>(
            "error_demo_account" to { api.saveProfile(ProfileForm(name = body("error_demo_account").text("name"))) },
            "error_demo_google" to { api.googleStart() },
        )) {
            val recorded = fixture(name)["response"]!!.jsonObject
            try {
                exchange(name, call)
                fail("$name should have been refused")
            } catch (e: ApiException) {
                assertEquals(name, 403, e.status)
                assertEquals(name, recorded.text("detail"), e.detail)
                assertEquals(name, "demo_account", e.code)
            }
        }
    }

    // --- a student's own account -------------------------------------------------------------------

    @Test
    fun `signing up, the profile, tokens, connections and WhatsApp`() = runTest {
        assertTrue(exchange("username_check") { api.usernameCheck("asha.k") }.available)
        val form = ProfileForm(
            username = "asha.k", name = "Asha K", branch = "CSE", year = 3,
            subjects = listOf("Operating Systems", "Computer Networks"),
        )
        assertEquals("the app sends what the server was tested with", body("me_save"), form.toJson())
        val saved = exchange("me_save") { api.saveProfile(form) }
        assertTrue(saved.onboarded && !saved.demo)
        assertEquals("asha.k", saved.profile?.username)
        assertEquals(listOf("Operating Systems", "Computer Networks"), saved.profile?.subjects)

        val me = exchange("me") { api.me() }
        assertEquals("Asha K", me.profile?.name)
        val token = exchange("me_token") { api.newPersonalToken() }
        assertTrue(token.token.startsWith("75p_") && token.mcpUrl.endsWith("/mcp"))
        val apps = exchange("me_connections") { api.connections() }
        assertEquals("Claude Code", apps.connections.single().label)
        assertTrue(apps.connections.single().connectedAt != null)
        val id = apps.connections.single().id
        assertTrue(exchange("me_disconnect") { api.disconnect(id) })
        val link = exchange("me_whatsapp") { api.linkWhatsApp() }
        assertTrue(link.code.isNotBlank() && link.message.contains(link.code) && link.botNumber != null)
        assertTrue(exchange("me_whatsapp_delete") { api.unlinkWhatsApp() }.onboarded)
    }

    @Test
    fun `connecting and disconnecting Google`() = runTest {
        assertTrue(exchange("google_start") { api.googleStart() }.url.startsWith("https://accounts.google.com/"))
        val finish = body("google_finish")
        val connected = exchange("google_finish") { api.googleFinish(finish.text("code"), finish.text("state")) }
        assertTrue(connected.connected && connected.google.connected && connected.google.gmail)
        assertNotNull(connected.google.email)
        val gone = exchange("google_disconnect") { api.googleDisconnect() }
        assertTrue(gone.disconnected && !gone.google.connected)
    }

    @Test
    fun `the sign-in settings`() = runTest {
        val config = exchange("auth_config") { api.authConfig() }
        assertTrue(config.usable && config.usernameLogin)
        assertEquals(8, config.passwordMinLength)
    }

    // --- across every answer ------------------------------------------------------------------------

    @Test
    fun `every recorded answer is read by a model here, and every model is tested`() {
        val files = contractDir().listFiles { f -> f.extension == "json" }!!.map { it.nameWithoutExtension }.toSet()
        assertEquals("fixtures without a model, or models without a fixture", files, MODELS.keys)
    }

    @Test
    fun `nothing reads only because the app is lenient`() {
        // The app's Json turns a null where it wants a value into the default, and ignores keys it
        // doesn't know. Here only the second is allowed: a null the app would quietly hide fails.
        val strict = Json { ignoreUnknownKeys = true; explicitNulls = false; coerceInputValues = false }
        val problems = mutableListOf<String>()
        for ((name, parts) in MODELS) for ((pointer, model) in parts) {
            val element = fixture(name)["response"]!!.at(pointer) ?: continue
            runCatching { strict.decodeFromJsonElement(model, element) }
                .onFailure { problems += "$name${pointer?.let { ".$it" } ?: ""}: ${it.message?.lines()?.first()}" }
        }
        assertTrue(problems.joinToString("\n"), problems.isEmpty())
    }

    @Test
    fun `every field the app reads is one the server sends`() {
        val coverage = Coverage()
        for ((name, parts) in MODELS) for ((pointer, model) in parts) {
            fixture(name)["response"]!!.at(pointer)?.let { coverage.walk(model.descriptor, it) }
        }
        val missing = coverage.declared.flatMap { (model, fields) ->
            (fields - coverage.sent[model].orEmpty() - NOT_SENT_HERE[model].orEmpty()).map { "$model.$it" }
        }.sorted()
        // For the report: what the server sends that no model reads (fine; maybe worth a look).
        coverage.ignored.filterValues { it.isNotEmpty() }.toSortedMap().forEach { (model, keys) ->
            println("contract: ${model.substringAfterLast('.')} ignores ${keys.sorted().joinToString()}")
        }
        assertTrue("the app reads these, but no recorded answer carries them:\n" + missing.joinToString("\n"), missing.isEmpty())
    }

    private companion object {
        fun contractDir(): File = File(ContractTest::class.java.getResource("/contract")!!.toURI())

        fun fixture(name: String): JsonObject =
            AppJson.parseToJsonElement(File(contractDir(), "$name.json").readText()).jsonObject

        fun JsonElement.at(pointer: String?): JsonElement? = if (pointer == null) this else jsonObject[pointer]

        /** Each recorded answer and the models the app reads it with (a tool's `result` separately). */
        val MODELS: Map<String, List<Pair<String?, KSerializer<*>>>> = mapOf(
            "auth_config" to listOf(null to AuthConfig.serializer()),
            "cards" to listOf(null to Cards.serializer()),
            "cards_busy" to listOf(null to Cards.serializer()),
            "briefing" to listOf(null to Briefing.serializer()),
            "settings" to listOf(null to AppSettings.serializer()),
            "notifications" to listOf(null to Outbox.serializer()),
            "tool_list_library" to listOf(null to ToolResponse.serializer(), "result" to LibraryTree.serializer()),
            "tool_list_library_files" to listOf(null to ToolResponse.serializer(), "result" to FilePage.serializer()),
            "tool_open_file" to listOf(null to ToolResponse.serializer(), "result" to OpenedFile.serializer()),
            "tool_open_note" to listOf(null to ToolResponse.serializer(), "result" to OpenedFile.serializer()),
            "tool_list_library_unavailable" to listOf(null to ToolResponse.serializer(), "result" to LibraryTree.serializer()),
            "tool_list_library_files_unavailable" to listOf(null to ToolResponse.serializer(), "result" to FilePage.serializer()),
            "tool_open_file_unavailable" to listOf(null to ToolResponse.serializer(), "result" to OpenedFile.serializer()),
            "ask" to listOf(null to AskAnswer.serializer()),
            "voice_session" to listOf(null to VoiceSession.serializer()),
            "voice_unavailable" to listOf(null to VoiceSession.serializer()),
            "tool_set_reminder" to listOf(null to ToolResponse.serializer(), "result" to SetReminderResult.serializer()),
            "tool_mark_done" to listOf(null to ToolResponse.serializer()),
            "tool_reopen" to listOf(null to ToolResponse.serializer()),
            "tool_cancel_reminder" to listOf(null to ToolResponse.serializer()),
            "tool_add_to_calendar" to listOf(null to ToolResponse.serializer()),
            "share" to listOf(null to ShareResult.serializer()),
            "share_unsorted" to listOf(null to ShareResult.serializer()),
            "call_settings" to listOf(null to CallSettings.serializer()),
            "call_test" to listOf(null to CallOutcome.serializer()),
            "call_quiet" to listOf(null to CallSettings.serializer()),
            "call_test_refused" to listOf(null to CallOutcome.serializer()),
            "calls" to listOf(null to CallHistory.serializer()),
            "mail_check" to listOf(null to MailCheckResult.serializer()),
            "demo_forward" to listOf(null to DemoForward.serializer()),
            // Refusals are read by Http itself (detail and code), checked above.
            "error_demo_account" to emptyList(),
            "error_demo_google" to emptyList(),
            "username_check" to listOf(null to UsernameCheck.serializer()),
            "me_save" to listOf(null to Me.serializer()),
            "me" to listOf(null to Me.serializer()),
            "me_token" to listOf(null to PersonalToken.serializer()),
            "me_connections" to listOf(null to McpConnections.serializer()),
            "me_disconnect" to listOf(null to Disconnected.serializer()),
            "me_whatsapp" to listOf(null to WhatsAppLink.serializer()),
            "me_whatsapp_delete" to listOf(null to Me.serializer()),
            "google_start" to listOf(null to GoogleStart.serializer()),
            "google_finish" to listOf(null to GoogleFinish.serializer()),
            "google_disconnect" to listOf(null to GoogleDisconnect.serializer()),
        )

        /** Fields the app reads that the demo morning has no answer carrying, each with why. */
        val NOT_SENT_HERE: Map<String, Set<String>> = mapOf()
    }
}

/** Walks an answer with the model that reads it: which fields each model class declares, which
 * the server's objects carried, and which keys the server sent that the model doesn't read. */
@OptIn(ExperimentalSerializationApi::class)
private class Coverage {
    val declared = mutableMapOf<String, Set<String>>()
    val sent = mutableMapOf<String, MutableSet<String>>()
    val ignored = mutableMapOf<String, MutableSet<String>>()

    fun walk(model: SerialDescriptor, element: JsonElement) {
        when (model.kind) {
            StructureKind.CLASS -> if (element is JsonObject) {
                val name = model.serialName.removeSuffix("?")
                val fields = (0 until model.elementsCount).map { model.getElementName(it) }.toSet()
                declared[name] = fields
                sent.getOrPut(name) { mutableSetOf() } += element.keys.filter { it in fields }
                ignored.getOrPut(name) { mutableSetOf() } += element.keys.filter { it !in fields }
                for (i in 0 until model.elementsCount) {
                    element[model.getElementName(i)]?.let { walk(model.getElementDescriptor(i), it) }
                }
            }
            StructureKind.LIST -> if (element is JsonArray) element.forEach { walk(model.getElementDescriptor(0), it) }
            StructureKind.MAP -> if (element is JsonObject) element.values.forEach { walk(model.getElementDescriptor(1), it) }
            else -> Unit
        }
    }
}
