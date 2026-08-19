"""
auth.py is the ONLY thing standing between the Mini App's data endpoints
and anyone who finds the ngrok URL - it needs the same rigor as
recovery.py/usage_limit.py's pure decision functions, exercised against
the real HMAC algorithm end to end, not mocked.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from tether.miniapp.auth import validate_init_data

BOT_TOKEN = "123456:AAtestFakeTokenForUnitTestsOnly"
CHAT_ID = 123456789


def _sign(fields: dict, bot_token: str = BOT_TOKEN) -> str:
    """Builds a genuinely-signed initData string the same way Telegram's
    client would, so tests exercise the real verification algorithm."""
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def _fields(user_id=CHAT_ID, auth_date=None):
    return {
        "query_id": "AAF_query123",
        "user": json.dumps({"id": user_id, "first_name": "Test"}),
        "auth_date": str(int(auth_date if auth_date is not None else time.time())),
    }


def test_valid_init_data_is_accepted():
    init_data = _sign(_fields())
    result = validate_init_data(init_data, BOT_TOKEN, CHAT_ID)
    assert result.ok
    assert result.user_id == CHAT_ID
    assert result.reason == "ok"


def test_tampered_field_after_signing_is_rejected():
    init_data = _sign(_fields())
    tampered = init_data.replace(f"auth_date={_fields()['auth_date']}", "auth_date=1")
    result = validate_init_data(tampered, BOT_TOKEN, CHAT_ID)
    assert not result.ok
    assert result.reason in ("bad_signature", "stale_init_data")


def test_wrong_bot_token_cannot_verify_even_a_genuinely_signed_payload():
    """Simulates an attacker who has the bot's initData format but not
    its token - the entire point of the HMAC scheme."""
    init_data = _sign(_fields(), bot_token=BOT_TOKEN)
    result = validate_init_data(init_data, "999999:DifferentToken", CHAT_ID)
    assert not result.ok
    assert result.reason == "bad_signature"


def test_missing_hash_is_rejected():
    result = validate_init_data("query_id=abc&auth_date=123", BOT_TOKEN, CHAT_ID)
    assert not result.ok
    assert result.reason == "missing_hash"


def test_stale_init_data_is_rejected():
    old = time.time() - 100000  # well past the default 24h window
    init_data = _sign(_fields(auth_date=old))
    result = validate_init_data(init_data, BOT_TOKEN, CHAT_ID)
    assert not result.ok
    assert result.reason == "stale_init_data"


def test_custom_max_age_is_honoured():
    init_data = _sign(_fields(auth_date=time.time() - 120))
    assert validate_init_data(init_data, BOT_TOKEN, CHAT_ID, max_age_sec=60).reason == "stale_init_data"
    assert validate_init_data(init_data, BOT_TOKEN, CHAT_ID, max_age_sec=600).ok


def test_auth_date_in_the_future_is_rejected_not_just_clamped():
    init_data = _sign(_fields(auth_date=time.time() + 100000))
    result = validate_init_data(init_data, BOT_TOKEN, CHAT_ID)
    assert not result.ok
    assert result.reason == "stale_init_data"


def test_valid_signature_for_a_different_chat_is_rejected():
    """The real defense against 'someone else also talks to this bot' -
    even a perfectly validly-signed initData for a DIFFERENT Telegram
    user must not unlock the owner's data."""
    init_data = _sign(_fields(user_id=999))
    result = validate_init_data(init_data, BOT_TOKEN, CHAT_ID)
    assert not result.ok
    assert result.reason == "wrong_chat"
    assert result.user_id == 999


def test_missing_user_field_is_rejected():
    fields = {"auth_date": str(int(time.time()))}
    init_data = _sign(fields)
    result = validate_init_data(init_data, BOT_TOKEN, CHAT_ID)
    assert not result.ok
    assert result.reason == "missing_user"


def test_empty_init_data_is_rejected():
    assert validate_init_data("", BOT_TOKEN, CHAT_ID).reason == "missing_input"


def test_empty_bot_token_is_rejected():
    init_data = _sign(_fields())
    assert validate_init_data(init_data, "", CHAT_ID).reason == "missing_input"


def test_malformed_init_data_does_not_raise():
    result = validate_init_data("not a query string %%%invalid", BOT_TOKEN, CHAT_ID)
    assert not result.ok
    assert result.reason == "malformed_init_data"


def test_malformed_user_json_is_rejected():
    fields = {"user": "{not valid json", "auth_date": str(int(time.time()))}
    init_data = _sign(fields)
    result = validate_init_data(init_data, BOT_TOKEN, CHAT_ID)
    assert not result.ok
    assert result.reason == "malformed_user"


def test_missing_auth_date_is_rejected():
    fields = {"user": json.dumps({"id": CHAT_ID})}
    init_data = _sign(fields)
    result = validate_init_data(init_data, BOT_TOKEN, CHAT_ID)
    assert not result.ok
    assert result.reason == "missing_auth_date"
