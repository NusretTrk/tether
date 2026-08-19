"""
Validates Telegram's `initData` string - the one thing standing between
the Mini App's data endpoints and anyone who stumbles onto the ngrok URL.
The URL itself is NOT a secret (ngrok's free static domain is guessable
by design - it's meant to be memorable), so every single API request has
to prove it came from a genuine Telegram WebApp launch for THIS bot and
THIS chat, not just "knew the URL".

Algorithm is Telegram's own documented one, not invented here:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
  1. Pull `hash` out of the query-string-shaped initData, HMAC-SHA256 the
     rest (sorted, "\\n"-joined "key=value" pairs) with a secret key
     derived from the bot token, compare to the extracted hash.
  2. Nobody without the bot token can produce a matching hash - forging
     one is exactly as hard as guessing the token itself.

Two more checks beyond that HMAC, specific to tether's single-owner model:
  - `auth_date` must be recent, so a captured/logged initData string can't
    be replayed indefinitely (Telegram's own reference examples use a
    24h window; kept the same rather than inventing a tighter number that
    might reject a Mini App session someone genuinely left open a while).
  - The signed `user.id` must equal the one authorized chat_id. This is a
    private 1:1 bot chat, so user_id and chat_id are the same number (see
    setup.py) - anyone else's initData, even if perfectly validly signed
    for a DIFFERENT chat talking to this same bot, is still rejected.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

DEFAULT_MAX_AGE_SEC = 86400  # 24h, matching Telegram's own reference examples


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    reason: str
    user_id: int | None = None


def validate_init_data(
    init_data: str,
    bot_token: str,
    expected_chat_id: int,
    max_age_sec: int = DEFAULT_MAX_AGE_SEC,
    now: float | None = None,
) -> AuthResult:
    if not init_data or not bot_token:
        return AuthResult(False, "missing_input")

    try:
        pairs = parse_qsl(init_data, strict_parsing=True)
    except ValueError:
        return AuthResult(False, "malformed_init_data")

    data = dict(pairs)
    received_hash = data.pop("hash", None)
    if not received_hash:
        return AuthResult(False, "missing_hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        return AuthResult(False, "bad_signature")

    auth_date_raw = data.get("auth_date")
    if auth_date_raw is None or not auth_date_raw.isdigit():
        return AuthResult(False, "missing_auth_date")
    now = time.time() if now is None else now
    age = now - int(auth_date_raw)
    if age < 0 or age > max_age_sec:
        return AuthResult(False, "stale_init_data")

    user_raw = data.get("user")
    if not user_raw:
        return AuthResult(False, "missing_user")
    try:
        user_id = json.loads(user_raw).get("id")
    except (json.JSONDecodeError, AttributeError):
        return AuthResult(False, "malformed_user")
    if user_id is None:
        return AuthResult(False, "malformed_user")

    if int(user_id) != int(expected_chat_id):
        return AuthResult(False, "wrong_chat", user_id=user_id)

    return AuthResult(True, "ok", user_id=user_id)
