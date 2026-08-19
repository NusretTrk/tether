"""
Crash-safe snapshot of in-flight state that would otherwise live only in
memory. A restart (crash, Task Manager close + watchdog relaunch, a manual
update) used to silently drop whatever was staged, deferred, or awaiting
confirmation - the buttons the user had just been sent would quietly stop
doing anything, with no explanation.

Snapshotted periodically (state_snapshot_job, transport/jobs.py) rather
than at every individual mutation site - far fewer places that can get it
wrong, at the cost of up to one interval of staleness, which is fine for
what's actually being protected here.

Not everything is restored the same way - it depends on whether anything
has actually touched the target window yet:

- deferred_text/photo, staged_text/staged_photo, staged_cmd,
  pending_shutdown_minutes: nothing irreversible has happened yet
  (deferred: nothing sent at all; staged_text/photo: already pasted but
  Enter never pressed; staged_cmd/pending_shutdown: purely waiting on a
  button). Fully restored into live state - the Send/Confirm/Cancel
  buttons already sitting in the user's chat keep working exactly as
  before, since callbacks.py only ever reads state.*, never a message id.

- pending_send_*: Enter was ALREADY pressed before the crash - the
  message most likely went out. But confirming that relies on watching
  the transcript tailer for the matching event, and a fresh tailer starts
  reading from wherever the file currently ends, not from history - it
  can never see a line written before this process existed. Restoring
  this into the normal wait-for-confirmation path would just guarantee a
  false "failed" report after its 10s timeout on a message that most
  likely succeeded. Deliberately NOT restored the same way - surfaced as
  an honest "couldn't verify" notice instead, see restore_into() below.
"""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "state"
SNAPSHOT_PATH = STATE_DIR / "session_snapshot.json"


def save(state) -> None:
    data = {
        "deferred_text": state.deferred_text,
        "deferred_caption": state.deferred_caption,
        "deferred_message_id": state.deferred_message_id,
        "deferred_photo_b64": (
            base64.b64encode(state.deferred_photo_bytes).decode("ascii")
            if state.deferred_photo_bytes is not None else None
        ),
        "staged_text": state.staged_text,
        "staged_photo": state.staged_photo,
        "staged_cmd": state.staged_cmd,
        "pending_shutdown_minutes": state.pending_shutdown_minutes,
        "pending_send": (
            {"text": state.pending_send_text, "kind": state.pending_send_kind}
            if state.pending_send_text is not None or state.pending_send_message_id is not None
            else None
        ),
    }
    try:
        STATE_DIR.mkdir(exist_ok=True)
        tmp = SNAPSHOT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(SNAPSHOT_PATH)
    except OSError:
        log.warning("could not write session snapshot", exc_info=True)


def _load_and_clear() -> dict | None:
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = None
    SNAPSHOT_PATH.unlink(missing_ok=True)
    return data


def restore_into(state) -> dict:
    """Applies a saved snapshot (if any) to a freshly-built AppState.
    Returns a summary describing what was recovered so the caller can
    tell the user, rather than restoring silently. {} if there was
    nothing worth recovering."""
    data = _load_and_clear()
    if not data:
        return {}

    summary: dict = {}

    photo_b64 = data.get("deferred_photo_b64")
    if data.get("deferred_text") or photo_b64:
        state.deferred_text = data.get("deferred_text")
        state.deferred_photo_bytes = base64.b64decode(photo_b64) if photo_b64 else None
        state.deferred_caption = data.get("deferred_caption") or ""
        state.deferred_message_id = data.get("deferred_message_id")
        summary["deferred"] = True

    if data.get("staged_text") or data.get("staged_photo"):
        state.staged_text = data.get("staged_text")
        state.staged_photo = bool(data.get("staged_photo"))
        summary["staged"] = True

    if data.get("staged_cmd"):
        state.staged_cmd = data["staged_cmd"]
        summary["staged_cmd"] = True

    if data.get("pending_shutdown_minutes") is not None:
        state.pending_shutdown_minutes = data["pending_shutdown_minutes"]
        summary["pending_shutdown"] = True

    pending_send = data.get("pending_send")
    if pending_send:
        summary["unverified_send"] = pending_send.get("text") or None

    return summary
