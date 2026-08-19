"""
Keeps the chat's persistent menu button in sync with mini_app_enabled -
a WebApp button opening the Mini App when it's on, Telegram's regular
command menu when it's off. Centralized here so cmd_start, startup, and
the /settings (and Mini App's own settings) toggle all go through the
same logic instead of drifting apart across separate call sites.
"""
from __future__ import annotations

import asyncio
import logging

from telegram import MenuButtonCommands, MenuButtonWebApp, WebAppInfo

from tether.i18n import make_translator

log = logging.getLogger(__name__)


def mini_app_url(state) -> str | None:
    """The button only ever points somewhere real. Deliberately keyed off
    state.miniapp_server (is the tunnel actually up right now) rather than
    the raw mini_app_enabled setting - if the setting is on but the ngrok
    domain or authtoken is missing/misconfigured, the server never starts,
    and showing a WebApp button anyway would just open a dead URL. See
    miniapp/lifecycle.py for what actually starts/stops the server."""
    if state.miniapp_server is None:
        return None
    domain = state.config.settings.mini_app_ngrok_domain.strip()
    if not domain:
        return None
    return f"https://{domain}/"


async def sync_menu_button(bot, chat_id: int, state) -> None:
    url = mini_app_url(state)
    try:
        if url:
            _t = make_translator(state.config.settings.language)
            await bot.set_chat_menu_button(
                chat_id, MenuButtonWebApp(text=_t("mini_app_button"), web_app=WebAppInfo(url=url)),
            )
        else:
            await bot.set_chat_menu_button(chat_id, MenuButtonCommands())
    except Exception:
        log.warning("failed to sync chat menu button", exc_info=True)


def schedule_menu_button_sync(bot, event_loop, state) -> None:
    """Safe to call from any thread - notably the Mini App's own HTTP
    server thread, right after a settings change made through the Mini
    App itself. Schedules the actual async Bot API call onto the bot's
    event loop instead of trying to run it directly on a foreign thread,
    which python-telegram-bot's Bot object doesn't support."""
    chat_id = state.config.secrets.chat_id
    asyncio.run_coroutine_threadsafe(sync_menu_button(bot, chat_id, state), event_loop)
