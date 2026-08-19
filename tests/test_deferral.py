"""
When someone is at the keyboard, a remote message must be held *before*
anything touches the window. Staging first and checking after is useless:
staging is what steals focus.
"""
import asyncio
from dataclasses import dataclass, field

import pytest

from tether.transport import text as text_mod

CHAT_ID = 111


@dataclass
class FakeChat:
    id: int = CHAT_ID


class FakeMessage:
    def __init__(self, txt):
        self.text = txt
        self.caption = None
        self.replies = []

    async def reply_text(self, txt, **kwargs):
        self.replies.append(txt)
        return type("M", (), {"message_id": 7})()


class FakeUpdate:
    def __init__(self, txt):
        self.effective_chat = FakeChat()
        self.message = FakeMessage(txt)


class FakeTarget:
    def __init__(self):
        self.staged_texts = []
        self.sent_keys = []
        self.enter_presses = 0

    def stage_text(self, t):
        self.staged_texts.append(t)
        from tether.targets.base import PasteResult
        return PasteResult(True)

    def send_key(self, k, w=None):
        self.sent_keys.append(k)
        return True

    def press_enter(self):
        self.enter_presses += 1
        return True


class FakeSettings:
    language = "en"
    confirm_before_send = False
    defer_when_user_active_sec = 30
    auto_send_after_idle_sec = 45


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    target: FakeTarget = field(default_factory=FakeTarget)
    config: FakeConfig = field(default_factory=FakeConfig)
    deferred_text: str | None = None
    deferred_photo_bytes: bytes | None = None
    deferred_caption: str = ""
    deferred_message_id: int | None = None
    pending_send_text: str | None = None
    pending_send_kind: str = "text"
    pending_send_message_id: int | None = None
    pending_send_since: float = 0.0
    active_target_profile: str | None = None


class FakeContext:
    def __init__(self):
        self.bot_data = {"state": FakeState()}


def test_message_is_held_without_touching_the_window_when_user_active(monkeypatch):
    monkeypatch.setattr(text_mod, "is_user_active", lambda threshold: True)
    monkeypatch.setattr(text_mod, "idle_seconds", lambda: 3.0)

    update = FakeUpdate("do the thing")
    context = FakeContext()
    asyncio.run(text_mod.handle_text(update, context))

    state = context.bot_data["state"]
    assert state.deferred_text == "do the thing"
    assert state.target.staged_texts == [], "window was touched despite user being active"
    assert state.target.enter_presses == 0


def test_message_goes_straight_through_when_user_is_away(monkeypatch):
    monkeypatch.setattr(text_mod, "is_user_active", lambda threshold: False)

    update = FakeUpdate("do the thing")
    context = FakeContext()
    asyncio.run(text_mod.handle_text(update, context))

    state = context.bot_data["state"]
    assert state.deferred_text is None
    assert state.target.staged_texts == ["do the thing"]


def test_deliver_deferred_sends_and_clears(monkeypatch):
    context = FakeContext()
    state = context.bot_data["state"]
    state.deferred_text = "held message"
    state.deferred_message_id = 7

    ok, reason = asyncio.run(text_mod.deliver_deferred(context, state, lambda k, **kw: k))

    assert ok, reason
    assert state.target.staged_texts == ["held message"]
    assert state.target.enter_presses == 1
    assert state.deferred_text is None, "deferred state not cleared after sending"
    assert state.pending_send_text == "held message"


def test_deliver_deferred_with_nothing_held_is_a_noop():
    context = FakeContext()
    state = context.bot_data["state"]
    ok, reason = asyncio.run(text_mod.deliver_deferred(context, state, lambda k, **kw: k))
    assert not ok
    assert reason == "nothing_deferred"


def test_message_goes_to_the_selected_target_not_claude(monkeypatch):
    """/target routes plain messages elsewhere - the Claude-Desktop
    FakeTarget must never be touched once a profile is selected, and the
    ground-truth pending_send_* state (meaningless for a generic target)
    must not be set either."""
    monkeypatch.setattr(text_mod, "is_user_active", lambda threshold: False)

    class FakeGenericTarget:
        def __init__(self, keyword, preserve):
            self.staged_texts = []
            self.enter_presses = 0

        def stage_text(self, t):
            self.staged_texts.append(t)
            from tether.targets.base import PasteResult
            return PasteResult(True)

        def press_enter(self):
            self.enter_presses += 1
            return True

    generic = FakeGenericTarget("Cursor", True)
    monkeypatch.setattr(
        "tether.targets.generic.GenericTarget",
        lambda kw, preserve, click=None, model_click=None, path_filter=None: generic,
    )
    monkeypatch.setattr(FakeSettings, "keypad_profiles", {"cursor": {"window_keyword": "Cursor"}}, raising=False)
    monkeypatch.setattr(FakeSettings, "preserve_user_clipboard", True, raising=False)

    update = FakeUpdate("do the thing")
    context = FakeContext()
    state = context.bot_data["state"]
    state.active_target_profile = "cursor"

    asyncio.run(text_mod.handle_text(update, context))

    assert generic.staged_texts == ["do the thing"]
    assert state.target.staged_texts == [], "message went to Claude Desktop instead of the selected target"
    assert state.pending_send_text is None, "ground-truth tracking doesn't apply to a generic target"


# --- send_text_to_target: the shared core handle_text and the Mini App's
# own /api/send both call, exercised directly (no update/context needed,
# just the notify callable) so its return-status contract is pinned
# independently of either caller. ---

class _RecordingNotify:
    def __init__(self):
        self.calls = []

    async def __call__(self, text, reply_markup=None):
        self.calls.append((text, reply_markup))
        return type("M", (), {"message_id": 42})()


def test_send_returns_deferred_status_when_user_active(monkeypatch):
    monkeypatch.setattr(text_mod, "is_user_active", lambda threshold: True)
    monkeypatch.setattr(text_mod, "idle_seconds", lambda: 3.0)
    state = FakeState()
    notify = _RecordingNotify()

    status = asyncio.run(text_mod.send_text_to_target(state, lambda k, **kw: k, "hi", notify))

    assert status == "deferred"
    assert state.deferred_text == "hi"
    assert len(notify.calls) == 1


def test_send_returns_staged_status_when_confirm_required(monkeypatch):
    monkeypatch.setattr(text_mod, "is_user_active", lambda threshold: False)
    state = FakeState()
    # FakeConfig.settings is a shared class-level instance across every
    # FakeState() in this file (not a dataclass field) - monkeypatch.setattr
    # auto-reverts after this test, a plain assignment would leak into
    # whichever test runs next.
    monkeypatch.setattr(state.config.settings, "confirm_before_send", True)

    status = asyncio.run(text_mod.send_text_to_target(state, lambda k, **kw: k, "hi", _RecordingNotify()))

    assert status == "staged"
    assert state.staged_text == "hi"
    assert state.target.enter_presses == 0, "must not press enter before confirmation"


def test_send_returns_sent_pending_verification_for_claude_desktop(monkeypatch):
    monkeypatch.setattr(text_mod, "is_user_active", lambda threshold: False)
    state = FakeState()

    status = asyncio.run(text_mod.send_text_to_target(state, lambda k, **kw: k, "hi", _RecordingNotify()))

    assert status == "sent_pending_verification"
    assert state.pending_send_text == "hi"
    assert state.target.enter_presses == 1


def test_send_returns_stage_failed_when_window_not_found(monkeypatch):
    monkeypatch.setattr(text_mod, "is_user_active", lambda threshold: False)
    state = FakeState()

    def failing_stage(t):
        from tether.targets.base import PasteResult
        return PasteResult(False, reason="window_not_found")

    state.target.stage_text = failing_stage

    status = asyncio.run(text_mod.send_text_to_target(state, lambda k, **kw: k, "hi", _RecordingNotify()))

    assert status == "stage_failed"
    assert state.target.enter_presses == 0


def test_send_notify_receives_no_reply_to_message_dependency(monkeypatch):
    """The Mini App has no originating Telegram message to reply to -
    notify() must work as a bare send, never assuming a message object
    to attach a reply to."""
    monkeypatch.setattr(text_mod, "is_user_active", lambda threshold: False)
    state = FakeState()
    notify = _RecordingNotify()
    asyncio.run(text_mod.send_text_to_target(state, lambda k, **kw: k, "hi", notify))
    assert len(notify.calls) >= 1
