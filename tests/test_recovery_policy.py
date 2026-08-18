"""
Auto-restart decisions, tested as pure logic. Every branch here is a case
where getting it wrong means either a restart loop or fighting the person
sitting at the machine, so all of them are covered explicitly rather than
just the happy path.
"""
import pytest

from tether.monitors.recovery import RecoveryDecider, RecoveryPolicy


def make(enabled=True, max_attempts=3, cooldown=120.0, require_idle=90.0, window=1800.0):
    return RecoveryDecider(RecoveryPolicy(
        enabled=enabled, max_attempts=max_attempts, cooldown_sec=cooldown,
        require_idle_sec=require_idle, attempt_window_sec=window,
    ))


def test_recovers_a_clean_crash_while_user_is_away():
    d = make()
    ok, reason = d.should_recover(app_running=False, was_running=True, idle_seconds=300, now=1000)
    assert ok, reason


def test_does_nothing_while_the_app_is_running():
    d = make()
    ok, reason = d.should_recover(app_running=True, was_running=True, idle_seconds=300, now=1000)
    assert not ok and reason == "still_running"


def test_does_not_fight_a_user_who_just_quit_the_app():
    """The whole point of the idle gate. Someone who closed it deliberately
    is sitting right there and does not want it coming back."""
    d = make(require_idle=90.0)
    ok, reason = d.should_recover(app_running=False, was_running=True, idle_seconds=5, now=1000)
    assert not ok and reason == "user_active"


def test_no_transition_means_no_action():
    """Already-down apps are reported once, not restarted on every poll."""
    d = make()
    ok, reason = d.should_recover(app_running=False, was_running=False, idle_seconds=999, now=1000)
    assert not ok and reason == "no_transition"


def test_first_check_after_startup_does_not_recover():
    d = make()
    ok, reason = d.should_recover(app_running=False, was_running=None, idle_seconds=999, now=1000)
    assert not ok and reason == "no_transition"


def test_unknown_presence_does_not_guess():
    """If idle time can't be read, a crash and a deliberate quit are
    indistinguishable — report rather than act."""
    d = make()
    ok, reason = d.should_recover(app_running=False, was_running=True, idle_seconds=None, now=1000)
    assert not ok and reason == "presence_unknown"


def test_disabled_policy_never_recovers():
    d = make(enabled=False)
    ok, reason = d.should_recover(app_running=False, was_running=True, idle_seconds=999, now=1000)
    assert not ok and reason == "disabled"


def test_cooldown_blocks_a_rapid_second_attempt():
    d = make(cooldown=120.0)
    d.record_attempt(1000)
    ok, reason = d.should_recover(app_running=False, was_running=True, idle_seconds=999, now=1030)
    assert not ok and reason == "cooling_down"


def test_attempt_allowed_once_cooldown_elapses():
    d = make(cooldown=120.0)
    d.record_attempt(1000)
    ok, reason = d.should_recover(app_running=False, was_running=True, idle_seconds=999, now=1200)
    assert ok, reason


def test_attempt_limit_stops_a_crash_loop():
    """An app broken on startup must not be restarted forever."""
    d = make(max_attempts=3, cooldown=0.0)
    for i in range(3):
        d.record_attempt(1000 + i)
    ok, reason = d.should_recover(app_running=False, was_running=True, idle_seconds=999, now=1010)
    assert not ok and reason == "attempt_limit_reached"


def test_old_attempts_are_forgiven_outside_the_window():
    """An app that dies once a day should be recovered every day, not
    permanently blacklisted after three lifetime failures."""
    d = make(max_attempts=3, cooldown=0.0, window=1800.0)
    for i in range(3):
        d.record_attempt(1000 + i)
    ok, reason = d.should_recover(app_running=False, was_running=True, idle_seconds=999, now=1000 + 5000)
    assert ok, reason


def test_reset_clears_the_attempt_budget():
    d = make(max_attempts=1, cooldown=0.0)
    d.record_attempt(1000)
    assert not d.should_recover(app_running=False, was_running=True, idle_seconds=999, now=1001)[0]
    d.reset()
    assert d.should_recover(app_running=False, was_running=True, idle_seconds=999, now=1002)[0]


def test_attempts_in_window_counts_correctly():
    d = make(window=100.0)
    d.record_attempt(1000)
    d.record_attempt(1050)
    assert d.attempts_in_window(1060) == 2   # cutoff 960, both count
    assert d.attempts_in_window(1120) == 1   # cutoff 1020, first aged out
    assert d.attempts_in_window(1500) == 0   # cutoff 1400, both aged out
