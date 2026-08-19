"""
activity_job/dialog_job poll Claude Desktop's UIA tree every 3s by default -
real work when there's a window to inspect, pure waste when app_health_job
has already confirmed the app isn't even running. These check that the
skip only triggers on a CONFIRMED-down app (app_was_running is False), not
on app_was_running being None (not checked yet, must still poll normally).
"""
import asyncio
from dataclasses import dataclass, field

from tether.transport import jobs

CHAT_ID = 21


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(text)


class FakeActivityWatcher:
    def __init__(self):
        self.poll_calls = 0

    def poll(self):
        self.poll_calls += 1
        return ([], [])


class FakeDialogWatcher:
    def __init__(self):
        self.poll_calls = 0

    def poll(self):
        self.poll_calls += 1
        return []


class FakeSettings:
    language = "en"
    activity_watch_enabled = True
    dialog_watch_enabled = True


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    activity_watcher: FakeActivityWatcher = field(default_factory=FakeActivityWatcher)
    dialog_watcher: FakeDialogWatcher = field(default_factory=FakeDialogWatcher)
    app_was_running: bool | None = None


class FakeContext:
    def __init__(self, app_was_running):
        self.bot = FakeBot()
        self.bot_data = {"state": FakeState(app_was_running=app_was_running)}


def test_activity_job_skips_when_app_confirmed_not_running():
    ctx = FakeContext(app_was_running=False)
    asyncio.run(jobs.activity_job(ctx))
    assert ctx.bot_data["state"].activity_watcher.poll_calls == 0


def test_activity_job_polls_when_app_is_running():
    ctx = FakeContext(app_was_running=True)
    asyncio.run(jobs.activity_job(ctx))
    assert ctx.bot_data["state"].activity_watcher.poll_calls == 1


def test_activity_job_polls_when_app_state_not_yet_checked():
    """None means app_health_job hasn't run yet - must not be treated the
    same as a confirmed-down app, or the very first poll after startup
    would be silently skipped."""
    ctx = FakeContext(app_was_running=None)
    asyncio.run(jobs.activity_job(ctx))
    assert ctx.bot_data["state"].activity_watcher.poll_calls == 1


def test_dialog_job_skips_when_app_confirmed_not_running():
    ctx = FakeContext(app_was_running=False)
    asyncio.run(jobs.dialog_job(ctx))
    assert ctx.bot_data["state"].dialog_watcher.poll_calls == 0


def test_dialog_job_polls_when_app_is_running():
    ctx = FakeContext(app_was_running=True)
    asyncio.run(jobs.dialog_job(ctx))
    assert ctx.bot_data["state"].dialog_watcher.poll_calls == 1


def test_dialog_job_polls_when_app_state_not_yet_checked():
    ctx = FakeContext(app_was_running=None)
    asyncio.run(jobs.dialog_job(ctx))
    assert ctx.bot_data["state"].dialog_watcher.poll_calls == 1
