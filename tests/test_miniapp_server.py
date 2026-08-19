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

    def list_sessions(self):
        return self.sessions

    def switch_session(self, name):
        self.switched_to = name
        return any(s.name == name for s in self.sessions)

    def read_status(self):
        return self.status


@dataclass
class FakeSettings:
    language: str = "en"
    output_mode: str = "summary"
    confirm_before_send: bool = True
    mini_app_enabled: bool = True
    mini_app_ngrok_domain: str = "test.ngrok-free.app"
    mini_app_local_port: int = 0
    saved: list = field(default_factory=list)

    def save(self):
        self.saved.append(True)


@dataclass
class FakeSecrets:
    bot_token: str = BOT_TOKEN
    chat_id: int = CHAT_ID


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


def test_repeated_bad_auth_trips_lockout_and_fires_one_alert(running_server, monkeypatch):
    server, base, state = running_server
    alerts = []
    monkeypatch.setattr(server, "_bridge_send_message", lambda text: alerts.append(text))

    for _ in range(20):
        _request(base + "/api/status", headers={"Authorization": "tma bogus"})

    status, body = _request(base + "/api/status", headers={"Authorization": "tma " + valid_init_data()})
    assert status == 429
    assert len(alerts) == 1  # fired exactly once, not once per failed attempt


def test_unknown_route_is_404(running_server):
    _, base, _ = running_server
    status, body = _request(base + "/api/does-not-exist")
    assert status == 404


def test_favicon_returns_no_content_without_auth(running_server):
    _, base, _ = running_server
    req = urllib.request.Request(base + "/favicon.ico")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 204
