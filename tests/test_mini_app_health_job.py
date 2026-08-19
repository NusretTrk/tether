"""
mini_app_health_job is the one thing that notices ngrok died and brings
it back - a no-op the overwhelming majority of the time (Mini App off),
so that's the case worth being certain about too.
"""
import asyncio
from dataclasses import dataclass

from tether.transport.jobs import mini_app_health_job


@dataclass
class FakeState:
    ngrok_runner: object = None


class FakeContext:
    def __init__(self, ngrok_runner=None):
        self.bot_data = {"state": FakeState(ngrok_runner=ngrok_runner)}


def test_noop_when_mini_app_is_off():
    ctx = FakeContext(ngrok_runner=None)
    asyncio.run(mini_app_health_job(ctx))  # must not raise


def test_calls_ensure_running_when_runner_present():
    calls = []

    class FakeRunner:
        def ensure_running(self):
            calls.append(1)

    ctx = FakeContext(ngrok_runner=FakeRunner())
    asyncio.run(mini_app_health_job(ctx))
    assert calls == [1]
