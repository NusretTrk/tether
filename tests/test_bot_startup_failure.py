"""
main() used to retry a failed startup in a loop within the same process
(sleep, then call run_polling() again). Confirmed live, not assumed, that
this doesn't actually work: a real Telegram-API outage during a session
left the bot stuck retrying with "Event loop is closed" on every attempt
after the first, even minutes after connectivity to Telegram had come back
- run_polling()'s own event-loop teardown leaves the process unable to
start a second one cleanly. The fix is to not retry in-process at all and
let watchdog.py (which already exists to relaunch tether unconditionally
on process death) bring up a fresh process instead, which is guaranteed
fresh asyncio state.
"""
from unittest.mock import MagicMock

from tether import bot as bot_mod


def test_main_exits_with_nonzero_code_on_startup_failure(monkeypatch):
    monkeypatch.setattr(bot_mod, "setup_logging", lambda path: None)
    monkeypatch.setattr(bot_mod.Config, "load", staticmethod(lambda: object()))

    failing_app = MagicMock()
    failing_app.run_polling.side_effect = RuntimeError("Event loop is closed")
    monkeypatch.setattr(bot_mod, "_build_app", lambda config: failing_app)

    exit_calls = []
    monkeypatch.setattr(bot_mod.sys, "exit", lambda code=0: exit_calls.append(code))

    bot_mod.main()

    assert exit_calls == [1]
    assert failing_app.run_polling.call_count == 1  # never retried in-process


def test_main_does_not_exit_on_a_clean_shutdown(monkeypatch):
    monkeypatch.setattr(bot_mod, "setup_logging", lambda path: None)
    monkeypatch.setattr(bot_mod.Config, "load", staticmethod(lambda: object()))

    clean_app = MagicMock()
    clean_app.run_polling.return_value = None  # run_polling only returns on a clean shutdown
    monkeypatch.setattr(bot_mod, "_build_app", lambda config: clean_app)

    exit_calls = []
    monkeypatch.setattr(bot_mod.sys, "exit", lambda code=0: exit_calls.append(code))

    bot_mod.main()

    assert exit_calls == []
