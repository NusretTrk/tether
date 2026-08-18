"""
Plain-script notify for anything that doesn't speak MCP (opencode, cron,
one-off scripts). Reads the same .env as the bot — no token on the command
line, no secrets to re-teach to every tool.

Usage:
    python tools/notify.py "message text"
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx

from tether.config import Config


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python tools/notify.py \"message text\"", file=sys.stderr)
        raise SystemExit(1)
    message = " ".join(sys.argv[1:])
    cfg = Config.load()
    resp = httpx.post(
        f"https://api.telegram.org/bot{cfg.secrets.bot_token}/sendMessage",
        data={"chat_id": cfg.secrets.chat_id, "text": message},
        timeout=15,
    )
    resp.raise_for_status()
    print("sent")


if __name__ == "__main__":
    main()
