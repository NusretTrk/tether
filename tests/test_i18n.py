"""i18n completeness: every language must have every key en.json has, so a
partial translation degrades to readable English rather than a raw key
name — never a KeyError."""
import json
from pathlib import Path

import pytest

from tether.i18n import FALLBACK_LANG, available_languages, t

I18N_DIR = Path(__file__).resolve().parent.parent / "src" / "tether" / "i18n"


def _load(lang: str) -> dict:
    return json.loads((I18N_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def test_all_languages_have_same_keys_as_english():
    base = set(_load(FALLBACK_LANG).keys())
    assert base, "en.json must not be empty"
    for lang in available_languages():
        if lang == FALLBACK_LANG:
            continue
        keys = set(_load(lang).keys())
        assert keys == base, f"{lang}.json key mismatch — missing={base - keys}, extra={keys - base}"


def test_missing_key_falls_back_to_key_name_not_exception():
    assert t("definitely_not_a_real_key") == "definitely_not_a_real_key"


def test_missing_language_falls_back_to_english():
    text_en = t("start_welcome", lang="en")
    text_unknown = t("start_welcome", lang="xx")
    assert text_unknown == text_en


def test_format_params_substituted():
    result = t("session_switched", lang="en", name="MySession")
    assert "MySession" in result


@pytest.mark.parametrize("lang", available_languages())
def test_every_catalogue_parses_as_valid_json(lang):
    data = _load(lang)
    assert isinstance(data, dict)
    for key, value in data.items():
        assert isinstance(key, str)
        assert isinstance(value, str)
