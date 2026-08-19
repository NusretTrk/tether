"""Usage-limit continuer: reset-time parsing and attempt-capping, tested as
pure logic. Every branch here is a case where getting it wrong means either
never auto-resuming, or auto-resuming at the wrong time, or looping."""
from datetime import datetime, timedelta

from tether.monitors.usage_limit import ContinueDecider, ContinuePolicy, parse_reset_time


def make_decider(enabled=True, max_attempts=3, window=21600.0):
    return ContinueDecider(ContinuePolicy(enabled=enabled, max_attempts=max_attempts, attempt_window_sec=window))


# --- parse_reset_time -------------------------------------------------

def test_parses_at_time_with_pm():
    now = datetime(2026, 8, 19, 10, 0)
    result = parse_reset_time("Usage limit reached. It resets at 3pm.", now)
    assert result == datetime(2026, 8, 19, 15, 0)


def test_parses_at_time_with_am():
    now = datetime(2026, 8, 19, 10, 0)
    result = parse_reset_time("resets at 6am", now)
    assert result == datetime(2026, 8, 19, 6, 0) + timedelta(days=1)


def test_parses_at_time_with_minutes():
    now = datetime(2026, 8, 19, 10, 0)
    result = parse_reset_time("resets at 3:45 PM", now)
    assert result == datetime(2026, 8, 19, 15, 45)


def test_parses_24h_time_with_no_meridiem():
    now = datetime(2026, 8, 19, 10, 0)
    result = parse_reset_time("resets at 15:30", now)
    assert result == datetime(2026, 8, 19, 15, 30)


def test_at_time_already_passed_today_rolls_to_tomorrow():
    now = datetime(2026, 8, 19, 16, 0)
    result = parse_reset_time("resets at 3pm", now)
    assert result == datetime(2026, 8, 20, 15, 0)


def test_parses_in_hours_and_minutes():
    now = datetime(2026, 8, 19, 10, 0)
    result = parse_reset_time("resets in 2 hours 15 minutes", now)
    assert result == datetime(2026, 8, 19, 12, 15)


def test_parses_in_hours_only():
    now = datetime(2026, 8, 19, 10, 0)
    result = parse_reset_time("Your limit resets in 4 hours.", now)
    assert result == datetime(2026, 8, 19, 14, 0)


def test_parses_in_minutes_only():
    now = datetime(2026, 8, 19, 10, 0)
    result = parse_reset_time("resets in 45 minutes", now)
    assert result == datetime(2026, 8, 19, 10, 45)


def test_no_recognizable_reset_phrase_returns_none():
    now = datetime(2026, 8, 19, 10, 0)
    assert parse_reset_time("You've hit your rate limit. Try again later.", now) is None


def test_garbage_hour_returns_none():
    now = datetime(2026, 8, 19, 10, 0)
    assert parse_reset_time("resets at 99:00", now) is None


def test_hour_over_12_with_meridiem_returns_none():
    now = datetime(2026, 8, 19, 10, 0)
    assert parse_reset_time("resets at 13pm", now) is None


def test_case_insensitive():
    now = datetime(2026, 8, 19, 10, 0)
    result = parse_reset_time("RESETS AT 3PM", now)
    assert result == datetime(2026, 8, 19, 15, 0)


# --- ContinueDecider ----------------------------------------------------

def test_can_schedule_when_enabled_and_under_cap():
    d = make_decider()
    assert d.can_schedule(1000)


def test_cannot_schedule_when_disabled():
    d = make_decider(enabled=False)
    assert not d.can_schedule(1000)


def test_attempt_cap_blocks_after_max_reached():
    d = make_decider(max_attempts=2)
    d.record_attempt(1000)
    d.record_attempt(1001)
    assert not d.can_schedule(1002)


def test_attempt_cap_allows_again_after_window_expires():
    d = make_decider(max_attempts=2, window=100.0)
    d.record_attempt(1000)
    d.record_attempt(1001)
    assert not d.can_schedule(1002)
    assert d.can_schedule(1200)  # both aged out of the 100s window
