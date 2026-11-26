package com.sevenfive.app

import com.sevenfive.app.data.AppJson
import com.sevenfive.app.data.AppSettings
import com.sevenfive.app.data.Briefing
import com.sevenfive.app.data.Cards
import com.sevenfive.app.data.Outbox
import com.sevenfive.app.data.VoiceSession
import com.sevenfive.app.util.Time
import com.sevenfive.app.voice.VoiceAssistant
import kotlinx.serialization.decodeFromString
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The shapes the new server features send, read exactly as the server writes them. */
class FeaturesParsingTest {
    @Test
    fun `a college mail card carries who, what, the form and the mail`() {
        val cards = AppJson.decodeFromString<Cards>(
            """{"opportunities":[{"id":9,"kind":"deadline","subject":"Miscellaneous","title":"Nimbus Systems Campus Drive",
               "due_at":"2026-11-30T17:00+05:30","status":"filed","source":"gmail","route":"mail","category":"placement",
               "organisation":"Nimbus Systems","role":"Graduate Engineer Trainee","link":"https://forms.gle/x",
               "mail_link":"https://mail.google.com/mail/u/0/#all/abc","summary":"Register by Monday.",
               "event_at":"2026-12-02T10:00+05:30","relevance":null}],
               "reminders":[{"reminder_id":1,"fires_at":"2026-11-30T15:00+05:30","title":"x","item_id":9,"channel":"call"}],
               "classes_today":[{"start":"09:00","end":"09:55","subject_code":"CS52","subject":"Database Management Systems","room":"LH-204"}],
               "mail":{"mode":"gmail","connected":true,"status":"connected","address":"s@college.edu","left_out":7,
               "checked_at":"2026-11-27T13:00+05:30","next_check_at":"2026-11-27T21:00+05:30","check_now_after":null}}"""
        )
        val card = cards.opportunities.single()
        assertTrue(card.fromMail)
        assertEquals("placement", card.category)
        assertEquals("Graduate Engineer Trainee", card.role)
        assertEquals("https://mail.google.com/mail/u/0/#all/abc", card.mailLink)
        assertEquals("2026-12-02T10:00+05:30", card.eventAt)
        assertTrue(cards.reminders.single().isCall)
        assertEquals(9, cards.reminders.single().itemId)
        assertEquals("LH-204", cards.classesToday.single().room)
        assertFalse(cards.mail.isDemo)
        assertEquals(7, cards.mail.leftOut)
    }

    @Test
    fun `an older server without the new fields still reads`() {
        val cards = AppJson.decodeFromString<Cards>("""{"due_this_week":[{"id":1,"kind":"exam","route":"llm"}],"reminders":[{"reminder_id":2}]}""")
        assertFalse(cards.dueThisWeek.single().fromMail)
        assertEquals("push", cards.reminders.single().channel)
        assertTrue(cards.mail.isDemo)
        assertTrue(cards.classesToday.isEmpty())
    }

    @Test
    fun `settings carry calls, Google and voice`() {
        val s = AppJson.decodeFromString<AppSettings>(
            """{"calls":{"enabled":true,"consent_at":"2026-11-26T10:00+05:30","quiet_start":"23:00","quiet_end":"07:00",
               "phone":"+91 ••••• •3210","live":false,"max_per_day":2,"lead_minutes":120,"max_seconds":90},
               "push":{"wakeups":false},
               "google":{"configured":true,"connected":true,"email":"s@college.edu","gmail":true,"calendar":true,"classroom":false},
               "voice":{"assistant":true,"briefing_audio":false}}"""
        )
        assertTrue(s.calls.enabled)
        assertEquals("23:00", s.calls.quietStart)
        assertEquals("+91 ••••• •3210", s.calls.phone)
        assertTrue(s.google.gmail)
        assertFalse(s.google.classroom)
        assertTrue(s.voice.assistant)
    }

    @Test
    fun `a voice session is a signed url, greeting values and the tools allowed`() {
        val v = AppJson.decodeFromString<VoiceSession>(
            """{"available":true,"signed_url":"wss://api.elevenlabs.io/v1/convai/conversation?conversation_signature=s",
               "dynamic_variables":{"student_name":"Demo","today":"Friday 27 November 2026"},
               "tools":["due_this_week","attendance"],"max_seconds":300}"""
        )
        assertEquals("Demo", v.dynamicVariables["student_name"])
        assertEquals(listOf("due_this_week", "attendance"), v.tools)
        val off = AppJson.decodeFromString<VoiceSession>("""{"available":false,"reason":"The voice assistant needs ElevenLabs set up on the server."}""")
        assertFalse(off.available)
        assertNull(off.signedUrl)
    }

    @Test
    fun `the briefing and the outbox read as sent`() {
        val b = AppJson.decodeFromString<Briefing>(
            """{"day":"2026-11-27","greeting":"Good morning, Demo.","sections":[{"key":"due","title":"Due soon","lines":["Nothing is due today or tomorrow."]}],
               "classes":[],"text":"Good morning, Demo. Nothing is due today or tomorrow.","audio":{"available":true}}"""
        )
        assertTrue(b.audio.available)
        assertEquals("Due soon", b.sections.single().title)
        val o = AppJson.decodeFromString<Outbox>(
            """{"notifications":[{"id":4,"kind":"call","title":"DBMS: Lab","body":"Due Fri. We called but couldn't reach you.","item_id":2,"created_at":"x"}],"latest_id":4}"""
        )
        assertEquals("call", o.notifications.single().kind)
        assertEquals(4, o.latestId)
    }

    @Test
    fun `the voice plays pcm at the rate ElevenLabs names and refuses mu-law`() {
        assertEquals(16000, VoiceAssistant.rate("pcm_16000"))
        assertEquals(44100, VoiceAssistant.rate("pcm_44100"))
        assertNull(VoiceAssistant.rate("ulaw_8000"))
        assertNull(VoiceAssistant.rate(null))
        assertEquals("Checking what's due…", VoiceAssistant.workingLabel("due_this_week"))
    }

    @Test
    fun `a timetable time reads as a clock time`() {
        assertEquals("9:00 AM", Time.hourMinute("09:00"))
        assertEquals("2:05 PM", Time.hourMinute("14:05"))
        assertEquals("soon", Time.hourMinute("soon"))
    }
}
