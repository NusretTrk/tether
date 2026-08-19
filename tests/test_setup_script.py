import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from setup import deep_link, extract_matching_chat_id, make_setup_nonce  # noqa: E402


def test_make_setup_nonce_is_random_and_urlsafe():
    a, b = make_setup_nonce(), make_setup_nonce()
    assert a != b
    assert all(c.isalnum() or c in "-_" for c in a)


def test_deep_link_format():
    assert deep_link("mybot", "abc123") == "https://t.me/mybot?start=abc123"


def _update(text, chat_id=555, kind="message"):
    return {kind: {"text": text, "chat": {"id": chat_id}}}


def test_matching_nonce_returns_chat_id():
    update = _update("/start secret123")
    assert extract_matching_chat_id(update, "secret123") == 555


def test_wrong_nonce_is_ignored():
    update = _update("/start wrongvalue")
    assert extract_matching_chat_id(update, "secret123") is None


def test_start_with_no_payload_is_ignored():
    update = _update("/start")
    assert extract_matching_chat_id(update, "secret123") is None


def test_unrelated_message_is_ignored():
    update = _update("hello there")
    assert extract_matching_chat_id(update, "secret123") is None


def test_someone_elses_correct_looking_message_without_nonce_is_ignored():
    update = _update("/start secret124", chat_id=999)
    assert extract_matching_chat_id(update, "secret123") is None


def test_edited_message_is_accepted_same_as_message():
    update = _update("/start secret123", kind="edited_message")
    assert extract_matching_chat_id(update, "secret123") == 555


def test_update_with_no_message_key_is_ignored():
    assert extract_matching_chat_id({"other_update_type": {}}, "secret123") is None


def test_whitespace_padded_text_still_matches():
    update = _update("  /start secret123  ")
    assert extract_matching_chat_id(update, "secret123") == 555


def test_extra_trailing_text_does_not_match():
    update = _update("/start secret123 extra")
    assert extract_matching_chat_id(update, "secret123") is None


def test_nonce_is_case_sensitive():
    update = _update("/start SECRET123")
    assert extract_matching_chat_id(update, "secret123") is None
