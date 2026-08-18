"""
JSON string catalogues keyed by string ID. English is the fallback for any
key missing from another language, so a partial translation degrades to
readable English rather than a KeyError or a raw key name.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_DIR = Path(__file__).resolve().parent
FALLBACK_LANG = "en"

_catalogues: dict[str, dict[str, str]] = {}


def _load(lang: str) -> dict[str, str]:
    if lang not in _catalogues:
        path = _DIR / f"{lang}.json"
        if not path.exists():
            log.warning("i18n catalogue missing for %r, falling back to %r", lang, FALLBACK_LANG)
            _catalogues[lang] = {}
        else:
            _catalogues[lang] = json.loads(path.read_text(encoding="utf-8"))
    return _catalogues[lang]


def available_languages() -> list[str]:
    return sorted(p.stem for p in _DIR.glob("*.json"))


def t(key: str, lang: str = FALLBACK_LANG, **params) -> str:
    catalogue = _load(lang)
    fallback = _load(FALLBACK_LANG)
    template = catalogue.get(key)
    if template is None:
        template = fallback.get(key)
    if template is None:
        log.warning("missing i18n key: %r", key)
        return key
    try:
        return template.format(**params)
    except (KeyError, IndexError) as e:
        log.warning("i18n key %r template/params mismatch: %s", key, e)
        return template


def make_translator(lang: str):
    """Returns a bound t(key, **params) using the given language, so call
    sites don't have to thread `lang` through every call."""
    def _t(key: str, **params) -> str:
        return t(key, lang=lang, **params)
    return _t
