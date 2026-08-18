"""
One-shot token redaction for existing log files. The old bot.py logged every
outbound Telegram HTTP request at INFO level, which put the bot token in the
URL on every line — this rewrites matching files in place.

Usage:
    python tools/scrub_logs.py [path-or-glob ...]

With no arguments, scrubs bot.log, bot.log.1, bot.log.2 in the parent
directory (the old bot's log location).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_TOKEN_RE = re.compile(r"bot\d{6,12}:[A-Za-z0-9_-]{30,50}")


def scrub_file(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8", errors="replace")
    redacted, count = _TOKEN_RE.subn("bot***REDACTED***", text)
    if count:
        path.write_text(redacted, encoding="utf-8")
    return count


def main() -> None:
    targets = sys.argv[1:]
    if not targets:
        parent = Path(__file__).resolve().parent.parent.parent
        targets = [str(p) for p in parent.glob("bot.log*")]

    if not targets:
        print("No log files found to scrub.")
        return

    total = 0
    for t in targets:
        for path in Path().glob(t) if any(c in t for c in "*?[") else [Path(t)]:
            n = scrub_file(path)
            if n:
                print(f"{path}: redacted {n} occurrence(s)")
                total += n
            elif path.exists():
                print(f"{path}: nothing to redact")
    print(f"Done. {total} total occurrence(s) redacted.")


if __name__ == "__main__":
    main()
