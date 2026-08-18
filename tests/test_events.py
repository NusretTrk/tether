"""Event parsing tests using fixtures shaped exactly like real transcript
lines observed live (see design spec §2)."""
from tether.events import EventType, parse_line


def test_user_plain_string_content():
    obj = {"type": "user", "uuid": "u1", "timestamp": "t1", "message": {"role": "user", "content": "hello"}}
    events = parse_line(obj)
    assert len(events) == 1
    assert events[0].type == EventType.USER_TEXT
    assert events[0].text == "hello"


def test_assistant_text_block():
    obj = {
        "type": "assistant", "uuid": "a1", "timestamp": "t2",
        "message": {"role": "assistant", "content": [{"type": "text", "text": "hi there"}]},
    }
    events = parse_line(obj)
    assert len(events) == 1
    assert events[0].type == EventType.ASSISTANT_TEXT
    assert events[0].text == "hi there"


def test_assistant_thinking_block():
    obj = {
        "type": "assistant", "uuid": "a2", "timestamp": "t3",
        "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "pondering", "signature": "x"}]},
    }
    events = parse_line(obj)
    assert events[0].type == EventType.THINKING
    assert events[0].text == "pondering"


def test_assistant_tool_use_block():
    obj = {
        "type": "assistant", "uuid": "a3", "timestamp": "t4",
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "tu1", "name": "PowerShell", "input": {"command": "dir"}}
        ]},
    }
    events = parse_line(obj)
    assert events[0].type == EventType.TOOL_CALL
    assert events[0].tool_name == "PowerShell"
    assert events[0].tool_input == {"command": "dir"}


def test_user_tool_result_string_content():
    obj = {
        "type": "user", "uuid": "u2", "timestamp": "t5",
        "message": {"role": "user", "content": [
            {"tool_use_id": "tu1", "type": "tool_result", "content": "output text", "is_error": False}
        ]},
        "toolUseResult": {"stdout": "output text", "stderr": "", "interrupted": False, "isImage": False},
    }
    events = parse_line(obj)
    assert events[0].type == EventType.TOOL_RESULT
    assert events[0].text == "output text"
    assert events[0].is_error is False


def test_user_tool_result_error():
    obj = {
        "type": "user", "uuid": "u3", "timestamp": "t6",
        "message": {"role": "user", "content": [
            {"tool_use_id": "tu2", "type": "tool_result", "content": "boom", "is_error": True}
        ]},
    }
    events = parse_line(obj)
    assert events[0].is_error is True


def test_user_tool_result_list_content_blocks():
    """Some tool_result content is itself a list of {"type":"text",...} blocks."""
    obj = {
        "type": "user", "uuid": "u4", "timestamp": "t7",
        "message": {"role": "user", "content": [
            {"tool_use_id": "tu3", "type": "tool_result",
             "content": [{"type": "text", "text": "part1"}, {"type": "text", "text": "part2"}],
             "is_error": False}
        ]},
    }
    events = parse_line(obj)
    assert events[0].text == "part1part2"


def test_user_image_block():
    obj = {
        "type": "user", "uuid": "u5", "timestamp": "t8",
        "message": {"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}}
        ]},
    }
    events = parse_line(obj)
    assert events[0].type == EventType.IMAGE


def test_system_event():
    obj = {"type": "system", "uuid": "s1", "timestamp": "t9", "content": "Conversation compacted"}
    events = parse_line(obj)
    assert events[0].type == EventType.SYSTEM
    assert events[0].text == "Conversation compacted"


def test_unknown_top_level_type_yields_nothing():
    for t in ("custom-title", "mode", "queue-operation", "last-prompt", "attachment"):
        assert parse_line({"type": t, "uuid": "x", "timestamp": "y"}) == []


def test_malformed_content_does_not_raise():
    # content is None, or blocks aren't dicts — must not raise
    assert parse_line({"type": "assistant", "message": {"content": None}}) == []
    assert parse_line({"type": "assistant", "message": {"content": ["not-a-dict"]}}) == []
    assert parse_line({"type": "user", "message": {"content": [123, None]}}) == []
