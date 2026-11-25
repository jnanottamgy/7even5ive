from __future__ import annotations

from datetime import datetime

from mailfilter.fake import Attachment, build_raw
from mailfilter.mail import MailMessage, render
from mailfilter.mime import clean_link, html_to_text, parse_raw
from mailfilter.timekit import IST

WHEN = datetime(2026, 12, 1, 10, 12, tzinfo=IST)


def raw(**kwargs: object) -> bytes:
    defaults: dict[str, object] = {
        "sender": "Training & Placement Office <tpo@mockcollege.edu.in>",
        "subject": "Drive",
        "received_at": WHEN,
        "message_id": "<m1@mockcollege.edu.in>",
    }
    defaults.update(kwargs)
    return build_raw(**defaults)  # type: ignore[arg-type]


def test_plain_text_and_its_links_are_read() -> None:
    content = parse_raw(raw(plain="Register: https://forms.gle/Abc123. Thanks!"), 15_000)
    assert content.text == "Register: https://forms.gle/Abc123. Thanks!"
    assert content.links == ("https://forms.gle/Abc123",)
    assert content.sender.startswith("Training & Placement Office")
    assert content.message_id == "<m1@mockcollege.edu.in>"


def test_a_link_behind_click_here_is_written_out() -> None:
    html = '<p>To apply <a href="https://forms.gle/Hidden1">click here</a>.</p>'
    content = parse_raw(raw(html=html), 15_000)
    assert "click here <https://forms.gle/Hidden1>" in content.text
    assert content.links == ("https://forms.gle/Hidden1",)


def test_plain_text_wins_but_html_links_are_kept() -> None:
    content = parse_raw(
        raw(
            plain="Register using the button in this mail.",
            html='<a href="https://forms.gle/OnlyInHtml">Register</a>',
        ),
        15_000,
    )
    assert content.text == "Register using the button in this mail."
    assert content.links == ("https://forms.gle/OnlyInHtml",)
    mail = MailMessage("m", "t", WHEN, frozenset({"INBOX"}), content)
    assert "--- links in the mail ---\nhttps://forms.gle/OnlyInHtml" in render(mail).checkable


def test_scripts_styles_and_entities() -> None:
    text, links = html_to_text(
        "<style>p{color:red}</style><script>steal()</script><p>Fee &amp; form &lt;today&gt;</p>"
    )
    assert text == "Fee & form <today>"
    assert links == []


def test_tables_keep_cells_apart() -> None:
    text, _ = html_to_text(
        "<table><tr><th>Applications close</th><td>20 December 2026</td></tr></table>"
    )
    assert text == "Applications close 20 December 2026"


def test_encoded_subject_and_latin1_body() -> None:
    content = parse_raw(
        raw(
            subject="Résumé clinic – placement cell",
            plain="Contact Mr. José.",
            charset="iso-8859-1",
        ),
        15_000,
    )
    assert content.subject == "Résumé clinic – placement cell"
    assert content.text == "Contact Mr. José."


def test_attachments_are_named_not_read() -> None:
    content = parse_raw(
        raw(plain="PFA.", attachments=[Attachment("Schedule.pdf", b"%PDF secret deadline 9 Dec")]),
        15_000,
    )
    assert content.attachments == ("Schedule.pdf",)
    assert "secret" not in content.text


def test_mailing_lists_and_forwards_are_marked() -> None:
    bulk = parse_raw(raw(plain="x", headers=[("List-Unsubscribe", "<mailto:u@x.com>")]), 100)
    forward = parse_raw(raw(subject="Fwd: Drive", plain="see below"), 100)
    inline = parse_raw(raw(plain="hi\n---------- Forwarded message ---------\nFrom: x"), 100)
    assert bulk.bulk and not bulk.forwarded
    assert forward.forwarded and inline.forwarded


def test_long_mail_is_cut_and_said_so() -> None:
    content = parse_raw(raw(plain="Register by 3 Dec. " + "filler " * 5000), 1_000)
    assert content.truncated
    assert content.text.startswith("Register by 3 Dec.")
    assert content.text.endswith("[... the rest of this mail was cut ...]")
    assert len(content.text) < 1_100


def test_invisible_characters_and_spacing_are_cleaned() -> None:
    content = parse_raw(raw(plain="Last date:​ 3  Dec\r\n\r\n\r\n\r\nBye"), 100)
    assert content.text == "Last date: 3 Dec\n\nBye"


def test_trailing_punctuation_is_not_part_of_a_link() -> None:
    assert clean_link("https://forms.gle/Abc).") == "https://forms.gle/Abc"
    assert clean_link("https://en.example.org/wiki/A_(b)") == "https://en.example.org/wiki/A_(b)"


def test_render_keeps_the_received_line_out_of_what_is_checked() -> None:
    content = parse_raw(raw(plain="Register by 3 Dec."), 100)
    rendered = render(MailMessage("m", "t", WHEN, frozenset({"INBOX"}), content))
    assert rendered.for_claude.startswith("Received: Tue 1 Dec 2026, 10:12 AM (India time)\n")
    assert "Received" not in rendered.checkable
    assert rendered.for_claude.endswith(rendered.checkable)
