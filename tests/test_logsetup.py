"""Token redaction filter — must never let a bot token reach a log line,
since python-telegram-bot logs the outbound request URL (which contains the
token) at INFO level on every poll."""
import logging

from tether.logsetup import RedactTokenFilter


def _make_record(msg, args=()):
    return logging.LogRecord("test", logging.INFO, __file__, 1, msg, args, None)


def test_redacts_token_in_message():
    f = RedactTokenFilter()
    record = _make_record("POST https://api.telegram.org/bot123456789:FAKEtokenFAKEtokenFAKEtokenFAKEtoken/getUpdates")
    f.filter(record)
    assert "FAKEtoken" not in record.msg
    assert "bot***REDACTED***" in record.msg


def test_redacts_token_in_args():
    f = RedactTokenFilter()
    record = _make_record("url=%s", ("https://api.telegram.org/bot123456789:ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ/sendMessage",))
    f.filter(record)
    assert "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ" not in record.args[0]


def test_leaves_normal_messages_untouched():
    f = RedactTokenFilter()
    record = _make_record("Application started")
    f.filter(record)
    assert record.msg == "Application started"


def test_filter_always_returns_true():
    f = RedactTokenFilter()
    assert f.filter(_make_record("anything")) is True
