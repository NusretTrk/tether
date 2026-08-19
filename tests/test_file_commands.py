"""
/files and /file wire the pure resolve_safe_path/list_recent_files logic
(tested separately in test_file_retrieval.py) into the bot - this checks
that wiring: no project detected, nothing found, a match too large to
send, and the happy path actually calling send_document with the right
file, both from the command and from the /files inline button.
"""
import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from tether.transport import callbacks, handlers

CHAT_ID = 77


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
    remote_file_extensions = [".md"]
    remote_file_list_limit = 15
    remote_file_max_bytes = 20_000_000


class FakeSecrets:
    chat_id = CHAT_ID


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    recent_files: list = field(default_factory=list)


class FakeBot:
    def __init__(self):
        self.sent_documents = []

    async def send_document(self, chat_id, document, **kwargs):
        self.sent_documents.append((chat_id, document))


class FakeContext:
    def __init__(self, args=None):
        self.args = args or []
        self.bot_data = {"state": FakeState()}
        self.bot = FakeBot()


# --- cmd_files -------------------------------------------------------

def test_files_no_project_detected(monkeypatch):
    monkeypatch.setattr(handlers, "_project_root", lambda state: None)
    update, context = FakeUpdate(), FakeContext()
    asyncio.run(handlers.cmd_files(update, context))
    assert "project" in update.message.replies[0][0].lower()

def test_files_none_found(monkeypatch, tmp_path):
    monkeypatch.setattr(handlers, "_project_root", lambda state: tmp_path)
    import tether.sources.files as files_mod
    monkeypatch.setattr(files_mod, "list_recent_files", lambda root, exts, limit: [])
    update, context = FakeUpdate(), FakeContext()
    asyncio.run(handlers.cmd_files(update, context))
    assert context.bot_data["state"].recent_files == []


def test_files_found_caches_and_shows_menu(monkeypatch, tmp_path):
    f = tmp_path / "notes.md"
    monkeypatch.setattr(handlers, "_project_root", lambda state: tmp_path)
    import tether.sources.files as files_mod
    monkeypatch.setattr(files_mod, "list_recent_files", lambda root, exts, limit: [f])
    update, context = FakeUpdate(), FakeContext()
    asyncio.run(handlers.cmd_files(update, context))
    assert context.bot_data["state"].recent_files == [f]
    text, markup = update.message.replies[0]
    assert markup is not None


# --- cmd_file ----------------------------------------------------------

def test_file_no_args_shows_usage():
    update, context = FakeUpdate(), FakeContext([])
    asyncio.run(handlers.cmd_file(update, context))
    assert context.bot.sent_documents == []


def test_file_no_project_detected(monkeypatch):
    monkeypatch.setattr(handlers, "_project_root", lambda state: None)
    update, context = FakeUpdate(), FakeContext(["notes.md"])
    asyncio.run(handlers.cmd_file(update, context))
    assert context.bot.sent_documents == []


def test_file_not_resolved_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(handlers, "_project_root", lambda state: tmp_path)
    import tether.sources.files as files_mod
    monkeypatch.setattr(files_mod, "resolve_safe_path", lambda root, req: None)
    update, context = FakeUpdate(), FakeContext(["../secret.txt"])
    asyncio.run(handlers.cmd_file(update, context))
    assert context.bot.sent_documents == []
    assert "not" in update.message.replies[0][0].lower() or "outside" in update.message.replies[0][0].lower()


def test_file_too_large_is_refused(monkeypatch, tmp_path):
    big = tmp_path / "big.md"
    big.write_bytes(b"x" * 100)
    monkeypatch.setattr(handlers, "_project_root", lambda state: tmp_path)
    import tether.sources.files as files_mod
    monkeypatch.setattr(files_mod, "resolve_safe_path", lambda root, req: big)
    monkeypatch.setattr(FakeSettings, "remote_file_max_bytes", 10)
    update, context = FakeUpdate(), FakeContext(["big.md"])
    asyncio.run(handlers.cmd_file(update, context))
    assert context.bot.sent_documents == []


def test_file_success_sends_document(monkeypatch, tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(handlers, "_project_root", lambda state: tmp_path)
    import tether.sources.files as files_mod
    monkeypatch.setattr(files_mod, "resolve_safe_path", lambda root, req: f)
    update, context = FakeUpdate(), FakeContext(["notes.md"])
    asyncio.run(handlers.cmd_file(update, context))
    assert len(context.bot.sent_documents) == 1
    assert context.bot.sent_documents[0][0] == CHAT_ID


# --- callback: file:send:<idx> ------------------------------------------

class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.message = type("M", (), {"message_id": 9})()

    async def answer(self, *a, **kw):
        pass

    async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
        self.edits = getattr(self, "edits", [])
        self.edits.append(text)


class FakeCallbackUpdate:
    def __init__(self, data):
        self.effective_chat = FakeChat()
        self.callback_query = FakeQuery(data)


def test_callback_sends_cached_file_by_index(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("hi", encoding="utf-8")
    update = FakeCallbackUpdate("file:send:0")
    context = FakeContext()
    context.bot_data["state"].recent_files = [f]

    asyncio.run(callbacks.handle_callback(update, context))

    assert len(context.bot.sent_documents) == 1


def test_callback_out_of_range_index_is_refused():
    update = FakeCallbackUpdate("file:send:5")
    context = FakeContext()
    context.bot_data["state"].recent_files = []

    asyncio.run(callbacks.handle_callback(update, context))

    assert context.bot.sent_documents == []
    assert update.callback_query.edits


def test_callback_file_no_longer_existing_is_refused(tmp_path):
    f = tmp_path / "gone.md"
    update = FakeCallbackUpdate("file:send:0")
    context = FakeContext()
    context.bot_data["state"].recent_files = [f]

    asyncio.run(callbacks.handle_callback(update, context))

    assert context.bot.sent_documents == []
