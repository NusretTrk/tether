"""
Normalizes Antigravity's own transcript.jsonl lines into the same Event
model transcript.py builds from Claude Code's - found by reading a real
one, not guessed: Antigravity IDE keeps a per-conversation transcript at
~/.gemini/<product>/brain/<uuid>/.system_generated/logs/transcript.jsonl,
same idea as Claude Code's ~/.claude/projects/*.jsonl, just a different
vocabulary of `type` values.

Deliberately conservative about what gets mapped to something visible:
EPHEMERAL_MESSAGE and SYSTEM_MESSAGE, verified against a real 1000+ line
transcript, turned out to be internal prompt-injection reminders and
inter-agent bookkeeping ("The following is a <EPHEMERAL_MESSAGE> not
actually sent by the user... do NOT respond to this message") - not
conversation content, and relaying them would be noise at best and
confusing at worst. Only what a human actually asked or was actually told
back gets surfaced.
"""
from __future__ import annotations

import re

from tether.events import Event, EventType

_USER_REQUEST_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.DOTALL)

# Antigravity logs a tool call and its result as ONE record (unlike Claude
# Code, which logs a tool_use and a separate tool_result) - mapped to
# TOOL_RESULT here since that's the record that actually carries output
# text, and it's what verbose/live mode already knows how to render.
_TOOL_RESULT_TYPES = {
    "RUN_COMMAND", "CODE_ACTION", "VIEW_FILE", "LIST_DIRECTORY",
    "SEARCH_WEB", "GREP_SEARCH", "INVOKE_SUBAGENT",
}

# Internal bookkeeping / prompt injection, never conversation content.
_SKIP_TYPES = {
    "CONVERSATION_HISTORY", "KNOWLEDGE_ARTIFACTS", "CHECKPOINT",
    "EPHEMERAL_MESSAGE", "SYSTEM_MESSAGE", "GENERIC",
}


def _extract_user_request(content: str) -> str:
    """Strips the <ADDITIONAL_METADATA>/<USER_SETTINGS_CHANGE> wrapper
    Antigravity adds around what was actually typed, so only the real
    message gets relayed - the wrapper is context for the model, not
    something the human needs echoed back to them."""
    match = _USER_REQUEST_RE.search(content)
    return match.group(1).strip() if match else content.strip()


def parse_antigravity_line(obj: dict) -> list[Event]:
    """Parses one decoded transcript.jsonl line into zero or more
    normalized Events. Unknown types are skipped, not an error - the
    format isn't documented and may add new ones without notice."""
    t = obj.get("type")
    timestamp = obj.get("created_at", "")
    uuid = f"{obj.get('step_index', '')}"
    content = obj.get("content", "") or ""

    if t == "USER_INPUT":
        return [Event(EventType.USER_TEXT, uuid, timestamp, text=_extract_user_request(content))]

    if t == "PLANNER_RESPONSE":
        return [Event(EventType.ASSISTANT_TEXT, uuid, timestamp, text=content)]

    if t == "ERROR_MESSAGE":
        return [Event(EventType.TOOL_RESULT, uuid, timestamp, text=obj.get("error") or content, is_error=True)]

    if t in _TOOL_RESULT_TYPES:
        return [Event(EventType.TOOL_RESULT, uuid, timestamp, text=content, tool_name=t)]

    if t in _SKIP_TYPES or t is None:
        return []

    return []
