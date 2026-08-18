"""Application wiring: builds the Telegram Application, registers every
handler and background job, and runs with startup-retry resilience."""
from __future__ import annotations

import logging
import time

from telegram import BotCommand
from telegram.ext import Application, ApplicationBuilder, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from tether.config import Config
from tether.platform.capabilities import CAPABILITIES, platform_name
from tether.logsetup import setup_logging
from tether.transport import handlers
from tether.transport.callbacks import handle_callback
from tether.transport.state import AppState
from tether.transport.text import handle_photo, handle_text
from tether.transport.jobs import (
    activity_job, dialog_job, stall_job, temp_monitor_job, transcript_job, usage_limit_job,
)

log = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Show the keyboard"),
    BotCommand("menu", "Full command menu"),
    BotCommand("sessions", "List and switch sessions"),
    BotCommand("screen", "Screenshot a window"),
    BotCommand("model", "Switch model"),
    BotCommand("effort", "Switch effort"),
    BotCommand("cmd", "Run a PowerShell command"),
    BotCommand("clear", "Clear the input box"),
    BotCommand("stop", "Stop the current generation"),
    BotCommand("kill", "Close terminal/emulator/Claude"),
    BotCommand("keys", "Send a key to the app (answer prompts)"),
    BotCommand("window", "Change which window Claude/AVD points at"),
    BotCommand("status", "Current model, effort, temps"),
    BotCommand("language", "Change language"),
    BotCommand("mode", "Change output verbosity"),
    BotCommand("confirm", "Toggle send confirmation"),
    BotCommand("settings", "View/edit settings"),
    BotCommand("help", "Show help"),
]

STARTUP_RETRY_INTERVAL_SEC = 30


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(BOT_COMMANDS)


def _build_app(config: Config) -> Application:
    app = ApplicationBuilder().token(config.secrets.bot_token).post_init(_post_init).build()
    app.bot_data["state"] = AppState.build(config)

    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("menu", handlers.cmd_menu))
    app.add_handler(CommandHandler("sessions", handlers.cmd_sessions))
    app.add_handler(CommandHandler(["screen", "screenshot"], handlers.cmd_screen))
    app.add_handler(CommandHandler("model", handlers.cmd_model))
    app.add_handler(CommandHandler("effort", handlers.cmd_effort))
    app.add_handler(CommandHandler("cmd", handlers.cmd_cmd))
    app.add_handler(CommandHandler("clear", handlers.cmd_clear))
    app.add_handler(CommandHandler("stop", handlers.cmd_stop))
    app.add_handler(CommandHandler("kill", handlers.cmd_kill))
    app.add_handler(CommandHandler("keys", handlers.cmd_keys))
    app.add_handler(CommandHandler("window", handlers.cmd_window))
    app.add_handler(CommandHandler("status", handlers.cmd_status))
    app.add_handler(CommandHandler("language", handlers.cmd_language))
    app.add_handler(CommandHandler("mode", handlers.cmd_mode))
    app.add_handler(CommandHandler("confirm", handlers.cmd_confirm))
    app.add_handler(CommandHandler("settings", handlers.cmd_settings))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_error_handler(handlers.error_handler)

    settings = config.settings
    app.job_queue.run_repeating(transcript_job, interval=settings.transcript_poll_interval_sec, first=5)
    app.job_queue.run_repeating(usage_limit_job, interval=settings.usage_limit_check_interval_sec, first=20)
    app.job_queue.run_repeating(temp_monitor_job, interval=settings.temp_check_interval_sec, first=10)
    # Session and dialog watching read the OS accessibility tree, which only
    # the Windows implementation provides. Scheduling them elsewhere would
    # just log a failure every few seconds.
    if CAPABILITIES.accessibility:
        app.job_queue.run_repeating(activity_job, interval=settings.uia_poll_interval_sec, first=15)
        app.job_queue.run_repeating(dialog_job, interval=settings.uia_poll_interval_sec, first=15)
    else:
        log.info("accessibility features unavailable on %s - session and dialog watchers disabled", platform_name())
    app.job_queue.run_repeating(stall_job, interval=15, first=30)

    return app


def main() -> None:
    from tether.config import SCRIPT_DIR
    setup_logging(SCRIPT_DIR / "tether.log")
    config = Config.load()

    # At-login auto-start can fire before Wi-Fi/DNS is up, which crashes the
    # initial getMe() call — retry startup indefinitely instead of dying on
    # one bad connection attempt at boot.
    while True:
        try:
            _build_app(config).run_polling()
            break  # run_polling only returns on a clean shutdown
        except Exception as e:
            log.error("Startup/run failed, retrying in %ss: %s", STARTUP_RETRY_INTERVAL_SEC, e)
            time.sleep(STARTUP_RETRY_INTERVAL_SEC)


if __name__ == "__main__":
    main()
