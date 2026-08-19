"""
/shutdown <minutes> ends the whole machine, not just Claude's session, so
every path here is worth pinning explicitly: the argument parsing (usage vs
cancel vs a real delay), the confirm-before-acting gate, and that the actual
Windows call only ever happens after that confirmation.
"""
import asyncio
from dataclasses import dataclass, field

import pytest

from tether.platform import power
from tether.platform.capabilities import Capabilities, UnsupportedOnThisPlatform
from tether.transport import callbacks, handlers, jobs

CHAT_ID = 42


def _caps(power_control: bool) -> Capabilities:
    return Capabilities(
        window_control=True, accessibility=True, hardware_temps=True,
        shell=True, power_control=power_control,
    )


# --- platform/power.py ---------------------------------------------------

def test_schedule_shutdown_calls_shutdown_command(monkeypatch):
    monkeypatch.setattr(power, "CAPABILITIES", _caps(True))
    calls = []

    class FakeResult:
        returncode = 0

    def fake_run(args, **kwargs):
        calls.append(args)
        return FakeResult()

    monkeypatch.setattr(power.subprocess, "run", fake_run)
    assert power.schedule_shutdown(120) is True
    assert calls == [["shutdown", "/s", "/f", "/t", "120"]]


def test_cancel_shutdown_calls_shutdown_abort(monkeypatch):
    monkeypatch.setattr(power, "CAPABILITIES", _caps(True))
    calls = []

    class FakeResult:
        returncode = 0

    def fake_run(args, **kwargs):
        calls.append(args)
        return FakeResult()

    monkeypatch.setattr(power.subprocess, "run", fake_run)
    assert power.cancel_shutdown() is True
    assert calls == [["shutdown", "/a"]]


def test_schedule_shutdown_raises_where_unsupported(monkeypatch):
    monkeypatch.setattr(power, "CAPABILITIES", _caps(False))
    with pytest.raises(UnsupportedOnThisPlatform):
        power.schedule_shutdown(60)


def test_cancel_shutdown_raises_where_unsupported(monkeypatch):
    monkeypatch.setattr(power, "CAPABILITIES", _caps(False))
    with pytest.raises(UnsupportedOnThisPlatform):
        power.cancel_shutdown()


# --- cmd_shutdown handler -------------------------------------------------

class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, txt, **kwargs):
        self.replies.append((txt, kwargs.get("reply_markup")))
        return type("M", (), {"message_id": 1})()


@dataclass
class FakeChat:
    id: int = CHAT_ID


class FakeUpdate:
    def __init__(self, args_text=""):
        self.effective_chat = FakeChat()
        self.message = FakeMessage()


class FakeSettings:
    language = "en"
    shutdown_warning_lead_sec = 60


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    pending_shutdown_minutes: float | None = None


class FakeJobQueue:
    def __init__(self):
        self.scheduled = []
        self.removed = []

    def run_once(self, func, when, name):
        self.scheduled.append((func, when, name))

    def get_jobs_by_name(self, name):
        return [FakeJob(self, name)] if any(n == name for _, _, n in self.scheduled) else []


class FakeJob:
    def __init__(self, queue, name):
        self.queue = queue
        self.name = name

    def schedule_removal(self):
        self.queue.removed.append(self.name)
        self.queue.scheduled = [s for s in self.queue.scheduled if s[2] != self.name]


class FakeContext:
    def __init__(self, args):
        self.args = args
        self.bot_data = {"state": FakeState()}
        self.job_queue = FakeJobQueue()


def test_no_args_shows_usage():
    update, context = FakeUpdate(), FakeContext([])
    asyncio.run(handlers.cmd_shutdown(update, context))
    assert "usage" in update.message.replies[0][0].lower() or "/shutdown" in update.message.replies[0][0]


def test_non_numeric_arg_shows_usage():
    update, context = FakeUpdate(), FakeContext(["soon"])
    asyncio.run(handlers.cmd_shutdown(update, context))
    assert context.bot_data["state"].pending_shutdown_minutes is None


def test_zero_minutes_rejected():
    update, context = FakeUpdate(), FakeContext(["0"])
    asyncio.run(handlers.cmd_shutdown(update, context))
    assert context.bot_data["state"].pending_shutdown_minutes is None


def test_negative_minutes_rejected():
    update, context = FakeUpdate(), FakeContext(["-5"])
    asyncio.run(handlers.cmd_shutdown(update, context))
    assert context.bot_data["state"].pending_shutdown_minutes is None


def test_valid_minutes_stages_for_confirmation_without_acting(monkeypatch):
    calls = []
    monkeypatch.setattr(power, "schedule_shutdown", lambda s: calls.append(s) or True)
    update, context = FakeUpdate(), FakeContext(["120"])
    asyncio.run(handlers.cmd_shutdown(update, context))

    assert context.bot_data["state"].pending_shutdown_minutes == 120.0
    assert calls == [], "shutdown must not be scheduled before the user confirms"
    text, markup = update.message.replies[0]
    assert markup is not None


def test_cancel_calls_cancel_shutdown_and_clears_warning_job(monkeypatch):
    calls = []
    monkeypatch.setattr(power, "cancel_shutdown", lambda: calls.append(True) or True)
    update, context = FakeUpdate(), FakeContext(["cancel"])
    context.job_queue.scheduled.append((jobs.shutdown_warning_job, 60, jobs.SHUTDOWN_WARNING_JOB_NAME))

    asyncio.run(handlers.cmd_shutdown(update, context))

    assert calls == [True]
    assert jobs.SHUTDOWN_WARNING_JOB_NAME in context.job_queue.removed


def test_unsupported_platform_reports_and_does_nothing_else(monkeypatch):
    monkeypatch.setattr(handlers, "CAPABILITIES", _caps(False))
    update, context = FakeUpdate(), FakeContext(["120"])
    asyncio.run(handlers.cmd_shutdown(update, context))
    assert context.bot_data["state"].pending_shutdown_minutes is None


# --- callback confirm/cancel flow -----------------------------------------

class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answered = False
        self.edits = []
        self.message = type("M", (), {"message_id": 9})()

    async def answer(self, *a, **kw):
        self.answered = True

    async def edit_message_text(self, text, reply_markup=None):
        self.edits.append(text)


class FakeCallbackUpdate:
    def __init__(self, data):
        self.effective_chat = FakeChat()
        self.callback_query = FakeQuery(data)


def test_shutdown_confirm_callback_schedules_only_after_confirmation(monkeypatch):
    calls = []
    monkeypatch.setattr(power, "schedule_shutdown", lambda s: calls.append(s) or True)

    update = FakeCallbackUpdate("shutdown:confirm")
    context = FakeContext([])
    context.bot_data["state"].pending_shutdown_minutes = 90.0

    asyncio.run(callbacks.handle_callback(update, context))

    assert calls == [90 * 60]
    assert context.bot_data["state"].pending_shutdown_minutes is None
    assert any("90" in e for e in update.callback_query.edits)


def test_shutdown_cancel_callback_never_calls_power(monkeypatch):
    calls = []
    monkeypatch.setattr(power, "schedule_shutdown", lambda s: calls.append(s) or True)

    update = FakeCallbackUpdate("shutdown:cancel")
    context = FakeContext([])
    context.bot_data["state"].pending_shutdown_minutes = 90.0

    asyncio.run(callbacks.handle_callback(update, context))

    assert calls == []
    assert context.bot_data["state"].pending_shutdown_minutes is None


# --- shutdown_warning_job -------------------------------------------------

class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(text)


class FakeJobContext:
    def __init__(self):
        self.bot = FakeBot()
        self.bot_data = {"state": FakeState()}


def test_shutdown_warning_job_sends_a_message():
    ctx = FakeJobContext()
    asyncio.run(jobs.shutdown_warning_job(ctx))
    assert len(ctx.bot.sent) == 1
