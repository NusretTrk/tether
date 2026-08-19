"""
/unlock and /lock wire the pure LockoutDecider logic (tested separately in
test_lockout.py) into the bot: wrong password records a failure, enough
wrong attempts locks out further tries, a correct password unlocks and
resets the counter, and /lock re-locks on demand.
"""
import asyncio
from dataclasses import dataclass, field

from tether.monitors.lockout import LockoutDecider, LockoutPolicy
from tether.transport import handlers

CHAT_ID = 33


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, txt, **kwargs):
        self.replies.append(txt)


@dataclass
class FakeChat:
    id: int = CHAT_ID


class FakeUpdate:
    def __init__(self, text="/unlock"):
        self.effective_chat = FakeChat()
        self.message = FakeMessage()
        # restricted()'s lock gate reads update.message.text to recognize
        # /unlock as exempt even while locked - a real Update always has
        # this set for a command message, so the fake needs it too.
        self.message.text = text


class FakeSettings:
    language = "en"


class FakeSecrets:
    chat_id = CHAT_ID
    bot_password = "hunter2"


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    unlocked: bool = False
    unlock_lockout: LockoutDecider = field(default_factory=lambda: LockoutDecider(LockoutPolicy(max_attempts=3, window_sec=300)))


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []
        self.bot_data = {"state": FakeState()}


# --- cmd_unlock ----------------------------------------------------------

def test_no_password_configured_says_not_needed(monkeypatch):
    monkeypatch.setattr(FakeSecrets, "bot_password", None)
    update, context = FakeUpdate(), FakeContext(["anything"])
    asyncio.run(handlers.cmd_unlock(update, context))
    assert context.bot_data["state"].unlocked is False
    assert "not" in update.message.replies[0].lower() or "no" in update.message.replies[0].lower()


def test_wrong_password_does_not_unlock_and_records_failure():
    update, context = FakeUpdate(), FakeContext(["wrongpass"])
    asyncio.run(handlers.cmd_unlock(update, context))
    assert context.bot_data["state"].unlocked is False
    assert len(context.bot_data["state"].unlock_lockout.failure_times) == 1


def test_correct_password_unlocks_and_resets_lockout():
    update, context = FakeUpdate(), FakeContext(["hunter2"])
    context.bot_data["state"].unlock_lockout.record_failure(1000)
    asyncio.run(handlers.cmd_unlock(update, context))
    assert context.bot_data["state"].unlocked is True
    assert context.bot_data["state"].unlock_lockout.failure_times == []


def test_too_many_wrong_attempts_locks_out_further_tries():
    update, context = FakeUpdate(), FakeContext(["wrong"])
    state = context.bot_data["state"]
    for _ in range(3):
        asyncio.run(handlers.cmd_unlock(FakeUpdate(), context))
    assert state.unlocked is False

    # Even the RIGHT password is refused once locked out.
    correct_update, correct_context = FakeUpdate(), FakeContext(["hunter2"])
    correct_context.bot_data["state"] = state
    asyncio.run(handlers.cmd_unlock(correct_update, correct_context))
    assert state.unlocked is False
    assert "later" in correct_update.message.replies[-1].lower() or "many" in correct_update.message.replies[-1].lower()


def test_multi_word_password_joins_args_with_spaces():
    update, context = FakeUpdate(), FakeContext(["not", "the", "password"])
    asyncio.run(handlers.cmd_unlock(update, context))
    assert context.bot_data["state"].unlocked is False


# --- cmd_lock --------------------------------------------------------------

def test_lock_relocks_an_unlocked_bot():
    update, context = FakeUpdate(), FakeContext()
    context.bot_data["state"].unlocked = True
    asyncio.run(handlers.cmd_lock(update, context))
    assert context.bot_data["state"].unlocked is False


def test_lock_with_no_password_configured_is_a_noop_message(monkeypatch):
    monkeypatch.setattr(FakeSecrets, "bot_password", None)
    update, context = FakeUpdate(), FakeContext()
    asyncio.run(handlers.cmd_lock(update, context))
    assert update.message.replies
