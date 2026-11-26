package com.sevenfive.app

import com.sevenfive.app.data.AppJson
import com.sevenfive.app.data.FilePage
import com.sevenfive.app.data.LibraryTree
import com.sevenfive.app.data.OpenedFile
import kotlinx.serialization.decodeFromString
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The Files tab's three responses, in the exact shape the bot's library API returns. */
class LibraryParsingTest {

    @Test
    fun `parses the library tree with shelf counts`() {
        val tree = AppJson.decodeFromString<LibraryTree>(
            """{"subjects":[{"id":1,"name":"Database Management Systems","shelves":[
               {"shelf":"material","label":"Material","files":2},
               {"shelf":"pyq","label":"PYQ & Questions","files":1},
               {"shelf":"info","label":"Info & Admin","files":0}]}],"unsorted":3}""",
        )
        assertTrue(tree.available)
        assertEquals("Database Management Systems", tree.subjects.single().name)
        assertEquals(3, tree.subjects.single().total)
        assertEquals(3, tree.unsorted)
    }

    @Test
    fun `an unreachable library says so instead of failing`() {
        val tree = AppJson.decodeFromString<LibraryTree>(
            """{"available":false,"reason":"The library can't be reached right now."}""",
        )
        assertFalse(tree.available)
        assertTrue(tree.subjects.isEmpty())
    }

    @Test
    fun `parses a page of files and the next offset`() {
        val page = AppJson.decodeFromString<FilePage>(
            """{"files":[{"id":103,"kind":"file","title":"CIE-1 question paper",
               "filename":"DBMS_CIE1_2025.pdf","mime_type":"application/pdf","shelf":"pyq",
               "subject_id":1,"created_at":"2026-11-20T10:00:00+05:30"}],"next_offset":50}""",
        )
        assertEquals("application/pdf", page.files.single().mimeType)
        assertEquals(50, page.nextOffset)
    }

    @Test
    fun `an opened file is a short link and a note is its text`() {
        val file = AppJson.decodeFromString<OpenedFile>(
            """{"kind":"file","url":"https://r2.example/x?sig=1","expires_in":300,
               "filename":"Unit 3.pdf","mime_type":"application/pdf"}""",
        )
        assertEquals("https://r2.example/x?sig=1", file.url)
        val note = AppJson.decodeFromString<OpenedFile>(
            """{"kind":"note","title":"Lab moved","text":"Thursday, 2 pm"}""",
        )
        assertNull(note.url)
        assertEquals("Thursday, 2 pm", note.text)
    }
}
