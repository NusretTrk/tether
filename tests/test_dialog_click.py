"""
Remote dialog-button clicking - the user's own explicit ask ("if there's a
button I need to press, can I") after getting repeated "sign in again"
alerts with no way to act on them except walking up to the PC.

Two things get tested here: the safety filter (monitors/dialogs.py) that
keeps a tap target scoped to a small reviewed allowlist rather than every
button name a UIA scan happens to return (confirmed live: an unscoped scan
returns unrelated session names alongside the real dialog button), and the
actual click primitive (targets/claude_desktop.py) that only ever fires in
response to an explicit tap, never on its own.
"""
import asyncio
from dataclasses import dataclass, field

from tether.monitors.dialogs import SAFE_DIALOG_BUTTON_LABELS, safe_dialog_buttons
from tether.targets import claude_desktop as cd
from tether.targets.base import Dialog
from tether.transport import callbacks, jobs
from tether.transport.menus import CALLBACK_DATA_MAX_BYTES, dialog_button_menu


def test_safe_dialog_buttons_keeps_only_allowlisted_labels():
    real_scan = ["More navigation items", "Claude Tele Control", "HalalO",
                 "RepertuArt", "Other", "Dostum Dostum Pro", "Sign in again"]
    assert safe_dialog_buttons(real_scan) == ["Sign in again"]


def test_safe_dialog_buttons_is_case_and_whitespace_insensitive():
    assert safe_dialog_buttons(["  OK  ", "Cancel", "SIGN IN AGAIN"]) == ["  OK  ", "Cancel", "SIGN IN AGAIN"]


def test_safe_dialog_buttons_empty_input_empty_output():
    assert safe_dialog_buttons([]) == []


def test_safe_dialog_buttons_preserves_order_and_original_text():
    # order + exact original casing matter - click_dialog_button needs the
    # real on-screen text, not the lowercased allowlist form
    assert safe_dialog_buttons(["Close", "not a real button", "Retry"]) == ["Close", "Retry"]


def test_allowlist_has_no_accidental_substring_traps():
    """Every entry is a short, generic, whole-phrase dialog action - nothing
    on it should ever plausibly collide with a real session/project name.
    This isn't exhaustive, just a sanity check that the list wasn't
    accidentally widened to something dangerous later."""
    for label in SAFE_DIALOG_BUTTON_LABELS:
        assert len(label) <= 20
        assert label == label.lower()


def test_dialog_button_menu_builds_one_button_per_name():
    kb = dialog_button_menu(["Sign in again", "Cancel"])
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert labels == ["Sign in again", "Cancel"]
    assert data == ["dialogbtn:click:Sign in again", "dialogbtn:click:Cancel"]


def test_dialog_button_menu_returns_none_when_nothing_safe():
    assert dialog_button_menu([]) is None


def test_dialog_button_menu_drops_a_button_that_would_exceed_telegrams_limit():
    huge_name = "x" * CALLBACK_DATA_MAX_BYTES
    kb = dialog_button_menu(["Cancel", huge_name])
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert labels == ["Cancel"]


# ---- click_dialog_button (ClaudeDesktopTarget) ----

class FakeControl:
    def __init__(self):
        self.clicked = False

    def Click(self, simulateMove=False):
        self.clicked = True


def _patch_uia(monkeypatch, control, capabilities=True):
    import dataclasses
    monkeypatch.setattr(cd, "CAPABILITIES", dataclasses.replace(cd.CAPABILITIES, accessibility=capabilities))
    monkeypatch.setattr(cd.uia, "run_on_uia_thread", lambda fn: fn())
    monkeypatch.setattr(cd.uia, "find_root_window", lambda kw: 999)
    monkeypatch.setattr(cd.uia, "warm_up", lambda win: None)
    captured = {}

    def fake_find(win, name, control_type=None):
        captured["name"] = name
        captured["control_type"] = control_type
        return control

    monkeypatch.setattr(cd.uia, "find_control_by_name", fake_find)
    return captured


def test_click_dialog_button_clicks_the_matching_control(monkeypatch):
    control = FakeControl()
    captured = _patch_uia(monkeypatch, control)

    target = cd.ClaudeDesktopTarget("Claude")
    assert target.click_dialog_button("Sign in again") is True
    assert control.clicked is True
    assert captured == {"name": "Sign in again", "control_type": "ButtonControl"}


def test_click_dialog_button_returns_false_when_button_no_longer_exists(monkeypatch):
    _patch_uia(monkeypatch, control=None)
    target = cd.ClaudeDesktopTarget("Claude")
    assert target.click_dialog_button("Sign in again") is False


def test_click_dialog_button_false_when_window_not_found(monkeypatch):
    control = FakeControl()
    _patch_uia(monkeypatch, control)
    monkeypatch.setattr(cd.uia, "find_root_window", lambda kw: None)
    target = cd.ClaudeDesktopTarget("Claude")
    assert target.click_dialog_button("Sign in again") is False
    assert control.clicked is False


def test_click_dialog_button_false_without_accessibility_capability(monkeypatch):
    control = FakeControl()
    _patch_uia(monkeypatch, control, capabilities=False)
    target = cd.ClaudeDesktopTarget("Claude")
    assert target.click_dialog_button("Sign in again") is False
    assert control.clicked is False


def test_click_dialog_button_false_when_the_click_itself_raises(monkeypatch):
    class ExplodingControl:
        def Click(self, simulateMove=False):
            raise RuntimeError("element went stale mid-click")

    _patch_uia(monkeypatch, ExplodingControl())
    target = cd.ClaudeDesktopTarget("Claude")
    assert target.click_dialog_button("Sign in again") is False


# ---- dialog_job wires the safe subset into a real inline keyboard ----


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((text, kwargs.get("reply_markup")))


class FakeDialogWatcher:
    def __init__(self, dialogs):
        self._dialogs = dialogs

    def poll(self):
        return self._dialogs


class FakeSettings:
    language = "en"
    dialog_watch_enabled = True


class FakeSecrets:
    chat_id = 21


class FakeConfig:
    settings = FakeSettings()
    secrets = FakeSecrets()


@dataclass
class FakeState:
    dialog_watcher: FakeDialogWatcher
    config: FakeConfig = field(default_factory=FakeConfig)
    app_was_running: bool | None = True


class FakeContext:
    def __init__(self, dialogs):
        self.bot = FakeBot()
        self.bot_data = {"state": FakeState(dialog_watcher=FakeDialogWatcher(dialogs))}


def test_dialog_job_attaches_a_keyboard_for_a_recognized_button():
    dialogs = [Dialog(name="For your security, sign in again", buttons=["Other", "Sign in again"])]
    ctx = FakeContext(dialogs)
    asyncio.run(jobs.dialog_job(ctx))

    text, markup = ctx.bot.sent[0]
    assert "sign in again" in text.lower()
    labels = [btn.text for row in markup.inline_keyboard for btn in row]
    assert labels == ["Sign in again"]  # "Other" never becomes a tap target


def test_dialog_job_sends_no_keyboard_when_nothing_recognized():
    dialogs = [Dialog(name="something odd happened", buttons=["HalalO", "Dostum Dostum Pro"])]
    ctx = FakeContext(dialogs)
    asyncio.run(jobs.dialog_job(ctx))

    _, markup = ctx.bot.sent[0]
    assert markup is None


# ---- the callback handler that actually performs the click ----


class FakeTarget:
    def __init__(self, click_result):
        self._result = click_result
        self.clicked_name = None

    def click_dialog_button(self, name):
        self.clicked_name = name
        return self._result


class FakeQuery:
    def __init__(self, data):
        self.data = data
        self.answers = []
        self.message = type("M", (), {"message_id": 1})()

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))

    async def edit_message_text(self, *a, **kw):
        raise AssertionError("dialog button clicks must not edit the original alert away")


class FakeChat:
    id = 21


class FakeCallbackUpdate:
    def __init__(self, data):
        self.effective_chat = FakeChat()
        self.callback_query = FakeQuery(data)


@dataclass
class FakeCallbackState:
    target: FakeTarget
    config: FakeConfig = field(default_factory=FakeConfig)
    unlocked: bool = True


class FakeCallbackContext:
    def __init__(self, target):
        self.bot_data = {"state": FakeCallbackState(target=target)}


def test_dialogbtn_click_calls_the_target_and_reports_success():
    target = FakeTarget(click_result=True)
    update = FakeCallbackUpdate("dialogbtn:click:Sign in again")
    ctx = FakeCallbackContext(target)

    asyncio.run(callbacks.handle_callback(update, ctx))

    assert target.clicked_name == "Sign in again"
    text, show_alert = update.callback_query.answers[0]
    assert "Sign in again" in text
    assert show_alert is False


def test_dialogbtn_click_reports_failure_without_crashing():
    target = FakeTarget(click_result=False)
    update = FakeCallbackUpdate("dialogbtn:click:Sign in again")
    ctx = FakeCallbackContext(target)

    asyncio.run(callbacks.handle_callback(update, ctx))

    text, _ = update.callback_query.answers[0]
    assert "couldn't" in text.lower() or "already closed" in text.lower()
