"""
make_translator()'s returned callable is `_t(key, **params)` — "key" is the
name of its own first positional parameter, the translation-string id. Any
call site passing key=... as a template parameter (e.g. _t("key_sent",
key=pressed_key)) collides with it and raises TypeError, which is exactly
what happened here: the inline keypad's "Sent: X" confirmation crashed on
every single press. The keystroke itself had already gone through by that
point, so the visible symptom was Telegram's button spinner never
resolving — indistinguishable from the whole keypad being broken.
"""
import re
from pathlib import Path

from tether.i18n import make_translator

SRC = Path(__file__).resolve().parent.parent / "src" / "tether"


def test_translator_call_signature_reserves_key_as_first_positional():
    _t = make_translator("en")
    # this is the exact call shape that used to crash
    result = _t("key_sent", key_name="1")
    assert "1" in result


def test_no_call_site_passes_key_as_a_template_param():
    """A grep-level guard: nothing in the codebase should call _t(..., key=...)
    since "key" is _t's own first positional argument name."""
    offenders = []
    pattern = re.compile(r'_t\(\s*["\'][^"\']+["\']\s*,\s*key=')
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(SRC)))
    assert not offenders, f"these files call _t(..., key=...), which collides with _t's own parameter: {offenders}"
