"""
File-based handoff between the MCP server process and the main bot process
for `ask`. Telegram's getUpdates (receiving) only allows one active
long-poll consumer per bot token — the main bot already holds that
connection, so the MCP server can't poll for replies itself. Sending
(sendMessage) has no such restriction, so `notify` needs no handoff at all;
only `ask`, which needs to receive a reply, does.

Protocol: the MCP server writes ask_pending.json with a question id, then
polls for ask_answer_<id>.json to appear. The main bot's text handler checks
for a pending question on every incoming message from the operator and, if
one exists, treats that message as the answer instead of routing it to the
target app.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "state"


def _ensure_dir() -> None:
    STATE_DIR.mkdir(exist_ok=True)


def pending_path() -> Path:
    return STATE_DIR / "ask_pending.json"


def answer_path(question_id: str) -> Path:
    return STATE_DIR / f"ask_answer_{question_id}.json"


def write_pending(question_id: str, question: str) -> None:
    _ensure_dir()
    pending_path().write_text(
        json.dumps({"id": question_id, "question": question, "ts": time.time()}),
        encoding="utf-8",
    )


def read_pending() -> dict | None:
    path = pending_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def clear_pending(question_id: str | None = None) -> None:
    pending = read_pending()
    if pending is None:
        return
    if question_id is not None and pending.get("id") != question_id:
        return
    pending_path().unlink(missing_ok=True)


def write_answer(question_id: str, answer: str) -> None:
    _ensure_dir()
    answer_path(question_id).write_text(json.dumps({"answer": answer}), encoding="utf-8")


def read_and_clear_answer(question_id: str) -> str | None:
    path = answer_path(question_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    path.unlink(missing_ok=True)
    return data.get("answer")
