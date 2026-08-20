"""
End-to-end tests against a real MiniAppServer bound to 127.0.0.1 on a
random port, driven with real HTTP requests carrying genuinely-signed
initData (same signing helper as test_miniapp_auth.py) - this is the
actual security boundary of the whole feature, so it's exercised as
close to the real request path as practical rather than unit-testing
route functions in isolation.
"""
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlencode

import pytest

from tether.miniapp.server import MiniAppServer
from tether.targets.base import Session, TargetStatus

BOT_TOKEN = "123456:AAtestFakeTokenForUnitTestsOnly"
CHAT_ID = 123456789


def sign(fields, bot_token=BOT_TOKEN):
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def valid_init_data(user_id=CHAT_ID):
    return sign({
        "query_id": "q1",
        "user": json.dumps({"id": user_id, "first_name": "Test"}),
        "auth_date": str(int(time.time())),
    })


class FakeTarget:
    def __init__(self):
        self.switched_to = None
        self.sessions = [Session(name="proj-a", running=True), Session(name="proj-b", running=False)]
        self.status = TargetStatus(model="Sonnet", effort="high")
        self.staged_texts = []
        self.enter_presses = 0
        self.set_model_calls = []

    def set_model(self, name):
        self.set_model_calls.append(name)
        matches = {"sonnet": "Sonnet", "opus": "Opus", "haiku": "Haiku"}
        return matches.get(name.lower())

    def list_sessions(self):
        return self.sessions

    def switch_session(self, name):
        self.switched_to = name
        return any(s.name == name for s in self.sessions)

    def read_status(self):
        return self.status

    def stage_text(self, text):
        self.staged_texts.append(text)
        from tether.targets.base import PasteResult
        return PasteResult(True)

    def press_enter(self):
        self.enter_presses += 1
        return True


@dataclass
class FakeSettings:
    language: str = "en"
    output_mode: str = "summary"
    confirm_before_send: bool = True
    mini_app_enabled: bool = True
    mini_app_ngrok_domain: str = "test.ngrok-free.app"
    mini_app_local_port: int = 0
    dialog_watch_enabled: bool = True
    stall_watch_enabled: bool = True
    activity_watch_enabled: bool = True
    app_health_watch_enabled: bool = True
    usage_limit_continue_enabled: bool = True
    preserve_user_clipboard: bool = True
    temp_emergency_c: int = 90
    defer_when_user_active_sec: int = 20
    auto_send_after_idle_sec: int = 45
    saved: list = field(default_factory=list)

    def save(self):
        self.saved.append(True)


@dataclass
class FakeSecrets:
    bot_token: str = BOT_TOKEN
    chat_id: int = CHAT_ID
    bot_password: str | None = None


@dataclass
class FakeConfig:
    settings: FakeSettings = field(default_factory=FakeSettings)
    secrets: FakeSecrets = field(default_factory=FakeSecrets)


@dataclass
class FakeState:
    target: FakeTarget = field(default_factory=FakeTarget)
    config: FakeConfig = field(default_factory=FakeConfig)
    active_target_profile: str | None = None
    tailer_path = None
    target_tailer_path = None
    miniapp_server: object = None
    ngrok_runner: object = None
    unlocked: bool = True  # default matches the common case (no BOT_PASSWORD set)
    web_token_hash: str | None = None
    deferred_text: str | None = None
    deferred_photo_bytes: bytes | None = None
    deferred_caption: str = ""
    deferred_message_id: int | None = None
    staged_text: str | None = None
    pending_send_text: str | None = None
    pending_send_message_id: int | None = None
    pending_send_since: float = 0.0
    staged_cmd: str | None = None


@pytest.fixture
def running_server():
    state = FakeState()
    server = MiniAppServer(("127.0.0.1", 0), state, bot=None, event_loop=None)
    import threading
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield server, f"http://127.0.0.1:{port}", state
    server.shutdown()
    server.server_close()


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self.sent.append(text)
        return type("M", (), {"message_id": 1})()


@pytest.fixture
def send_capable_server(monkeypatch):
    """/api/send bridges onto a real asyncio event loop (the same way the
    live bot's own loop is used) - spun up on its own background thread
    here so the test can drive it with plain synchronous HTTP calls."""
    import asyncio
    import threading

    monkeypatch.setattr("tether.transport.text.is_user_active", lambda threshold: False)

    state = FakeState()
    loop_ready = threading.Event()
    holder = {}

    def run_loop():
        loop = asyncio.new_event_loop()
        holder["loop"] = loop
        asyncio.set_event_loop(loop)
        loop_ready.set()
        loop.run_forever()

    loop_thread = threading.Thread(target=run_loop, daemon=True)
    loop_thread.start()
    loop_ready.wait(timeout=5)

    bot = FakeBot()
    server = MiniAppServer(("127.0.0.1", 0), state, bot=bot, event_loop=holder["loop"])
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    port = server.server_address[1]

    yield server, f"http://127.0.0.1:{port}", state, bot

    server.shutdown()
    server.server_close()
    holder["loop"].call_soon_threadsafe(holder["loop"].stop)
    server.shutdown()
    server.server_close()


def _request(url, method="GET", headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_index_page_serves_without_auth(running_server):
    _, base, _ = running_server
    with urllib.request.urlopen(base + "/", timeout=5) as resp:
        assert resp.status == 200
        body = resp.read().decode()
    assert "tether" in body
    assert "Telegram" in body


def test_api_request_without_auth_header_is_rejected(running_server):
    _, base, _ = running_server
    status, body = _request(base + "/api/status")
    assert status == 401
    assert body["error"] == "missing_input"


def test_responses_carry_standard_hardening_headers(running_server):
    _, base, _ = running_server
    with urllib.request.urlopen(base + "/", timeout=5) as resp:
        headers = resp.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("Referrer-Policy") == "no-referrer"
    assert headers.get("X-Frame-Options") is None  # would break Telegram Web/Desktop's iframe


def test_server_header_does_not_advertise_python_version(running_server):
    """Found via `curl -I` against the real running server: the stdlib
    default Server header is "BaseHTTP/0.6 Python/3.12.1" - a free, exact
    fingerprint handed to anyone who requests it, for no reason a real
    client needs. Not itself an exploit, but there's no reason to leak it."""
    _, base, _ = running_server
    with urllib.request.urlopen(base + "/", timeout=5) as resp:
        server_header = resp.headers.get("Server", "")
    assert "Python" not in server_header
    assert "." not in server_header  # no version number of any kind


def test_idle_connection_is_closed_rather_than_held_forever(running_server):
    """Confirmed live before this fix: opening a raw socket and never
    sending anything kept the connection (and one of the 20 concurrent
    slots) alive indefinitely - ~20 such connections would lock the real
    owner out of their own tunnel. socketserver's built-in `timeout`
    class attribute is what actually closes it; this proves it end to
    end against the real server rather than just asserting the
    attribute is set."""
    import socket
    _, base, _ = running_server
    port = int(base.rsplit(":", 1)[1])

    sock = socket.create_connection(("127.0.0.1", port), timeout=15)
    sock.settimeout(15)
    start = time.time()
    try:
        data = sock.recv(1024)  # server-initiated close arrives as EOF (b"")
    finally:
        sock.close()
    elapsed = time.time() - start

    assert data == b""
    assert elapsed < 15  # closed on its own well before our socket-level timeout


def test_api_request_with_bad_signature_is_rejected(running_server):
    _, base, _ = running_server
    status, body = _request(base + "/api/status", headers={"Authorization": "tma bogus=data&hash=nope"})
    assert status == 401


def test_status_with_valid_auth_returns_target_status(running_server):
    _, base, _ = running_server
    status, body = _request(base + "/api/status", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 200
    assert body["model"] == "Sonnet"
    assert body["effort"] == "high"
    assert body["output_mode"] == "summary"


def test_sessions_list_returns_fake_sessions(running_server):
    _, base, _ = running_server
    status, body = _request(base + "/api/sessions", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 200
    names = {s["name"] for s in body["sessions"]}
    assert names == {"proj-a", "proj-b"}


def test_session_switch_calls_target(running_server):
    server, base, state = running_server
    status, body = _request(
        base + "/api/sessions/switch", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"name": "proj-b"},
    )
    assert status == 200
    assert body["ok"] is True
    assert state.target.switched_to == "proj-b"


def test_session_switch_missing_name_is_rejected(running_server):
    _, base, _ = running_server
    status, body = _request(
        base + "/api/sessions/switch", method="POST",
        headers={"Authorization": "tma " + valid_init_data()}, body={},
    )
    assert status == 400


def test_settings_get_returns_current_values(running_server):
    _, base, _ = running_server
    status, body = _request(base + "/api/settings", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 200
    assert body["language"] == "en"
    assert body["confirm_before_send"] is True


def test_settings_post_updates_allowed_key(running_server):
    server, base, state = running_server
    status, body = _request(
        base + "/api/settings", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"key": "output_mode", "value": "quiet"},
    )
    assert status == 200
    assert state.config.settings.output_mode == "quiet"
    assert state.config.settings.saved  # settings.save() was called


def test_settings_post_rejects_unknown_key(running_server):
    _, base, _ = running_server
    status, body = _request(
        base + "/api/settings", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"key": "bot_password", "value": "hunter2"},
    )
    assert status == 400
    assert body["error"] == "unknown_key"


def test_settings_post_rejects_invalid_value_for_known_key(running_server):
    _, base, _ = running_server
    status, body = _request(
        base + "/api/settings", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"key": "output_mode", "value": "not_a_real_mode"},
    )
    assert status == 400
    assert body["error"] == "invalid_value"


def test_mini_app_enabled_toggle_reapplies_lifecycle_after_responding(running_server, monkeypatch):
    """Toggling mini_app_enabled off from inside the Mini App itself has
    to be able to tear this very server down - done on a separate thread,
    after the response is flushed, so the request handler never blocks
    on its own server's shutdown(). Real apply_mini_app_state is
    replaced here since exercising the real start/stop machinery isn't
    the point of this test - just that it's invoked, once, post-response."""
    import threading
    server, base, state = running_server
    called = threading.Event()
    calls = []

    def fake_apply(st, bot, loop):
        calls.append((st, bot, loop))
        called.set()

    monkeypatch.setattr("tether.miniapp.lifecycle.apply_mini_app_state", fake_apply)

    status, body = _request(
        base + "/api/settings", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"key": "mini_app_enabled", "value": False},
    )
    assert status == 200
    assert called.wait(timeout=2)
    assert len(calls) == 1
    assert calls[0][0] is state


def test_wrong_chat_id_signature_is_rejected(running_server):
    _, base, _ = running_server
    status, body = _request(base + "/api/status", headers={"Authorization": "tma " + valid_init_data(user_id=999)})
    assert status == 401
    assert body["error"] == "wrong_chat"


def test_valid_signature_is_rejected_while_bot_password_is_locked(running_server):
    """This is the real point of BOT_PASSWORD: it protects against the
    owner's own Telegram account being compromised, a scenario where the
    attacker's initData is genuinely, validly signed (they ARE the
    authorized chat_id as far as Telegram's concerned). A validly-signed
    request must not bypass this second factor."""
    server, base, state = running_server
    state.config.secrets.bot_password = "hunter2"
    state.unlocked = False

    status, body = _request(base + "/api/status", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 423
    assert body["error"] == "locked"


def test_valid_signature_works_once_unlocked(running_server):
    server, base, state = running_server
    state.config.secrets.bot_password = "hunter2"
    state.unlocked = True

    status, body = _request(base + "/api/status", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 200


def test_locked_rejection_does_not_count_toward_lockout(running_server):
    """Being locked isn't a forged/bad signature - a real owner who just
    hasn't unlocked yet shouldn't get treated like an attacker and
    eventually rate-limited out of their own bot."""
    server, base, state = running_server
    state.config.secrets.bot_password = "hunter2"
    state.unlocked = False

    for _ in range(15):
        status, _ = _request(base + "/api/status", headers={"Authorization": "tma " + valid_init_data()})
        assert status == 423

    state.unlocked = True
    status, body = _request(base + "/api/status", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 200  # not 429 - never got treated as auth failures


def test_no_bot_password_set_ignores_unlocked_flag(running_server):
    """The common case (BOT_PASSWORD never set) must behave exactly as
    before this check existed - state.unlocked is irrelevant when there's
    no password to unlock in the first place."""
    server, base, state = running_server
    state.config.secrets.bot_password = None
    state.unlocked = False

    status, body = _request(base + "/api/status", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 200


def test_repeated_bad_auth_trips_lockout_and_fires_one_alert(running_server, monkeypatch):
    server, base, state = running_server
    alerts = []
    monkeypatch.setattr(server, "_bridge_send_message", lambda text: alerts.append(text))

    for _ in range(20):
        _request(base + "/api/status", headers={"Authorization": "tma bogus"})

    status, body = _request(base + "/api/status", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 429
    assert len(alerts) == 1  # fired exactly once, not once per failed attempt


def test_bearer_token_matching_hash_is_accepted(running_server):
    from tether.miniapp import webtoken
    server, base, state = running_server
    raw = "a-real-web-token"
    state.web_token_hash = webtoken.hash_token(raw)

    status, body = _request(base + "/api/status", headers={"Authorization": "Bearer " + raw})
    assert status == 200


def test_bearer_token_not_matching_hash_is_rejected(running_server):
    from tether.miniapp import webtoken
    server, base, state = running_server
    state.web_token_hash = webtoken.hash_token("the-real-token")

    status, body = _request(base + "/api/status", headers={"Authorization": "Bearer wrong-token"})
    assert status == 401
    assert body["error"] == "bad_web_token"


def test_bearer_token_rejected_when_none_has_ever_been_issued(running_server):
    server, base, state = running_server
    assert state.web_token_hash is None

    status, body = _request(base + "/api/status", headers={"Authorization": "Bearer anything"})
    assert status == 401


def test_bearer_token_also_respects_the_bot_password_lock(running_server):
    from tether.miniapp import webtoken
    server, base, state = running_server
    raw = "a-real-web-token"
    state.web_token_hash = webtoken.hash_token(raw)
    state.config.secrets.bot_password = "secret"
    state.unlocked = False

    status, body = _request(base + "/api/status", headers={"Authorization": "Bearer " + raw})
    assert status == 423
    assert body["error"] == "locked"


def test_bad_bearer_tokens_count_toward_the_same_lockout_as_bad_init_data(running_server, monkeypatch):
    from tether.miniapp import webtoken
    server, base, state = running_server
    state.web_token_hash = webtoken.hash_token("the-real-token")
    alerts = []
    monkeypatch.setattr(server, "_bridge_send_message", lambda text: alerts.append(text))

    for _ in range(20):
        _request(base + "/api/status", headers={"Authorization": "Bearer wrong"})

    status, body = _request(base + "/api/status", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 429
    assert len(alerts) == 1


def test_unknown_route_is_404(running_server):
    _, base, _ = running_server
    status, body = _request(base + "/api/does-not-exist")
    assert status == 404


def test_favicon_returns_no_content_without_auth(running_server):
    _, base, _ = running_server
    req = urllib.request.Request(base + "/favicon.ico")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 204


def test_settings_get_includes_watcher_toggles_and_thresholds(running_server):
    _, base, _ = running_server
    status, body = _request(base + "/api/settings", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 200
    assert body["dialog_watch_enabled"] is True
    assert body["temp_emergency_c"] == 90


def test_settings_post_updates_a_watcher_toggle(running_server):
    server, base, state = running_server
    status, body = _request(
        base + "/api/settings", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"key": "stall_watch_enabled", "value": False},
    )
    assert status == 200
    assert state.config.settings.stall_watch_enabled is False


def test_settings_post_updates_a_numeric_threshold_within_bounds(running_server):
    server, base, state = running_server
    status, body = _request(
        base + "/api/settings", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"key": "temp_emergency_c", "value": 85},
    )
    assert status == 200
    assert state.config.settings.temp_emergency_c == 85


def test_settings_post_rejects_numeric_value_out_of_bounds(running_server):
    _, base, state = running_server
    status, body = _request(
        base + "/api/settings", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"key": "temp_emergency_c", "value": 999},
    )
    assert status == 400
    assert body["error"] == "invalid_value"
    assert state.config.settings.temp_emergency_c == 90  # unchanged


def test_settings_post_rejects_non_integer_for_numeric_key(running_server):
    _, base, _ = running_server
    status, body = _request(
        base + "/api/settings", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"key": "temp_emergency_c", "value": "hot"},
    )
    assert status == 400
    assert body["error"] == "invalid_value"


def test_settings_post_rejects_bool_value_for_numeric_key(running_server):
    """isinstance(True, int) is True in Python - a bare `true` sent for a
    numeric field must not silently become 1, or slip past bounds checks
    that assume a real number."""
    _, base, _ = running_server
    status, body = _request(
        base + "/api/settings", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"key": "temp_emergency_c", "value": True},
    )
    assert status == 400
    assert body["error"] == "invalid_value"


def test_connection_over_cap_is_dropped_without_spawning_a_thread(running_server, monkeypatch):
    """ThreadingHTTPServer has no built-in concurrency limit - an
    internet-facing instance (this one, via ngrok) needs one, or a flood
    of connections spawns an unbounded number of OS threads. Exercised
    directly against process_request rather than opening real sockets,
    since simulating hundreds of held-open connections isn't practical
    in a unit test."""
    from tether.miniapp import server as server_mod

    server, base, state = running_server
    monkeypatch.setattr(server_mod, "MAX_CONCURRENT_CONNECTIONS", 1)

    shutdown_calls = []
    monkeypatch.setattr(server, "shutdown_request", lambda req: shutdown_calls.append(req))

    spawned = []
    monkeypatch.setattr(
        server_mod.ThreadingHTTPServer, "process_request",
        lambda self, request, addr: spawned.append(request),
    )

    server.process_request("req-1", ("127.0.0.1", 1))  # fills the one slot
    assert spawned == ["req-1"]
    assert server._active_connections == 1

    server.process_request("req-2", ("127.0.0.1", 2))  # over cap - dropped
    assert shutdown_calls == ["req-2"]
    assert "req-2" not in spawned


# --- /api/send: the Mini App's own compose box, wired through the exact
# same transport.text.send_text_to_target real Telegram messages use. ---

def test_send_requires_auth(send_capable_server):
    server, base, state, bot = send_capable_server
    status, body = _request(base + "/api/send", method="POST", body={"text": "hello"})
    assert status == 401


def test_send_types_the_message_and_presses_enter(send_capable_server):
    server, base, state, bot = send_capable_server
    state.config.settings.confirm_before_send = False
    status, body = _request(
        base + "/api/send", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"text": "hello claude"},
    )
    assert status == 200
    assert body["status"] == "sent_pending_verification"
    assert state.target.staged_texts == ["hello claude"]
    assert state.target.enter_presses == 1


def test_send_respects_confirm_before_send(send_capable_server):
    server, base, state, bot = send_capable_server
    state.config.settings.confirm_before_send = True

    status, body = _request(
        base + "/api/send", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"text": "hello claude"},
    )
    assert status == 200
    assert body["status"] == "staged"
    assert state.target.enter_presses == 0, "must not press enter before confirmation"
    assert state.staged_text == "hello claude"


def test_send_a_telegram_notification_is_sent_too(send_capable_server):
    """The Mini App's own send still produces the normal Telegram-side
    confirmation message - it's an additional way to send, not a silent
    side channel invisible from the chat."""
    server, base, state, bot = send_capable_server
    _request(
        base + "/api/send", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"text": "hello claude"},
    )
    assert len(bot.sent) >= 1


def test_send_rejects_empty_text(send_capable_server):
    server, base, state, bot = send_capable_server
    status, body = _request(
        base + "/api/send", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"text": "   "},
    )
    assert status == 400
    assert body["error"] == "missing_text"
    assert state.target.staged_texts == []


def test_send_rejects_missing_text_key(send_capable_server):
    server, base, state, bot = send_capable_server
    status, body = _request(
        base + "/api/send", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={},
    )
    assert status == 400
    assert body["error"] == "missing_text"


def test_send_rejects_overly_long_text(send_capable_server):
    server, base, state, bot = send_capable_server
    status, body = _request(
        base + "/api/send", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"text": "x" * 5000},
    )
    assert status == 400
    assert body["error"] == "text_too_long"
    assert state.target.staged_texts == []


def test_send_is_deferred_when_user_is_active(send_capable_server, monkeypatch):
    monkeypatch.setattr("tether.transport.text.is_user_active", lambda threshold: True)
    monkeypatch.setattr("tether.transport.text.idle_seconds", lambda: 2.0)
    server, base, state, bot = send_capable_server

    status, body = _request(
        base + "/api/send", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"text": "hello claude"},
    )
    assert status == 200
    assert body["status"] == "deferred"
    assert state.target.staged_texts == [], "window must not be touched while the user is active"
    assert state.deferred_text == "hello claude"


# --- /api/models, /api/model: model switching from the Status view ---

def test_models_lists_the_fixed_claude_desktop_set(running_server):
    _, base, state = running_server
    status, body = _request(base + "/api/models", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 200
    assert body["models"] == ["Fable", "Opus", "Sonnet", "Haiku"]
    assert body["current"] == "Sonnet"


def test_model_set_switches_and_reports_the_matched_name(running_server):
    _, base, state = running_server
    status, body = _request(
        base + "/api/model", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"name": "opus"},
    )
    assert status == 200
    assert body["model"] == "Opus"
    assert state.target.set_model_calls == ["opus"]


def test_model_set_with_no_match_returns_409(running_server):
    _, base, state = running_server
    status, body = _request(
        base + "/api/model", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"name": "not-a-real-model"},
    )
    assert status == 409
    assert body["model"] is None


def test_model_set_requires_a_name(running_server):
    _, base, state = running_server
    status, body = _request(
        base + "/api/model", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={},
    )
    assert status == 400
    assert body["error"] == "missing_name"


def test_models_requires_auth(running_server):
    _, base, state = running_server
    status, body = _request(base + "/api/models")
    assert status == 401


# --- /api/cmd/stage, /api/cmd/confirm, /api/cmd/cancel: reuses /cmd's
# own stage-then-confirm shape and audit log, plus posts the result back
# to the real Telegram chat so a command run from the Mini App is never
# a silent side channel invisible from there. ---

def test_cmd_stage_sets_staged_cmd(send_capable_server):
    server, base, state, bot = send_capable_server
    status, body = _request(
        base + "/api/cmd/stage", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"command": "Get-Process"},
    )
    assert status == 200
    assert state.staged_cmd == "Get-Process"


def test_cmd_stage_rejects_empty_command(send_capable_server):
    server, base, state, bot = send_capable_server
    status, body = _request(
        base + "/api/cmd/stage", method="POST",
        headers={"Authorization": "tma " + valid_init_data()},
        body={"command": "   "},
    )
    assert status == 400
    assert body["error"] == "missing_command"
    assert state.staged_cmd is None


def test_cmd_cancel_clears_without_running_anything(send_capable_server, monkeypatch):
    monkeypatch.setattr(
        "tether.transport.cmd_exec.execute_command",
        lambda cmd: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    server, base, state, bot = send_capable_server
    state.staged_cmd = "Get-Process"

    status, body = _request(base + "/api/cmd/cancel", method="POST", headers={"Authorization": "tma " + valid_init_data()})

    assert status == 200
    assert state.staged_cmd is None


def test_cmd_confirm_with_nothing_staged_is_rejected(send_capable_server):
    server, base, state, bot = send_capable_server
    status, body = _request(base + "/api/cmd/confirm", method="POST", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 400
    assert body["error"] == "nothing_staged"


def test_cmd_confirm_runs_the_staged_command_and_notifies_telegram(send_capable_server, monkeypatch):
    async def fake_execute(command):
        return True, "process list here"

    monkeypatch.setattr("tether.transport.cmd_exec.execute_command", fake_execute)
    server, base, state, bot = send_capable_server
    state.staged_cmd = "Get-Process"

    status, body = _request(base + "/api/cmd/confirm", method="POST", headers={"Authorization": "tma " + valid_init_data()})

    assert status == 200
    assert body["ok"] is True
    assert body["output"] == "process list here"
    assert state.staged_cmd is None
    assert any("process list here" in m for m in bot.sent), "result must also be posted to the real Telegram chat"


def test_cmd_confirm_failure_still_notifies_telegram_and_reports_ok_false(send_capable_server, monkeypatch):
    async def fake_execute(command):
        return False, "something broke"

    monkeypatch.setattr("tether.transport.cmd_exec.execute_command", fake_execute)
    server, base, state, bot = send_capable_server
    state.staged_cmd = "bad-command"

    status, body = _request(base + "/api/cmd/confirm", method="POST", headers={"Authorization": "tma " + valid_init_data()})

    assert status == 200
    assert body["ok"] is False
    assert any("something broke" in m for m in bot.sent)
