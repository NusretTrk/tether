"""
The physical keyboard's Yes/No buttons show the localized label (German
"j" for ja, Spanish "s" for si) but must still send the underlying "y"/"n"
keystroke — matching only the English literal would silently break the
button in every language except English/Turkish, where the translated
label happens to already be "y"/"n".
"""
import asyncio
from dataclasses import dataclass, field

import pytest

from tether.transport.text import handle_text

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
    def __init__(self, language):
        self.language = language
        self.confirm_before_send = False
        self.defer_when_user_active_sec = 0
        self.auto_send_after_idle_sec = 0


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    def __init__(self, language):
        self.settings = FakeSettings(language)
        self.secrets = FakeSecrets()


@dataclass
class FakeState:
    target: FakeTarget = field(default_factory=FakeTarget)
    config: FakeConfig = field(default_factory=lambda: FakeConfig("en"))
    pending_send_text: str | None = None
    pending_send_kind: str = "text"
    pending_send_message_id: int | None = None
    pending_send_since: float = 0.0


class FakeContext:
    def __init__(self, language):
        self.bot_data = {"state": FakeState(config=FakeConfig(language))}


@pytest.mark.parametrize("language,button_text,expected_key", [
    ("de", "j", "y"),        # German "ja" button
    ("es", "s", "y"),        # Spanish "si" button
    ("en", "y", "y"),        # English, unchanged
    ("tr", "y", "y"),        # Turkish, unchanged
])
def test_localized_yes_button_sends_y_keystroke(language, button_text, expected_key):
    update = FakeUpdate(button_text)
    context = FakeContext(language)
    asyncio.run(handle_text(update, context))

    state = context.bot_data["state"]
    assert state.target.sent_keys == [expected_key], (
        f"in {language}, pressing the localized Yes button ({button_text!r}) "
        f"should send {expected_key!r}, not fall through to chat text"
    )
    assert state.target.staged_texts == []


def test_german_j_is_not_intercepted_as_a_shortcut_in_english_mode():
    """"j" isn't a shortcut in English — must type normally, not silently
    treated as a stray German yes-button press."""
    update = FakeUpdate("j")
    context = FakeContext("en")
    asyncio.run(handle_text(update, context))
    state = context.bot_data["state"]
    assert state.target.sent_keys == []
    assert state.target.staged_texts == ["j"]
