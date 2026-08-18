"""
Byte-precise incremental tailer for a Claude Code transcript JSONL file.
Binary mode throughout — text-mode seek/tell is unreliable across multi-byte
UTF-8 characters and Windows line endings, so offsets are tracked in bytes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from tether.events import Event, parse_line

log = logging.getLogger(__name__)


class TranscriptTailer:
    def __init__(self, path: Path, from_start: bool = False):
        self.path = Path(path)
        try:
            self._offset = 0 if from_start else self.path.stat().st_size
        except FileNotFoundError:
            self._offset = 0

    def poll(self) -> list[Event]:
        """Reads any new complete lines since the last poll. A trailing
        incomplete line (file mid-write) is left for the next poll rather
        than dropped or parsed partially."""
        try:
            size = self.path.stat().st_size
        except FileNotFoundError:
            return []

        if size < self._offset:
            log.info("transcript %s shrank (rotated?), restarting from 0", self.path)
            self._offset = 0
        if size == self._offset:
            return []

        with open(self.path, "rb") as f:
            f.seek(self._offset)
            data = f.read()

        last_newline = data.rfind(b"\n")
        if last_newline == -1:
            return []  # no complete line yet

        complete, self._offset = data[:last_newline + 1], self._offset + last_newline + 1

        events: list[Event] = []
        for raw_line in complete.split(b"\n"):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                log.warning("skipping malformed transcript line in %s: %s", self.path, e)
                continue
            events.extend(parse_line(obj))
        return events
