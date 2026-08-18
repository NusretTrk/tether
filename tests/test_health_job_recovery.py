"""
The policy is unit-tested separately; this checks the job actually wires it
up - that a crash while idle really does trigger a restart, and a crash
while the user is present really does not.
"""
import asyncio
from dataclasses import dataclass, field

import pytest

from tether.monitors.recovery import RecoveryDecider, RecoveryPolicy
from tether.transport import jobs

CHAT_ID = 55


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(text)


class FakeTarget:
    def __init__(self, running):
        self._running = running
        self.restart_calls = 0

    def is_app_running(self):
        return self._running

    def restart_app(self):
        self.restart_calls += 1
        self._running = True
        return (True, "ok")


class FakeSettings:
    language = "en"
    app_health_watch_enabled = True
    auto_recover_max_attempts = 3


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    target: FakeTarget = None
    config: FakeConfig = field(default_factory=FakeConfig)
    recovery: RecoveryDecider = None
    app_was_running: bool | None = True
    app_down_notified: bool = False


class FakeContext:
    def __init__(self, target, recovery):
        self.bot = FakeBot()
        self.bot_data = {"state": FakeState(target=target, recovery=recovery)}


def _run(target, recovery, idle, monkeypatch):
    monkeypatch.setattr(
        "tether.platform.presence.idle_seconds", lambda: idle
    )
    ctx = FakeContext(target, recovery)
    asyncio.run(jobs.app_health_job(ctx))
    return ctx


def test_crash_while_away_triggers_restart(monkeypatch):
    target = FakeTarget(running=False)
    recovery = RecoveryDecider(RecoveryPolicy(require_idle_sec=90, cooldown_sec=0))
    ctx = _run(target, recovery, idle=500, monkeypatch=monkeypatch)

    assert target.restart_calls == 1, "crash while idle should have been recovered"
    assert any("back" in m.lower() or "restart" in m.lower() for m in ctx.bot.sent)


def test_crash_while_user_present_does_not_restart(monkeypatch):
    target = FakeTarget(running=False)
    recovery = RecoveryDecider(RecoveryPolicy(require_idle_sec=90, cooldown_sec=0))
    ctx = _run(target, recovery, idle=3, monkeypatch=monkeypatch)

    assert target.restart_calls == 0, "restarted despite the user being at the machine"
    assert ctx.bot.sent, "should still have reported that it went down"


def test_disabled_policy_reports_but_never_restarts(monkeypatch):
    target = FakeTarget(running=False)
    recovery = RecoveryDecider(RecoveryPolicy(enabled=False))
    ctx = _run(target, recovery, idle=999, monkeypatch=monkeypatch)

    assert target.restart_calls == 0
    assert ctx.bot.sent


def test_still_running_is_silent(monkeypatch):
    target = FakeTarget(running=True)
    recovery = RecoveryDecider(RecoveryPolicy())
    ctx = _run(target, recovery, idle=999, monkeypatch=monkeypatch)

    assert target.restart_calls == 0
    assert ctx.bot.sent == []
