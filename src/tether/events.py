"""
Normalized event model for Claude Code transcript lines. Shapes here were
verified against a live transcript, not guessed — see
docs/superpowers/specs/2026-08-18-tether-remote-agent-control-design.md §2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EventType(Enum):
    USER_TEXT = "user_text"
    ASSISTANT_TEXT = "assistant_text"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    IMAGE = "image"
    SYSTEM = "system"


@dataclass
class Event:
    type: EventType
    uuid: str
    timestamp: str
    text: str = ""
    tool_name: str | None = None
    tool_input: dict | None = None
    is_error: bool = False
    raw: dict = field(default_factory=dict)


def _flatten_text(content) -> str:
    """tool_result content is sometimes a plain string, sometimes a list of
    {"type": "text", "text": ...} blocks — normalize both to a string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def parse_line(obj: dict) -> list[Event]:
    """Parses one decoded JSONL line into zero or more normalized Events.
    Unknown top-level types (custom-title, mode, queue-operation, last-prompt,
    attachment) are not conversation content and yield nothing — tolerated,
    not an error, since new ones may appear in future Claude Code versions."""
    t = obj.get("type")
    uuid = obj.get("uuid", "")
    timestamp = obj.get("timestamp", "")
    events: list[Event] = []

    if t == "assistant":
        content = obj.get("message", {}).get("content", []) or []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                events.append(Event(EventType.ASSISTANT_TEXT, uuid, timestamp, text=block.get("text", ""), raw=block))
            elif btype == "thinking":
                events.append(Event(EventType.THINKING, uuid, timestamp, text=block.get("thinking", ""), raw=block))
            elif btype == "tool_use":
                events.append(Event(
                    EventType.TOOL_CALL, uuid, timestamp,
                    tool_name=block.get("name"), tool_input=block.get("input"), raw=block,
                ))

    elif t == "user":
        msg = obj.get("message", {})
        content = msg.get("content")
        if isinstance(content, str):
            events.append(Event(EventType.USER_TEXT, uuid, timestamp, text=content, raw=obj))
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "tool_result":
                    events.append(Event(
                        EventType.TOOL_RESULT, uuid, timestamp,
                        text=_flatten_text(block.get("content")),
                        is_error=bool(block.get("is_error")),
                        raw={**block, "toolUseResult": obj.get("toolUseResult", {})},
                    ))
                elif btype == "image":
                    events.append(Event(EventType.IMAGE, uuid, timestamp, raw=block))
                elif btype == "text":
                    events.append(Event(EventType.USER_TEXT, uuid, timestamp, text=block.get("text", ""), raw=block))

    elif t == "system":
        text = obj.get("content")
        if not isinstance(text, str):
            text = str(obj.get("message", "") or "")
        events.append(Event(EventType.SYSTEM, uuid, timestamp, text=text, raw=obj))

    return events
