"""
Caps repeated /unlock guesses, tested as pure logic - same rigor as
RecoveryDecider/ContinueDecider since getting this wrong either lets a
compromised Telegram account brute-force the password, or locks the real
owner out forever.
"""
from tether.monitors.lockout import LockoutDecider, LockoutPolicy


def make(max_attempts=5, window=300.0):
    return LockoutDecider(LockoutPolicy(max_attempts=max_attempts, window_sec=window))


def test_not_locked_out_with_no_failures():
    d = make()
    assert not d.is_locked_out(1000)


def test_locked_out_after_max_attempts():
    d = make(max_attempts=3)
    for i in range(3):
        d.record_failure(1000 + i)
    assert d.is_locked_out(1003)


def test_not_locked_out_below_max_attempts():
    d = make(max_attempts=3)
    d.record_failure(1000)
    d.record_failure(1001)
    assert not d.is_locked_out(1002)


def test_old_failures_age_out_of_the_window():
    d = make(max_attempts=3, window=100.0)
    for i in range(3):
        d.record_failure(1000 + i)
    assert d.is_locked_out(1000 + 50)
    assert not d.is_locked_out(1000 + 500), "failures outside the window should be forgiven"


def test_reset_clears_failures():
    d = make(max_attempts=1)
    d.record_failure(1000)
    assert d.is_locked_out(1001)
    d.reset()
    assert not d.is_locked_out(1002)
