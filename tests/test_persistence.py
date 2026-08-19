"""
persistence.py is what makes a crash or watchdog restart forget nothing
that hadn't already touched the target window. Tests use a bare object
with just the fields save()/restore_into() actually read or write, not a
real AppState (which needs a full Config) - same pattern as FakeState in
test_target_transcript_job.py.
"""
from dataclasses import dataclass

import pytest

from tether.transport import persistence


@dataclass
class FakeState:
    deferred_text: str | None = None
    deferred_caption: str = ""
    deferred_message_id: int | None = None
    deferred_photo_bytes: bytes | None = None
    staged_text: str | None = None
    staged_photo: bool = False
    staged_cmd: str | None = None
    pending_shutdown_minutes: float | None = None
    pending_send_text: str | None = None
    pending_send_kind: str = "text"
    pending_send_message_id: int | None = None


@pytest.fixture(autouse=True)
def isolated_snapshot_path(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "STATE_DIR", tmp_path)
    monkeypatch.setattr(persistence, "SNAPSHOT_PATH", tmp_path / "session_snapshot.json")


def test_restore_into_with_no_snapshot_file_is_a_noop():
    state = FakeState()
    assert persistence.restore_into(state) == {}
    assert state.deferred_text is None


def test_deferred_text_round_trips():
    saved = FakeState(deferred_text="hello", deferred_caption="cap", deferred_message_id=42)
    persistence.save(saved)

    restored = FakeState()
    summary = persistence.restore_into(restored)

    assert summary == {"deferred": True}
    assert restored.deferred_text == "hello"
    assert restored.deferred_caption == "cap"
    assert restored.deferred_message_id == 42


def test_deferred_photo_bytes_round_trip_through_base64():
    photo_bytes = bytes(range(256)) * 4  # non-trivial binary content
    saved = FakeState(deferred_photo_bytes=photo_bytes, deferred_caption="a photo")
    persistence.save(saved)

    restored = FakeState()
    summary = persistence.restore_into(restored)

    assert summary == {"deferred": True}
    assert restored.deferred_photo_bytes == photo_bytes
    assert restored.deferred_text is None


def test_staged_text_is_restored():
    saved = FakeState(staged_text="about to send this")
    persistence.save(saved)

    restored = FakeState()
    assert persistence.restore_into(restored) == {"staged": True}
    assert restored.staged_text == "about to send this"
    assert restored.staged_photo is False


def test_staged_photo_flag_is_restored_without_needing_bytes():
    saved = FakeState(staged_photo=True)
    persistence.save(saved)

    restored = FakeState()
    assert persistence.restore_into(restored) == {"staged": True}
    assert restored.staged_photo is True
    assert restored.staged_text is None


def test_staged_cmd_is_restored():
    saved = FakeState(staged_cmd="Get-Process")
    persistence.save(saved)

    restored = FakeState()
    assert persistence.restore_into(restored) == {"staged_cmd": True}
    assert restored.staged_cmd == "Get-Process"


def test_pending_shutdown_minutes_is_restored():
    saved = FakeState(pending_shutdown_minutes=15.0)
    persistence.save(saved)

    restored = FakeState()
    assert persistence.restore_into(restored) == {"pending_shutdown": True}
    assert restored.pending_shutdown_minutes == 15.0


def test_pending_shutdown_of_zero_minutes_is_still_restored():
    """0.0 is falsy but a legitimate pending value - must use an is-None
    check, not truthiness, or a same-minute shutdown request silently
    vanishes across a restart."""
    saved = FakeState(pending_shutdown_minutes=0.0)
    persistence.save(saved)

    restored = FakeState()
    assert persistence.restore_into(restored) == {"pending_shutdown": True}
    assert restored.pending_shutdown_minutes == 0.0


def test_pending_send_is_surfaced_as_unverified_not_restored_into_wait_flow():
    """Enter was already pressed before the crash - a fresh transcript
    tailer can never see a pre-restart confirmation line, so silently
    re-arming the normal wait-and-confirm path would just guarantee a
    false 'failed' report. Must come back as a notice, not live state."""
    saved = FakeState(pending_send_text="my message", pending_send_message_id=7)
    persistence.save(saved)

    restored = FakeState()
    summary = persistence.restore_into(restored)

    assert summary == {"unverified_send": "my message"}
    assert restored.pending_send_text is None


def test_pending_send_photo_has_no_text_but_is_still_surfaced():
    saved = FakeState(pending_send_text=None, pending_send_kind="image", pending_send_message_id=7)
    persistence.save(saved)

    restored = FakeState()
    summary = persistence.restore_into(restored)

    assert summary == {"unverified_send": None}
    assert "unverified_send" in summary


def test_nothing_in_flight_produces_no_snapshot_worth_restoring():
    saved = FakeState()
    persistence.save(saved)

    restored = FakeState()
    assert persistence.restore_into(restored) == {}


def test_snapshot_is_cleared_after_being_restored_once():
    saved = FakeState(staged_text="x")
    persistence.save(saved)

    assert persistence.restore_into(FakeState()) == {"staged": True}
    assert persistence.restore_into(FakeState()) == {}


def test_corrupted_snapshot_file_is_discarded_not_raised(tmp_path):
    persistence.SNAPSHOT_PATH.parent.mkdir(exist_ok=True)
    persistence.SNAPSHOT_PATH.write_text("not valid json{{{", encoding="utf-8")

    assert persistence.restore_into(FakeState()) == {}
    assert not persistence.SNAPSHOT_PATH.exists()


def test_multiple_in_flight_fields_all_come_back_together():
    saved = FakeState(deferred_text="d", staged_cmd="whoami", pending_shutdown_minutes=5.0)
    persistence.save(saved)

    restored = FakeState()
    summary = persistence.restore_into(restored)

    assert summary == {"deferred": True, "staged_cmd": True, "pending_shutdown": True}
    assert restored.deferred_text == "d"
    assert restored.staged_cmd == "whoami"
    assert restored.pending_shutdown_minutes == 5.0
