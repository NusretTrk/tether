"""Message chunking and formatting for Telegram's 4096-char limit."""
from __future__ import annotations

import re
import unicodedata

TELEGRAM_MAX_LEN = 4096
_SAFE_LEN = 4000  # leave headroom for formatting markup added after chunking

# Typographic substitutions an app's own text box can apply on the way in
# (smart quotes/dashes) that our verbatim clipboard paste never contained -
# mapped back to their plain ASCII originals before comparing.
_SMART_PUNCT = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    "…": "...",
    " ": " ",
})
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def normalize_for_comparison(text: str) -> str:
    """Ground-truth confirmation (transport/jobs.py's pending_send check)
    compares what we pasted against what the target app's own transcript
    recorded - not always byte-identical even when delivery genuinely
    succeeded, since some apps apply their own text processing (smart
    quotes/dashes, collapsing whitespace, Unicode normalization) between
    receiving a paste and writing it to their transcript. Normalizing
    both sides the same way before comparing turns those cosmetic
    differences into a match instead of a false "wasn't confirmed"
    report on a message that actually arrived fine."""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_SMART_PUNCT)
    text = _WHITESPACE_RUN_RE.sub(" ", text)
    return text.strip()


def chunk_text(text: str, max_len: int = _SAFE_LEN) -> list[str]:
    """Splits text into chunks under max_len, preferring line boundaries so
    words and (best-effort) code fences aren't split mid-line."""
    if len(text) <= max_len:
        return [text] if text else []

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        window = remaining[:max_len]
        split_at = window.rfind("\n")
        if split_at <= 0:
            split_at = max_len
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def format_code_block(text: str, language: str = "") -> str:
    return f"```{language}\n{text}\n```"


def truncate_with_notice(text: str, max_len: int, notice: str) -> str:
    """Truncates to max_len, replacing the tail with a notice (e.g. "… (N more
    chars, use /full to see the rest") rather than silently cutting content."""
    if len(text) <= max_len:
        return text
    cut = max_len - len(notice)
    return text[:max(cut, 0)] + notice
