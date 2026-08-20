"""
Second credential path into the Mini App, for opening it as a bookmarked
web app (e.g. iOS "Add to Home Screen") outside a real Telegram WebApp
launch - `Telegram.WebApp.initData` (miniapp/auth.py) simply does not
exist in that context, there is no Telegram session to sign it.

Generated on request (/miniapp link), sent to the owner as a URL
fragment: `https://<domain>/#t=<token>`. A URL fragment is never sent to
any server by the browser (hard HTTP/URL-spec guarantee) - unlike a query
string, it never reaches ngrok's or tether's own request logs, and
frontend.py reads it purely client-side to build the same
`Authorization` header initData already uses (`Bearer <token>` instead of
`tma <initData>`), so server.py has one extra branch, not a parallel
auth system.

Only the SHA-256 hash is ever persisted (state/web_token.json, gitignored
- see persistence.py for the same STATE_DIR convention) - if that file
somehow leaked, it would not itself grant access, same reasoning as never
storing a password in cleartext. Single active token by design (this is
a single-owner bot): requesting a new link invalidates whatever link was
sent before, and /miniapp revoke clears it outright without issuing a
new one.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets as _secrets
from pathlib import Path

log = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "state"
TOKEN_PATH = STATE_DIR / "web_token.json"

TOKEN_BYTES = 32  # 256 bits - guessing this is not a realistic attack, unlike a short PIN


def generate() -> str:
    return _secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify(raw: str | None, stored_hash: str | None) -> bool:
    if not raw or not stored_hash:
        return False
    return hmac.compare_digest(hash_token(raw), stored_hash)


def save_hash(hash_hex: str) -> None:
    try:
        STATE_DIR.mkdir(exist_ok=True)
        tmp = TOKEN_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"hash": hash_hex}), encoding="utf-8")
        tmp.replace(TOKEN_PATH)
    except OSError:
        log.warning("could not persist web token hash", exc_info=True)


def load_hash() -> str | None:
    if not TOKEN_PATH.exists():
        return None
    try:
        data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    hash_hex = data.get("hash")
    return hash_hex if isinstance(hash_hex, str) and hash_hex else None


def clear() -> None:
    try:
        TOKEN_PATH.unlink(missing_ok=True)
    except OSError:
        log.warning("could not remove web token file", exc_info=True)


def issue() -> str:
    """Generates a fresh token, persists only its hash, returns the raw
    token (this is the one and only moment the raw value exists outside
    the owner's own Telegram client - never logged, never returned
    again)."""
    raw = generate()
    save_hash(hash_token(raw))
    return raw
