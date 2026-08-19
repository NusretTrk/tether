"""
This is the one place a real secret gets typed into the chat itself, so
it's tested for exactly the failsafes promised in the module docstring:
best-effort delete, masked confirmation only, staged-not-applied until
confirmed, and a timeout so an abandoned flow can't swallow a later
message as if it were the token.
"""
import asyncio
import time
from dataclasses import dataclass, field

from tether.transport import ngrok_setup

CHAT_ID = 111


@dataclass
class FakeChat:
    id: int = CHAT_ID


class FakeMessage:
    def __init__(self, text, message_id=7):
        self.text = text
        self.message_id = message_id


class FakeUpdate:
    def __init__(self, text):
        self.effective_chat = FakeChat()
        self.message = FakeMessage(text)


class FakeBot:
    def __init__(self, delete_should_fail=False):
        self.sent = []
        self.deleted = []
        self._delete_should_fail = delete_should_fail

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(text)
        return type("M", (), {"message_id": 99})()

    async def delete_message(self, chat_id, message_id):
        if self._delete_should_fail:
            raise RuntimeError("can't delete, too old")
        self.deleted.append(message_id)


class FakeContext:
    def __init__(self, bot=None):
        self.bot = bot or FakeBot()


@dataclass
class FakeState:
    pending_ngrok_token_since: float | None = None
    pending_ngrok_domain_since: float | None = None
    staged_ngrok_token: str | None = None
    staged_ngrok_domain: str | None = None


def _t(key, **kwargs):
    return key.format(**kwargs) if kwargs else key


def test_no_pending_capture_returns_false_and_sends_nothing():
    state = FakeState()
    ctx = FakeContext()
    result = asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("hello"), ctx, state, _t))
    assert result is False
    assert ctx.bot.sent == []


def test_valid_token_is_captured_and_message_deleted():
    state = FakeState(pending_ngrok_token_since=time.monotonic())
    ctx = FakeContext()
    update = FakeUpdate("a-real-looking-token-123")

    result = asyncio.run(ngrok_setup._maybe_capture(update, ctx, state, _t))

    assert result is True
    assert state.staged_ngrok_token == "a-real-looking-token-123"
    assert ctx.bot.deleted == [7]
    assert state.pending_ngrok_token_since is None


def test_captured_token_confirmation_never_contains_the_full_value():
    state = FakeState(pending_ngrok_token_since=time.monotonic())
    ctx = FakeContext()
    secret = "sk_live_super_secret_value_do_not_leak_1234567890"
    asyncio.run(ngrok_setup._maybe_capture(FakeUpdate(secret), ctx, state, _t))

    for msg in ctx.bot.sent:
        assert secret not in msg


def test_delete_failure_is_reported_not_hidden():
    state = FakeState(pending_ngrok_token_since=time.monotonic())
    ctx = FakeContext(bot=FakeBot(delete_should_fail=True))
    asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("some-token"), ctx, state, _t))

    assert state.staged_ngrok_token == "some-token"  # still captured
    assert any("ngrok_delete_failed" in m for m in ctx.bot.sent)


def test_token_with_whitespace_is_rejected():
    state = FakeState(pending_ngrok_token_since=time.monotonic())
    ctx = FakeContext()
    asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("has a space"), ctx, state, _t))

    assert state.staged_ngrok_token is None
    assert any("ngrok_token_invalid" in m for m in ctx.bot.sent)


def test_empty_token_is_rejected():
    state = FakeState(pending_ngrok_token_since=time.monotonic())
    ctx = FakeContext()
    asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("   "), ctx, state, _t))
    assert state.staged_ngrok_token is None


def test_overly_long_token_is_rejected():
    state = FakeState(pending_ngrok_token_since=time.monotonic())
    ctx = FakeContext()
    asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("x" * 500), ctx, state, _t))
    assert state.staged_ngrok_token is None


def test_expired_token_capture_times_out_without_staging_anything():
    long_ago = time.monotonic() - (ngrok_setup.PENDING_INPUT_TIMEOUT_SEC + 5)
    state = FakeState(pending_ngrok_token_since=long_ago)
    ctx = FakeContext()

    result = asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("a-token"), ctx, state, _t))

    assert result is True  # consumed, but as a timeout
    assert state.staged_ngrok_token is None
    assert any("ngrok_input_timed_out" in m for m in ctx.bot.sent)


def test_valid_domain_is_captured():
    state = FakeState(pending_ngrok_domain_since=time.monotonic())
    ctx = FakeContext()
    asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("myname.ngrok-free.app"), ctx, state, _t))
    assert state.staged_ngrok_domain == "myname.ngrok-free.app"


def test_domain_with_https_prefix_and_trailing_slash_is_normalized():
    state = FakeState(pending_ngrok_domain_since=time.monotonic())
    ctx = FakeContext()
    asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("https://myname.ngrok-free.app/"), ctx, state, _t))
    assert state.staged_ngrok_domain == "myname.ngrok-free.app"


def test_invalid_domain_is_rejected():
    state = FakeState(pending_ngrok_domain_since=time.monotonic())
    ctx = FakeContext()
    asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("not a domain!!"), ctx, state, _t))
    assert state.staged_ngrok_domain is None


def test_domain_without_a_dot_is_rejected():
    """A bare word ('localhost', 'mybot') is not a real ngrok domain -
    reject rather than silently accepting something that will just fail
    to resolve later."""
    state = FakeState(pending_ngrok_domain_since=time.monotonic())
    ctx = FakeContext()
    asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("justaword"), ctx, state, _t))
    assert state.staged_ngrok_domain is None


def test_token_capture_takes_priority_over_domain_capture_if_both_somehow_pending():
    state = FakeState(pending_ngrok_token_since=time.monotonic(), pending_ngrok_domain_since=time.monotonic())
    ctx = FakeContext()
    asyncio.run(ngrok_setup._maybe_capture(FakeUpdate("token-value"), ctx, state, _t))

    assert state.staged_ngrok_token == "token-value"
    assert state.staged_ngrok_domain is None
    # starting a new capture always clears the other kind first (see
    # start_token_capture/start_domain_capture) so this is a defensive
    # check on _maybe_capture's own ordering, not a real reachable state.


def test_start_token_capture_clears_any_pending_domain_capture():
    state = FakeState(pending_ngrok_domain_since=time.monotonic())
    ctx_bot = FakeBot()
    asyncio.run(ngrok_setup.start_token_capture(ctx_bot, CHAT_ID, state, _t))

    assert state.pending_ngrok_domain_since is None
    assert state.pending_ngrok_token_since is not None


def test_start_domain_capture_clears_any_pending_token_capture():
    state = FakeState(pending_ngrok_token_since=time.monotonic())
    ctx_bot = FakeBot()
    asyncio.run(ngrok_setup.start_domain_capture(ctx_bot, CHAT_ID, state, _t))

    assert state.pending_ngrok_token_since is None
    assert state.pending_ngrok_domain_since is not None


def test_mask_short_value_is_fully_masked():
    assert ngrok_setup._mask("short") == "•••••"


def test_mask_long_value_shows_only_edges():
    masked = ngrok_setup._mask("sk_live_1234567890abcdef")
    assert masked == "sk_l…cdef"
    assert "1234567890" not in masked
