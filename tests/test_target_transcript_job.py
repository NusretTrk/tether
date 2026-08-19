"""
target_transcript_job is the actual mechanism behind "read {target}'s
replies back" - it must stay a no-op whenever no transcript-capable
profile is active (the overwhelmingly common case, since most sessions
never touch /target at all), and it must never let switching /target
affect the separate Claude transcript relay.
"""
import asyncio
from dataclasses import dataclass, field

from tether.transport import jobs

CHAT_ID = 66


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(text)


class FakeSettings:
    language = "en"
    output_mode = "summary"
    keypad_profiles = {
        "antigravity": {"window_keyword": "Antigravity", "transcript_source": "antigravity"},
        "cursor": {"window_keyword": "Cursor"},  # no transcript_source
    }


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    active_target_profile: str | None = None
    target_tailer: object = None
    target_tailer_path: object = None
    target_transcript_poll_count: int = 0


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()
        self.bot_data = {"state": FakeState()}


def test_noop_when_no_target_profile_active():
    ctx = FakeContext()
    ctx.bot_data["state"].active_target_profile = None
    asyncio.run(jobs.target_transcript_job(ctx))
    assert ctx.bot.sent == []
    assert ctx.bot_data["state"].target_tailer is None


def test_noop_when_active_profile_has_no_transcript_source():
    ctx = FakeContext()
    ctx.bot_data["state"].active_target_profile = "cursor"
    asyncio.run(jobs.target_transcript_job(ctx))
    assert ctx.bot.sent == []
    assert ctx.bot_data["state"].target_tailer is None


def test_noop_when_profile_name_is_unknown():
    ctx = FakeContext()
    ctx.bot_data["state"].active_target_profile = "does_not_exist"
    asyncio.run(jobs.target_transcript_job(ctx))
    assert ctx.bot.sent == []


class FakeTailer:
    def __init__(self, events):
        self._events = events

    def poll(self):
        events, self._events = self._events, []
        return events


def test_assistant_text_is_relayed_with_target_name_prefix():
    from tether.events import Event, EventType
    ctx = FakeContext()
    state = ctx.bot_data["state"]
    state.active_target_profile = "antigravity"
    state.target_tailer = FakeTailer([Event(EventType.ASSISTANT_TEXT, "1", "t", text="hello from antigravity")])
    state.target_tailer_path = "already-set"  # target_tailer already set -> discovery re-check is skipped

    asyncio.run(jobs.target_transcript_job(ctx))

    assert len(ctx.bot.sent) == 1
    assert "[antigravity]" in ctx.bot.sent[0]
    assert "hello from antigravity" in ctx.bot.sent[0]


def test_tool_result_only_relayed_in_verbose_or_live_mode():
    from tether.events import Event, EventType
    ctx = FakeContext()
    state = ctx.bot_data["state"]
    state.active_target_profile = "antigravity"
    state.target_tailer = FakeTailer([Event(EventType.TOOL_RESULT, "1", "t", text="ran a command", tool_name="RUN_COMMAND")])
    state.target_tailer_path = "already-set"

    FakeSettings.output_mode = "summary"
    asyncio.run(jobs.target_transcript_job(ctx))
    assert ctx.bot.sent == [], "tool results should not appear in summary mode"

    state.target_tailer = FakeTailer([Event(EventType.TOOL_RESULT, "1", "t", text="ran a command", tool_name="RUN_COMMAND")])
    FakeSettings.output_mode = "verbose"
    try:
        asyncio.run(jobs.target_transcript_job(ctx))
    finally:
        FakeSettings.output_mode = "summary"
    assert len(ctx.bot.sent) == 1
    assert "ran a command" in ctx.bot.sent[0]


def test_error_tool_result_gets_error_icon():
    from tether.events import Event, EventType
    ctx = FakeContext()
    state = ctx.bot_data["state"]
    state.active_target_profile = "antigravity"
    state.target_tailer = FakeTailer([Event(EventType.TOOL_RESULT, "1", "t", text="it broke", is_error=True)])
    state.target_tailer_path = "already-set"

    FakeSettings.output_mode = "verbose"
    try:
        asyncio.run(jobs.target_transcript_job(ctx))
    finally:
        FakeSettings.output_mode = "summary"
    assert "❌" in ctx.bot.sent[0]


def test_quiet_mode_suppresses_everything():
    from tether.events import Event, EventType
    ctx = FakeContext()
    state = ctx.bot_data["state"]
    state.active_target_profile = "antigravity"
    state.target_tailer = FakeTailer([Event(EventType.ASSISTANT_TEXT, "1", "t", text="hello")])
    state.target_tailer_path = "already-set"

    FakeSettings.output_mode = "quiet"
    try:
        asyncio.run(jobs.target_transcript_job(ctx))
    finally:
        FakeSettings.output_mode = "summary"
    assert ctx.bot.sent == []


def test_no_events_sends_nothing():
    ctx = FakeContext()
    state = ctx.bot_data["state"]
    state.active_target_profile = "antigravity"
    state.target_tailer = FakeTailer([])
    state.target_tailer_path = "already-set"
    asyncio.run(jobs.target_transcript_job(ctx))
    assert ctx.bot.sent == []
