"""
First-run setup. Asks for a bot token, verifies it, waits for you to message
the bot, and picks up your chat ID automatically so you never have to look
it up. Writes .env at the end.

    python setup.py
"""
from __future__ import annotations

import secrets
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


def make_setup_nonce() -> str:
    """A one-time secret that never leaves this machine except by round-
    tripping through Telegram's own deep-link mechanism."""
    return secrets.token_urlsafe(12)


def deep_link(username: str, nonce: str) -> str:
    return f"https://t.me/{username}?start={nonce}"


def extract_matching_chat_id(update: dict, nonce: str) -> int | None:
    """Returns the chat id if this update is a /start carrying exactly the
    expected nonce, else None. Pulled out as a pure function so every case
    (right payload, wrong payload, no payload, edited message, malformed
    update) is testable without a network call."""
    msg = update.get("message") or update.get("edited_message")
    if not msg or "chat" not in msg:
        return None
    text = (msg.get("text") or "").strip()
    if text != f"/start {nonce}":
        return None
    return int(msg["chat"]["id"])


def wait_for_chat_id(token: str, username: str, timeout: int = 300) -> int:
    """Waits for proof that whoever is running this script is the same
    person who will end up owning the bot, then returns their chat id.

    This project is meant to be cloned and run by anyone, so "whoever
    messages first" is the wrong trust model to ship - a bot's username is
    only unguessable for the few seconds after BotFather hands it out, and
    "first message wins" bakes that timing assumption into every install
    forever. A random nonce embedded in a Telegram deep link (t.me/<bot>?
    start=<nonce>) fixes it structurally instead: only a message carrying
    the exact nonce generated on *this* machine, for *this* run, is
    accepted. Nothing else - a stray message, a similar name, a lucky
    guess - can produce a match.
    """
    nonce = make_setup_nonce()

    # Clear any backlog first so a leftover old message can't be mistaken
    # for the answer (it never carries the fresh nonce anyway, but this
    # keeps the log clean and the wait fast).
    try:
        r = httpx.get(API.format(token=token, method="getUpdates"), timeout=15)
        updates = r.json().get("result", [])
        offset = updates[-1]["update_id"] + 1 if updates else None
    except Exception:
        offset = None

    link = deep_link(username, nonce)
    print(f"\n  Open this link to connect your account:\n\n    {link}\n")
    print("  (Tapping it sends the bot a one-time code proving it's really you.")
    print("  If it won't open, message the bot this exact text instead:")
    print(f"    /start {nonce}")
    print("  Press Ctrl+C to cancel.)\n")

    deadline = time.time() + timeout
    while time.time() < deadline:
        params = {"timeout": 20}
        if offset is not None:
            params["offset"] = offset
        try:
            r = httpx.get(API.format(token=token, method="getUpdates"), params=params, timeout=30)
            for update in r.json().get("result", []):
                chat_id = extract_matching_chat_id(update, nonce)
                if chat_id is not None:
                    print(f"  Verified (chat id {chat_id}).")
                    return chat_id
                offset = update["update_id"] + 1
        except httpx.HTTPError:
            time.sleep(2)
    fail("Timed out waiting for confirmation. Run setup again when you're ready.")


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
