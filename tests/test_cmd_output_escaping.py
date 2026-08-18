"""
Command output is attacker-influenced in the sense that it is whatever a
program printed, and it goes into a formatted Telegram message. Markdown
code fences break on unclosed ``` - and the 4000 char truncation can create
one by itself - so output is sent as HTML with the content escaped.
"""
import html

from tether.i18n import t


def _render(output: str) -> str:
    return t("cmd_output", lang="en", output=html.escape(output))


def test_output_is_wrapped_in_pre_not_markdown_fences():
    rendered = _render("hello")
    assert rendered.startswith("<pre>") and rendered.endswith("</pre>")
    assert "```" not in rendered


def test_unclosed_code_fence_does_not_leak_into_markup():
    # This exact payload made Telegram return 400 with Markdown parse mode.
    rendered = _render("```\nunclosed")
    assert "```" in rendered  # preserved as literal text
    assert rendered.count("<pre>") == 1 and rendered.count("</pre>") == 1


def test_html_in_output_is_escaped_not_interpreted():
    rendered = _render("<script>alert(1)</script>")
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_closing_pre_in_output_cannot_break_out():
    rendered = _render("</pre><b>injected</b>")
    assert rendered.count("</pre>") == 1  # only the real closing tag
    assert "<b>" not in rendered


def test_ampersand_escaped_first():
    rendered = _render("a & b")
    assert "&amp;" in rendered


def test_error_template_also_escapes():
    rendered = t("cmd_error", lang="en", error=html.escape("<bad> & 'worse'"))
    assert "<bad>" not in rendered
    assert "&lt;bad&gt;" in rendered
