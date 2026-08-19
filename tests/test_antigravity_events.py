"""
parse_antigravity_line normalizes Antigravity's own transcript.jsonl lines
into the same Event model Claude Code's transcript produces. Every shape
here is copied from a REAL transcript.jsonl on this machine (both a fresh
"hi" exchange and a 1000+ line real coding session), not invented -
particularly the EPHEMERAL_MESSAGE/SYSTEM_MESSAGE skip, which matters:
those turned out to be internal prompt-injection reminders, not
conversation content, and relaying them verbatim would flood the chat with
"do NOT respond to this message, just act accordingly" style system text.
"""
from tether.events import EventType
from tether.sources.antigravity_events import parse_antigravity_line


def test_user_input_strips_the_metadata_wrapper():
    obj = {
        "step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE",
        "created_at": "2026-08-19T13:56:01Z",
        "content": (
            "<USER_REQUEST>\nhi\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\n"
            "The current local time is: 2026-08-19T16:56:01+03:00.\n</ADDITIONAL_METADATA>\n"
            "<USER_SETTINGS_CHANGE>\nThe user changed setting `Model Selection`...\n</USER_SETTINGS_CHANGE>"
        ),
    }
    events = parse_antigravity_line(obj)
    assert len(events) == 1
    assert events[0].type == EventType.USER_TEXT
    assert events[0].text == "hi"


def test_user_input_without_wrapper_tags_falls_back_to_raw_content():
    obj = {"type": "USER_INPUT", "content": "plain text, no tags"}
    events = parse_antigravity_line(obj)
    assert events[0].text == "plain text, no tags"


def test_planner_response_becomes_assistant_text():
    obj = {
        "step_index": 3, "source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE",
        "created_at": "2026-08-19T13:56:01Z",
        "content": "Hello! I'm Antigravity, your AI coding assistant.",
    }
    events = parse_antigravity_line(obj)
    assert len(events) == 1
    assert events[0].type == EventType.ASSISTANT_TEXT
    assert events[0].text == "Hello! I'm Antigravity, your AI coding assistant."


def test_run_command_becomes_tool_result():
    obj = {
        "step_index": 26, "source": "MODEL", "type": "RUN_COMMAND", "status": "DONE",
        "created_at": "2026-07-06T23:28:06Z",
        "content": "Created At: ...\nCompleted At: ...\nThe command completed successfully.\nOutput:\nnpm warn...",
    }
    events = parse_antigravity_line(obj)
    assert len(events) == 1
    assert events[0].type == EventType.TOOL_RESULT
    assert events[0].tool_name == "RUN_COMMAND"
    assert not events[0].is_error


def test_error_message_becomes_tool_result_flagged_as_error():
    obj = {
        "step_index": 130, "source": "SYSTEM", "type": "ERROR_MESSAGE", "status": "DONE",
        "created_at": "2026-07-06T23:55:27Z",
        "error": "There was a problem parsing the tool call.",
        "content": "Created At: ...\nError invalid tool call: ...",
    }
    events = parse_antigravity_line(obj)
    assert len(events) == 1
    assert events[0].type == EventType.TOOL_RESULT
    assert events[0].is_error
    assert "problem parsing" in events[0].text


def test_ephemeral_message_is_skipped_not_relayed():
    """Verified against a real transcript: this is an internal prompt
    reminder ("do NOT respond to this message"), not conversation content."""
    obj = {
        "type": "EPHEMERAL_MESSAGE", "source": "SYSTEM",
        "content": "The following is an <EPHEMERAL_MESSAGE> not actually sent by the user...",
    }
    assert parse_antigravity_line(obj) == []


def test_system_message_is_skipped_not_relayed():
    obj = {"type": "SYSTEM_MESSAGE", "source": "SYSTEM", "content": "internal inter-agent note"}
    assert parse_antigravity_line(obj) == []


def test_checkpoint_conversation_history_and_knowledge_artifacts_are_skipped():
    for t in ("CHECKPOINT", "CONVERSATION_HISTORY", "KNOWLEDGE_ARTIFACTS", "GENERIC"):
        assert parse_antigravity_line({"type": t, "content": "whatever"}) == []


def test_unknown_type_is_skipped_not_an_error():
    assert parse_antigravity_line({"type": "SOME_FUTURE_TYPE_NOT_YET_SEEN", "content": "x"}) == []


def test_missing_type_is_skipped():
    assert parse_antigravity_line({"content": "no type field at all"}) == []


def test_view_file_list_directory_search_web_grep_search_all_map_to_tool_result():
    for t in ("VIEW_FILE", "LIST_DIRECTORY", "SEARCH_WEB", "GREP_SEARCH", "CODE_ACTION", "INVOKE_SUBAGENT"):
        events = parse_antigravity_line({"type": t, "content": "some output"})
        assert len(events) == 1
        assert events[0].type == EventType.TOOL_RESULT
        assert events[0].tool_name == t
