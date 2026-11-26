package com.sevenfive.app

import android.media.AudioDeviceInfo
import com.sevenfive.app.data.ServerSettings
import com.sevenfive.app.ui.auth.AuthStep
import com.sevenfive.app.ui.components.uniqueKeys
import com.sevenfive.app.voice.VoiceAssistant
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** The small rules behind the fixes: each one pure, so it is checked here on its own. */
class AppRulesTest {
    private val online = "https://new.example"

    @Test
    fun `a build with another server moves the app, and says from where`() {
        // The older build used its own default: an account made there is on that server.
        assertEquals("https://old.example", ServerSettings.movedFrom("https://old.example", null, online, "10.0.2.2"))
        // ... or a server the student chose under it.
        assertEquals("http://192.168.1.20:8000",
            ServerSettings.movedFrom("https://old.example", "http://192.168.1.20:8000", online, "10.0.2.2"))
        // A laptop build before this online one.
        assertEquals("http://10.0.2.2:8000", ServerSettings.movedFrom("", null, online, "10.0.2.2"))
    }

    @Test
    fun `the app stays where it was when nothing really moves`() {
        assertNull(ServerSettings.movedFrom(online, null, online, "10.0.2.2")) // the same build's default
        assertNull(ServerSettings.movedFrom(null, null, online, "10.0.2.2")) // a new install
        assertNull(ServerSettings.movedFrom("https://new.example/", null, online, "10.0.2.2")) // only a slash
        // A new default, but the student had already chosen that very server.
        assertNull(ServerSettings.movedFrom("https://old.example", "https://new.example", online, "10.0.2.2"))
    }

    @Test
    fun `the sign-up and reset steps survive the app being closed`() {
        for (step in listOf(AuthStep.Login, AuthStep.SignUp, AuthStep.Code("asha@example.com"), AuthStep.Forgot,
            AuthStep.Reset("asha@example.com"))) {
            val (name, email) = AuthStep.save(step)
            assertEquals(step, AuthStep.restore(name, email))
        }
        assertEquals(AuthStep.Login, AuthStep.restore(null, null)) // nothing saved
        assertEquals(AuthStep.SignUp, AuthStep.restore("code", null)) // a code with no email starts over
        assertEquals(AuthStep.Forgot, AuthStep.restore("reset", ""))
    }

    @Test
    fun `list keys never repeat and stay with their item`() {
        assertEquals(listOf("CS301", "MA201"), uniqueKeys(listOf("CS301", "MA201")) { it })
        assertEquals(listOf("CS301", "MA201", "CS301#2", "", "#2"),
            uniqueKeys(listOf("CS301", "MA201", "CS301", "", "")) { it })
        // Re-sorted, the first CS301 keeps its key.
        assertEquals(listOf("MA201", "CS301", "CS301#2"), uniqueKeys(listOf("MA201", "CS301", "CS301")) { it })
    }

    @Test
    fun `the voice talks through what the student is wearing, else the loudspeaker`() {
        val speaker = AudioDeviceInfo.TYPE_BUILTIN_SPEAKER
        val earpiece = AudioDeviceInfo.TYPE_BUILTIN_EARPIECE
        assertEquals(1, VoiceAssistant.preferredOutput(listOf(earpiece, speaker)))
        assertEquals(2, VoiceAssistant.preferredOutput(listOf(earpiece, speaker, AudioDeviceInfo.TYPE_WIRED_HEADSET)))
        assertEquals(0, VoiceAssistant.preferredOutput(listOf(AudioDeviceInfo.TYPE_BLUETOOTH_SCO, speaker, AudioDeviceInfo.TYPE_WIRED_HEADSET)))
        assertEquals(2, VoiceAssistant.preferredOutput(listOf(speaker, earpiece, AudioDeviceInfo.TYPE_BLE_HEADSET)))
        assertNull(VoiceAssistant.preferredOutput(listOf(earpiece)))
    }
}
