"""
apply_mini_app_state is the one place that decides whether the Mini
App's server + tunnel should actually be running, called from startup,
/settings, and the Mini App's own settings screen. Exercised against
fakes for the server/runner it manages, not real network resources.
"""
from dataclasses import dataclass, field

from tether.miniapp import lifecycle


@dataclass
class FakeSettings:
    mini_app_enabled: bool = False
    mini_app_ngrok_domain: str = ""
    mini_app_ngrok_path: str = "ngrok"
    mini_app_local_port: int = 8743
    language: str = "en"


@dataclass
class FakeSecrets:
    chat_id: int = 123
    ngrok_authtoken: str | None = None


@dataclass
class FakeConfig:
    settings: FakeSettings = field(default_factory=FakeSettings)
    secrets: FakeSecrets = field(default_factory=FakeSecrets)


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    miniapp_server: object = None
    ngrok_runner: object = None


class FakeServer:
    stopped = False

    def shutdown(self):
        self.stopped = True

    def server_close(self):
        pass


class FakeRunner:
    def __init__(self, *a, **k):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        return True

    def stop(self):
        self.stopped = True


def fully_configured_state(enabled=True):
    return FakeState(config=FakeConfig(
        settings=FakeSettings(mini_app_enabled=enabled, mini_app_ngrok_domain="me.ngrok-free.app"),
        secrets=FakeSecrets(ngrok_authtoken="tok"),
    ))


def test_does_nothing_when_disabled_and_not_running(monkeypatch):
    calls = []
    monkeypatch.setattr("tether.transport.menu_button.schedule_menu_button_sync", lambda *a: calls.append(a))
    state = FakeState()  # disabled, no domain, no token
    lifecycle.apply_mini_app_state(state, bot=None, event_loop=None)
    assert state.miniapp_server is None
    assert len(calls) == 1  # menu button still synced (to Commands)


def test_starts_server_and_runner_when_should_run(monkeypatch):
    started_server = FakeServer()
    monkeypatch.setattr("tether.miniapp.server.start", lambda state, bot, loop: started_server)
    monkeypatch.setattr("tether.miniapp.lifecycle.NgrokRunner", FakeRunner)
    monkeypatch.setattr("tether.transport.menu_button.schedule_menu_button_sync", lambda *a: None)

    state = fully_configured_state(enabled=True)
    lifecycle.apply_mini_app_state(state, bot=None, event_loop=None)

    assert state.miniapp_server is started_server
    assert isinstance(state.ngrok_runner, FakeRunner)
    assert state.ngrok_runner.started


def test_stops_server_and_runner_when_disabled_while_running(monkeypatch):
    monkeypatch.setattr("tether.transport.menu_button.schedule_menu_button_sync", lambda *a: None)
    server = FakeServer()
    runner = FakeRunner()
    state = fully_configured_state(enabled=False)
    state.miniapp_server = server
    state.ngrok_runner = runner

    lifecycle.apply_mini_app_state(state, bot=None, event_loop=None)

    assert server.stopped
    assert runner.stopped
    assert state.miniapp_server is None
    assert state.ngrok_runner is None


def test_missing_domain_prevents_start_even_if_enabled(monkeypatch):
    monkeypatch.setattr("tether.transport.menu_button.schedule_menu_button_sync", lambda *a: None)
    monkeypatch.setattr("tether.miniapp.server.start", lambda *a: (_ for _ in ()).throw(AssertionError("should not start")))
    state = FakeState(config=FakeConfig(
        settings=FakeSettings(mini_app_enabled=True, mini_app_ngrok_domain=""),
        secrets=FakeSecrets(ngrok_authtoken="tok"),
    ))
    lifecycle.apply_mini_app_state(state, bot=None, event_loop=None)
    assert state.miniapp_server is None


def test_missing_authtoken_prevents_start_even_if_enabled_and_domain_set(monkeypatch):
    monkeypatch.setattr("tether.transport.menu_button.schedule_menu_button_sync", lambda *a: None)
    monkeypatch.setattr("tether.miniapp.server.start", lambda *a: (_ for _ in ()).throw(AssertionError("should not start")))
    state = FakeState(config=FakeConfig(
        settings=FakeSettings(mini_app_enabled=True, mini_app_ngrok_domain="me.ngrok-free.app"),
        secrets=FakeSecrets(ngrok_authtoken=None),
    ))
    lifecycle.apply_mini_app_state(state, bot=None, event_loop=None)
    assert state.miniapp_server is None


def test_calling_twice_while_already_running_does_not_restart(monkeypatch):
    start_calls = []
    monkeypatch.setattr("tether.miniapp.server.start", lambda *a: start_calls.append(1) or FakeServer())
    monkeypatch.setattr("tether.miniapp.lifecycle.NgrokRunner", FakeRunner)
    monkeypatch.setattr("tether.transport.menu_button.schedule_menu_button_sync", lambda *a: None)

    state = fully_configured_state(enabled=True)
    lifecycle.apply_mini_app_state(state, bot=None, event_loop=None)
    lifecycle.apply_mini_app_state(state, bot=None, event_loop=None)

    assert len(start_calls) == 1


def test_menu_button_is_synced_on_every_call():
    calls = []

    def fake_sync(bot, loop, state):
        calls.append(state)

    import tether.transport.menu_button as mb
    original = mb.schedule_menu_button_sync
    mb.schedule_menu_button_sync = fake_sync
    try:
        state = FakeState()
        lifecycle.apply_mini_app_state(state, bot=None, event_loop=None)
    finally:
        mb.schedule_menu_button_sync = original
    assert calls == [state]
