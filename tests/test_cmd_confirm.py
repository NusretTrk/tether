"""
/cmd runs arbitrary shell commands with the user's own privileges - the
single most dangerous action in the bot, and until now the only
destructive one with no confirmation step at all. These check the new
stage-then-confirm flow, and specifically regression-test a real bug found
while adding it: the actual execution path never called html.escape() or
used parse_mode="HTML" despite a whole test file (test_cmd_output_escaping.py)
documenting that it should - that file only exercised a standalone helper,
never the real handler, so the gap went uncaught.
"""
import asyncio
from dataclasses import dataclass, field

from tether.platform import cmd_audit, shell
from tether.transport import callbacks, handlers

CHAT_ID = 44


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, txt, **kwargs):
        self.replies.append((txt, kwargs.get("reply_markup")))
        return type("M", (), {"message_id": 1})()


@dataclass
class FakeChat:
    id: int = CHAT_ID


class FakeUpdate:
    def __init__(self):
        self.effective_chat = FakeChat()
        self.message = FakeMessage()


class FakeSettings:
    language = "en"


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    staged_cmd: str | None = None


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []
        self.bot_data = {"state": FakeState()}


# --- cmd_cmd (staging) ----------------------------------------------------

def test_no_args_shows_usage_and_stages_nothing():
    update, context = FakeUpdate(), FakeContext([])
    asyncio.run(handlers.cmd_cmd(update, context))
    assert context.bot_data["state"].staged_cmd is None


def test_command_is_staged_not_executed(monkeypatch):
    calls = []
    monkeypatch.setattr(shell, "run_cmd", lambda cmd, **kw: calls.append(cmd))
    update, context = FakeUpdate(), FakeContext(["Remove-Item", "-Recurse", "C:\\"])
    asyncio.run(handlers.cmd_cmd(update, context))
    assert context.bot_data["state"].staged_cmd == "Remove-Item -Recurse C:\\"
    assert calls == [], "command must not run before confirmation"
    text, markup = update.message.replies[0]
    assert markup is not None


# --- callback: cmd:confirm / cmd:cancel -----------------------------------

class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.message = type("M", (), {"message_id": 9})()
        self.edits = []

    async def answer(self, *a, **kw):
        pass

    async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
        self.edits.append((text, parse_mode))


class FakeCallbackUpdate:
    def __init__(self, data):
        self.effective_chat = FakeChat()
        self.callback_query = FakeQuery(data)


def test_cancel_never_runs_the_command(monkeypatch):
    calls = []
    monkeypatch.setattr(shell, "run_cmd", lambda cmd, **kw: calls.append(cmd))
    update = FakeCallbackUpdate("cmd:cancel")
    context = FakeContext()
    context.bot_data["state"].staged_cmd = "shutdown /s /f /t 0"

    asyncio.run(callbacks.handle_callback(update, context))

    assert calls == []
    assert context.bot_data["state"].staged_cmd is None


def test_confirm_with_nothing_staged_is_a_noop(monkeypatch):
    calls = []
    monkeypatch.setattr(shell, "run_cmd", lambda cmd, **kw: calls.append(cmd))
    update = FakeCallbackUpdate("cmd:confirm")
    context = FakeContext()
    # staged_cmd left as None

    asyncio.run(callbacks.handle_callback(update, context))

    assert calls == []


async def _fake_run_cmd(command, **kwargs):
    return "<script>alert(1)</script>"


def test_confirm_runs_logs_and_escapes_output(monkeypatch):
    monkeypatch.setattr(shell, "run_cmd", _fake_run_cmd)
    logged = []
    monkeypatch.setattr(cmd_audit, "log_command", lambda cmd: logged.append(cmd))

    update = FakeCallbackUpdate("cmd:confirm")
    context = FakeContext()
    context.bot_data["state"].staged_cmd = "echo test"

    asyncio.run(callbacks.handle_callback(update, context))

    assert logged == ["echo test"], "executed command must be audit-logged"
    text, parse_mode = update.callback_query.edits[0]
    assert parse_mode == "HTML"
    assert "<script>" not in text, "raw HTML in command output must be escaped"
    assert "&lt;script&gt;" in text
    assert context.bot_data["state"].staged_cmd is None


async def _fake_run_cmd_raises(command, **kwargs):
    raise RuntimeError("boom <b>bad</b>")


def test_confirm_error_path_also_escapes_and_uses_html(monkeypatch):
    monkeypatch.setattr(shell, "run_cmd", _fake_run_cmd_raises)
    monkeypatch.setattr(cmd_audit, "log_command", lambda cmd: None)

    update = FakeCallbackUpdate("cmd:confirm")
    context = FakeContext()
    context.bot_data["state"].staged_cmd = "whatever"

    asyncio.run(callbacks.handle_callback(update, context))

    text, parse_mode = update.callback_query.edits[0]
    assert parse_mode == "HTML"
    assert "<b>bad</b>" not in text
    assert "&lt;b&gt;bad&lt;/b&gt;" in text
