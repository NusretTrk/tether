"""
Single place that decides whether the Mini App's local server + ngrok
tunnel should actually be running right now, and makes reality match
that decision. Called from three different contexts - startup, the
regular /settings toggle, and the Mini App's own settings toggle - so
this is where "should it be on" lives instead of three call sites
re-deriving the same logic and drifting apart.

Safe to call from any thread: it never touches the bot's asyncio loop
directly, only through menu_button.schedule_menu_button_sync (which
already does the thread-safe bridge). Idempotent - calling it again with
nothing changed is a no-op either way.
"""
from __future__ import annotations

import logging

from tether.miniapp import server as miniapp_server
from tether.miniapp.runner import NgrokRunner
from tether.transport import menu_button

log = logging.getLogger(__name__)


def _should_run(state) -> bool:
    settings = state.config.settings
    secrets = state.config.secrets
    return bool(
        settings.mini_app_enabled
        and settings.mini_app_ngrok_domain.strip()
        and secrets.ngrok_authtoken
    )


def apply_mini_app_state(state, bot, event_loop) -> None:
    should_run = _should_run(state)
    currently_running = state.miniapp_server is not None

    if should_run and not currently_running:
        settings, secrets = state.config.settings, state.config.secrets
        state.miniapp_server = miniapp_server.start(state, bot, event_loop)
        runner = NgrokRunner(
            settings.mini_app_ngrok_path, settings.mini_app_ngrok_domain.strip(),
            settings.mini_app_local_port, secrets.ngrok_authtoken,
        )
        state.ngrok_runner = runner if runner.start() else None
        log.info("mini app turned on")
    elif not should_run and currently_running:
        stop_mini_app(state)
        log.info("mini app turned off")
    elif state.config.settings.mini_app_enabled and not should_run:
        log.warning("mini_app_enabled is on but mini_app_ngrok_domain or NGROK_AUTHTOKEN is missing - not starting")

    menu_button.schedule_menu_button_sync(bot, event_loop, state)


WEBLINK_EXPIRE_MIN = 10  # how long the /miniapp link message stays before self-deleting


def issue_web_link(state) -> str | None:
    """Generates a fresh web-access token and returns the full URL to send
    the owner, or None if there's no domain configured yet (a link would
    just be dead - same precondition as turning the Mini App on at all).
    Replaces whatever token was issued before - only one is ever live."""
    domain = state.config.settings.mini_app_ngrok_domain.strip()
    if not domain:
        return None
    from tether.miniapp import webtoken
    raw = webtoken.issue()
    state.web_token_hash = webtoken.hash_token(raw)
    return f"https://{domain}/#t={raw}"


def revoke_web_link(state) -> None:
    from tether.miniapp import webtoken
    webtoken.clear()
    state.web_token_hash = None


def stop_mini_app(state) -> None:
    """Also called directly from bot.py on shutdown - ngrok.exe is a real
    child process, not a thread, and does NOT die on its own just because
    the parent Python process exits. Left unstopped, it would keep
    tunneling traffic to a local server that no longer exists."""
    if state.ngrok_runner is not None:
        state.ngrok_runner.stop()
        state.ngrok_runner = None
    if state.miniapp_server is not None:
        state.miniapp_server.shutdown()
        state.miniapp_server.server_close()
        state.miniapp_server = None
