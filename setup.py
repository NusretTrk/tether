"""
First-run setup. Asks for a bot token, verifies it, waits for you to message
the bot, and picks up your chat ID automatically so you never have to look
it up. Writes .env at the end.

    python setup.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

ENV_PATH = Path(__file__).resolve().parent / ".env"
API = "https://api.telegram.org/bot{token}/{method}"


def fail(msg: str) -> None:
    print(f"\n  {msg}\n")
    sys.exit(1)


def verify_token(token: str) -> str:
    """Returns the bot's @username, or exits with a readable error."""
    try:
        r = httpx.get(API.format(token=token, method="getMe"), timeout=15)
    except httpx.HTTPError as e:
        fail(f"Couldn't reach Telegram: {e}")
    if r.status_code == 401:
        fail("Telegram rejected that token. Check you copied all of it from @BotFather.")
    if r.status_code != 200:
        fail(f"Telegram returned {r.status_code}: {r.text[:200]}")
    return r.json()["result"]["username"]


def wait_for_chat_id(token: str, username: str, timeout: int = 300) -> int:
    """Polls getUpdates until the user messages the bot, then returns their id."""
    # Clear any backlog first so an old message doesn't pick the wrong chat.
    try:
        r = httpx.get(API.format(token=token, method="getUpdates"), timeout=15)
        updates = r.json().get("result", [])
        offset = updates[-1]["update_id"] + 1 if updates else None
    except Exception:
        offset = None

    print(f"\n  Now open Telegram, find @{username}, and send it any message.")
    print("  (Press Ctrl+C to cancel.)\n")

    deadline = time.time() + timeout
    while time.time() < deadline:
        params = {"timeout": 20}
        if offset is not None:
            params["offset"] = offset
        try:
            r = httpx.get(API.format(token=token, method="getUpdates"), params=params, timeout=30)
            for update in r.json().get("result", []):
                msg = update.get("message") or update.get("edited_message")
                if msg and "chat" in msg:
                    chat = msg["chat"]
                    name = chat.get("first_name") or chat.get("title") or "?"
                    print(f"  Got a message from {name} (id {chat['id']}).")
                    return int(chat["id"])
                offset = update["update_id"] + 1
        except httpx.HTTPError:
            time.sleep(2)
    fail("Timed out waiting for a message. Run setup again when you're ready.")


def main() -> None:
    print("\n  tether setup\n  " + "-" * 40)

    if ENV_PATH.exists():
        answer = input(f"\n  .env already exists. Overwrite it? [y/N] ").strip().lower()
        if answer != "y":
            print("\n  Left it alone. Nothing changed.\n")
            return

    print("\n  1. Open Telegram and talk to @BotFather")
    print("  2. Send /newbot and follow the prompts")
    print("  3. Copy the HTTP API token it gives you\n")
    token = input("  Paste the token here: ").strip()
    if not token:
        fail("No token entered.")

    username = verify_token(token)
    print(f"\n  Token works — this is @{username}.")

    chat_id = wait_for_chat_id(token, username)

    ENV_PATH.write_text(f"BOT_TOKEN={token}\nCHAT_ID={chat_id}\n", encoding="utf-8")
    print(f"\n  Wrote {ENV_PATH.name}. This file holds your token — it's gitignored, keep it private.")
    print("\n  Start the bot with:  python run.py\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.\n")
