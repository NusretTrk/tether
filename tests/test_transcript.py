"""TranscriptTailer tests — incremental reads, partial trailing lines,
rotation/truncation, malformed lines."""
import json

import pytest

from tether.sources.transcript import TranscriptTailer


def _line(obj) -> bytes:
    return (json.dumps(obj) + "\n").encode("utf-8")


def test_reads_new_complete_lines_incrementally(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_bytes(_line({"type": "system", "uuid": "1", "timestamp": "t", "content": "first"}))

    tailer = TranscriptTailer(path, from_start=True)
    events = tailer.poll()
    assert len(events) == 1
    assert events[0].text == "first"

    # nothing new yet
    assert tailer.poll() == []

    with open(path, "ab") as f:
        f.write(_line({"type": "system", "uuid": "2", "timestamp": "t", "content": "second"}))
    events = tailer.poll()
    assert len(events) == 1
    assert events[0].text == "second"


def test_incomplete_trailing_line_deferred_to_next_poll(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_bytes(_line({"type": "system", "uuid": "1", "timestamp": "t", "content": "complete"}))
    tailer = TranscriptTailer(path, from_start=True)
    assert len(tailer.poll()) == 1

    # append a line with no trailing newline yet (mid-write)
    with open(path, "ab") as f:
        f.write(b'{"type": "system", "uuid": "2", "timestamp": "t", "content": "partial"')
    assert tailer.poll() == []  # not committed — no trailing \n

    with open(path, "ab") as f:
        f.write(b'}\n')
    events = tailer.poll()
    assert len(events) == 1
    assert events[0].text == "partial"


def test_malformed_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_bytes(
        _line({"type": "system", "uuid": "1", "timestamp": "t", "content": "before"})
        + b"{not valid json at all\n"
        + _line({"type": "system", "uuid": "2", "timestamp": "t", "content": "after"})
    )
    tailer = TranscriptTailer(path, from_start=True)
    events = tailer.poll()
    texts = [e.text for e in events]
    assert texts == ["before", "after"]


def test_from_start_false_skips_existing_content(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_bytes(_line({"type": "system", "uuid": "1", "timestamp": "t", "content": "old"}))
    tailer = TranscriptTailer(path, from_start=False)
    assert tailer.poll() == []

    with open(path, "ab") as f:
        f.write(_line({"type": "system", "uuid": "2", "timestamp": "t", "content": "new"}))
    events = tailer.poll()
    assert len(events) == 1
    assert events[0].text == "new"


def test_file_shrinking_restarts_from_zero(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_bytes(_line({"type": "system", "uuid": "1", "timestamp": "t", "content": "a" * 100}))
    tailer = TranscriptTailer(path, from_start=True)
    tailer.poll()

    # simulate rotation: file replaced with something smaller
    path.write_bytes(_line({"type": "system", "uuid": "2", "timestamp": "t", "content": "new-and-short"}))
    events = tailer.poll()
    assert len(events) == 1
    assert events[0].text == "new-and-short"


def test_missing_file_returns_empty_not_raises(tmp_path):
    path = tmp_path / "does_not_exist.jsonl"
    tailer = TranscriptTailer(path, from_start=True)
    assert tailer.poll() == []
