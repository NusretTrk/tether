"""
Plain text messages like "1", "y", "Enter" must be interpreted as keypress
shortcuts (answering a prompt), not typed literally into Claude's chat.
The rewrite lost this — everything fell through to stage_text — which from
the user's side looked identical to "the keypad stopped working": sending
"1" put the literal character in the chat instead of answering anything.
"""
import asyncio
from dataclasses import dataclass, field

import pytest

from tether.transport.text import handle_text, TEXT_KEY_SHORTCUTS

CHAT_ID = 111


@dataclass
class FakeChat:
    id: int = CHAT_ID


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return type("M", (), {"message_id": 1})()


class FakeUpdate:
    def __init__(self, text):
        self.effective_chat = FakeChat()
        self.message = FakeMessage(text)


class FakeTarget:
    def __init__(self):
        self.sent_keys = []
        self.staged_texts = []

    def send_key(self, key):
        self.sent_keys.append(key)
        return True

    def stage_text(self, text):
        self.staged_texts.append(text)
        from tether.targets.base import PasteResult
        return PasteResult(True)

    def press_enter(self):
        return True


class FakeSettings:
    language = "en"
    confirm_before_send = False


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    target: FakeTarget = field(default_factory=FakeTarget)
    config: FakeConfig = field(default_factory=FakeConfig)
    pending_send_text: str | None = None
    pending_send_kind: str = "text"
    pending_send_message_id: int | None = None
    pending_send_since: float = 0.0


class FakeContext:
    def __init__(self):
        self.bot_data = {"state": FakeState()}


@pytest.mark.parametrize("shortcut", ["1", "2", "3", "y", "n", "Enter", "ENTER", "esc", "Tab"])
def test_bare_shortcut_sends_key_not_chat_text(shortcut):
    update = FakeUpdate(shortcut)
    context = FakeContext()
    asyncio.run(handle_text(update, context))

    state = context.bot_data["state"]
    assert state.target.sent_keys, f"{shortcut!r} did not trigger send_key"
    assert state.target.staged_texts == [], f"{shortcut!r} was typed into Claude instead of sent as a key"


def test_esc_maps_to_escape():
    update = FakeUpdate("esc")
    context = FakeContext()
    asyncio.run(handle_text(update, context))
    assert context.bot_data["state"].target.sent_keys == ["escape"]


def test_ordinary_sentence_is_still_typed_not_intercepted():
    update = FakeUpdate("can you check the logs")
    context = FakeContext()
    asyncio.run(handle_text(update, context))

    state = context.bot_data["state"]
    assert state.target.staged_texts == ["can you check the logs"]
    assert state.target.sent_keys == []


def test_word_containing_a_shortcut_is_not_intercepted():
    """"yes" must not match "y", "no" must not match "n"."""
    for word in ("yes", "no", "entertainment"):
        update = FakeUpdate(word)
        context = FakeContext()
        asyncio.run(handle_text(update, context))
        state = context.bot_data["state"]
        assert state.target.sent_keys == [], f"{word!r} was wrongly treated as a shortcut"
        assert state.target.staged_texts == [word]
