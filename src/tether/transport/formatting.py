"""Message chunking and formatting for Telegram's 4096-char limit."""
from __future__ import annotations

TELEGRAM_MAX_LEN = 4096
_SAFE_LEN = 4000  # leave headroom for formatting markup added after chunking


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
