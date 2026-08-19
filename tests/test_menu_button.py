"""
mini_app_url/sync_menu_button decide whether the chat's persistent menu
button points at the Mini App or Telegram's regular command list -
exercised with a fake bot so no real Bot API call happens. Keyed off
state.miniapp_server (actual running state), not the raw setting - a
misconfigured "enabled" setting must never produce a button pointing at
a dead URL.
"""
import asyncio
from dataclasses import dataclass, field

from telegram import MenuButtonCommands, MenuButtonWebApp

from tether.transport.menu_button import mini_app_url, sync_menu_button


@dataclass
class FakeSettings:
    mini_app_ngrok_domain: str = ""
    language: str = "en"


@dataclass
class FakeSecrets:
    chat_id: int = 123


@dataclass
class FakeConfig:
    settings: FakeSettings = field(default_factory=FakeSettings)
    secrets: FakeSecrets = field(default_factory=FakeSecrets)


@dataclass
class FakeState:
    config: FakeConfig = field(default_factory=FakeConfig)
    miniapp_server: object = None  # None = not running


class FakeBot:
    def __init__(self):
        self.calls = []

    async def set_chat_menu_button(self, chat_id, menu_button):
        self.calls.append((chat_id, menu_button))


def test_url_is_none_when_server_not_running():
    state = FakeState(miniapp_server=None, config=FakeConfig(settings=FakeSettings(mini_app_ngrok_domain="x.ngrok-free.app")))
    assert mini_app_url(state) is None


def test_url_is_none_when_domain_unset_even_if_server_running():
    state = FakeState(miniapp_server=object(), config=FakeConfig(settings=FakeSettings(mini_app_ngrok_domain="")))
    assert mini_app_url(state) is None


def test_url_is_none_when_domain_only_whitespace():
    state = FakeState(miniapp_server=object(), config=FakeConfig(settings=FakeSettings(mini_app_ngrok_domain="   ")))
    assert mini_app_url(state) is None


def test_url_is_built_from_domain_when_server_running():
    state = FakeState(miniapp_server=object(), config=FakeConfig(settings=FakeSettings(mini_app_ngrok_domain="myname.ngrok-free.app")))
    assert mini_app_url(state) == "https://myname.ngrok-free.app/"


def test_sync_sets_webapp_button_when_running():
    bot = FakeBot()
    state = FakeState(miniapp_server=object(), config=FakeConfig(settings=FakeSettings(mini_app_ngrok_domain="myname.ngrok-free.app")))
    asyncio.run(sync_menu_button(bot, 123, state))

    assert len(bot.calls) == 1
    chat_id, button = bot.calls[0]
    assert chat_id == 123
    assert isinstance(button, MenuButtonWebApp)
    assert button.web_app.url == "https://myname.ngrok-free.app/"


def test_sync_restores_commands_button_when_not_running():
    bot = FakeBot()
    state = FakeState(miniapp_server=None)
    asyncio.run(sync_menu_button(bot, 123, state))

    assert len(bot.calls) == 1
    chat_id, button = bot.calls[0]
    assert isinstance(button, MenuButtonCommands)


def test_sync_swallows_bot_api_errors_instead_of_raising():
    class FailingBot:
        async def set_chat_menu_button(self, *a, **k):
            raise RuntimeError("network down")

    # Must not raise - a transient Bot API failure shouldn't crash whatever
    # called this (startup, /start, or a settings POST from the Mini App).
    asyncio.run(sync_menu_button(FailingBot(), 123, FakeState(miniapp_server=None)))
