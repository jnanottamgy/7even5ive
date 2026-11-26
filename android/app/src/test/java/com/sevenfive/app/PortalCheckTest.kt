package com.sevenfive.app

import com.sevenfive.app.portal.PortalCheck
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PortalCheckTest {
    @Test
    fun `a typed portal address becomes a web address`() {
        assertEquals("https://parents.msrit.edu", PortalCheck.normalise("parents.msrit.edu"))
        assertEquals("https://parents.msrit.edu/", PortalCheck.normalise("  https://parents.msrit.edu/ "))
        assertEquals("http://10.0.2.2:8765/index.php", PortalCheck.normalise("http://10.0.2.2:8765/index.php"))
    }

    @Test
    fun `what isn't a web address is refused`() {
        assertNull(PortalCheck.normalise(""))
        assertNull(PortalCheck.normalise("msrit"))
        assertNull(PortalCheck.normalise("parents msrit edu"))
    }

    @Test
    fun `pages on the portal's own site open in the test`() {
        assertTrue(PortalCheck.sameSite("parents.msrit.edu", "parents.msrit.edu", "https"))
        assertTrue(PortalCheck.sameSite("parents.msrit.edu", "exam.msrit.edu", "https"))
        assertTrue(PortalCheck.sameSite("parents.msrit.edu", "PARENTS.MSRIT.EDU.", "https"))
    }

    @Test
    fun `anything else stays out`() {
        assertFalse(PortalCheck.sameSite("parents.msrit.edu", "evil.example.com", "https"))
        assertFalse(PortalCheck.sameSite("parents.msrit.edu", "msrit.edu.evil.com", "https"))
        assertFalse(PortalCheck.sameSite("parents.msrit.edu", "parents.msrit.edu", "intent"))
        assertFalse(PortalCheck.sameSite("parents.msrit.edu", null, "https"))
    }
}
