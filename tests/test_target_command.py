"""/target wires the profile lookup into the bot - unknown names must
refuse cleanly, "claude"/"none" must always reset, and a valid name must
stick until changed."""
import asyncio
from dataclasses import dataclass, field

from tether.transport import handlers

CHAT_ID = 88


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, txt, **kwargs):
        self.replies.append(txt)


@dataclass
class FakeChat:
    id: int = CHAT_ID


class FakeUpdate:
    def __init__(self):
        self.effective_chat = FakeChat()
        self.message = FakeMessage()


class FakeSettings:
    language = "en"
    keypad_profiles = {"cursor": {"window_keyword": "Cursor"}, "broken": {}}


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    active_target_profile: str | None = None


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []
        self.bot_data = {"state": FakeState()}


def test_no_args_shows_current_target():
    update, context = FakeUpdate(), FakeContext([])
    asyncio.run(handlers.cmd_target(update, context))
    assert "claude" in update.message.replies[0].lower()


def test_setting_a_valid_profile_switches_the_target():
    update, context = FakeUpdate(), FakeContext(["cursor"])
    asyncio.run(handlers.cmd_target(update, context))
    assert context.bot_data["state"].active_target_profile == "cursor"


def test_unknown_profile_is_refused_and_does_not_change_state():
    update, context = FakeUpdate(), FakeContext(["nonexistent"])
    asyncio.run(handlers.cmd_target(update, context))
    assert context.bot_data["state"].active_target_profile is None


def test_profile_without_window_keyword_is_refused():
    update, context = FakeUpdate(), FakeContext(["broken"])
    asyncio.run(handlers.cmd_target(update, context))
    assert context.bot_data["state"].active_target_profile is None


def test_claude_resets_to_default():
    update, context = FakeUpdate(), FakeContext(["claude"])
    context.bot_data["state"].active_target_profile = "cursor"
    asyncio.run(handlers.cmd_target(update, context))
    assert context.bot_data["state"].active_target_profile is None


def test_none_also_resets_to_default():
    update, context = FakeUpdate(), FakeContext(["none"])
    context.bot_data["state"].active_target_profile = "cursor"
    asyncio.run(handlers.cmd_target(update, context))
    assert context.bot_data["state"].active_target_profile is None


def test_target_name_is_case_insensitive():
    update, context = FakeUpdate(), FakeContext(["CURSOR"])
    asyncio.run(handlers.cmd_target(update, context))
    assert context.bot_data["state"].active_target_profile == "cursor"
