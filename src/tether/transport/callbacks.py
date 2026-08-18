"""Single dispatcher for every inline button, routed by callback_data prefix
("category:action[:arg]") rather than one handler per button."""
from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from tether.i18n import make_translator
from tether.transport import menus
from tether.transport.handlers import restricted

log = logging.getLogger(__name__)


@restricted
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    state = context.bot_data["state"]
    _t = make_translator(state.config.settings.language)
    data = query.data or ""
    parts = data.split(":")
    category = parts[0]

    # A callback query can only be answered once. Keypad presses answer with
    # their own toast further down, so only acknowledge here for everything
    # else - answering twice raises.
    if category != "key":
        await query.answer()

    async def edit(text: str, markup=None):
        await query.edit_message_text(text, reply_markup=markup)

    # ---- menu navigation ----
    if category == "menu":
        target = parts[1] if len(parts) > 1 else "root"
        if target == "root":
            await edit(_t("menu_title"), menus.main_menu(_t))
        elif target == "session":
            sessions = await asyncio.to_thread(state.target.list_sessions)
            if not sessions:
                await edit(_t("sessions_none"), menus.main_menu(_t))
            else:
                await edit(_t("menu_session_title"), menus.session_menu(_t, sessions))
        elif target == "screen":
            await edit(_t("menu_screen_title"), menus.screen_menu(
                _t, state.config.settings.claude_window_keyword, state.config.settings.avd_window_keyword
            ))
        elif target == "system":
            await edit(_t("menu_system_title"), menus.system_menu(_t))
        elif target == "settings":
            await edit(_t("menu_settings_title"), menus.settings_menu(_t))
        elif target == "keypad":
            await edit(_t("keypad_title"), menus.keypad_menu(_t, state.config.settings.custom_keys))
        return

    # ---- remote keypad ----
    # Answers whatever prompt the agent has put on screen (numbered choices,
    # y/n confirmations, permission dialogs). Without this a blocked session
    # cannot be unblocked remotely.
    if category == "key":
        key = ":".join(parts[1:])
        ok = await asyncio.to_thread(state.target.send_key, key)
        await query.answer(_t("key_sent", key_name=key) if ok else _t("key_failed"), show_alert=not ok)
        return

    # ---- profile keypad: same mechanism, targets a different window ----
    if category == "pkeymenu":
        name = ":".join(parts[1:])
        profile = state.config.settings.keypad_profiles.get(name)
        if not profile:
            await edit(_t("keypad_profile_unknown", name=name, options=", ".join(state.config.settings.keypad_profiles) or "-"))
            return
        await edit(_t("keypad_profile_title", name=name), menus.profile_keypad_menu(_t, name, profile.get("keys", {})))
        return

    if category == "pkey":
        profile_name, key = parts[1], ":".join(parts[2:])
        profile = state.config.settings.keypad_profiles.get(profile_name)
        window_keyword = profile.get("window_keyword") if profile else None
        ok = await asyncio.to_thread(state.target.send_key, key, window_keyword)
        await query.answer(_t("key_sent", key_name=key) if ok else _t("key_failed"), show_alert=not ok)
        return

    # ---- sessions ----
    if category == "session" and parts[1] == "switch":
        name = ":".join(parts[2:])
        ok = await asyncio.to_thread(state.target.switch_session, name)
        await edit(_t("session_switched", name=name) if ok else _t("session_switch_failed"))
        return

    # ---- screenshots ----
    if category == "screen":
        action = parts[1]
        if action == "claude":
            from tether.transport.handlers import _send_screenshot
            await _send_screenshot(update, context, state.config.settings.claude_window_keyword, "claude", query.message.reply_text)
        elif action == "avd":
            from tether.transport.handlers import _send_screenshot
            await _send_screenshot(update, context, state.config.settings.avd_window_keyword, "avd", query.message.reply_text)
        return

    # ---- model ----
    if category == "model":
        action = parts[1]
        if action == "menu":
            await edit("Model:", menus.model_menu(_t))
        elif action == "set":
            name = parts[2]
            from tether.targets.claude_desktop import MODEL_NAMES
            result = await asyncio.to_thread(state.target.set_model, name)
            if result:
                await edit(_t("model_set", model=result), menus.screen_menu(
                    _t, state.config.settings.claude_window_keyword, state.config.settings.avd_window_keyword
                ))
            else:
                await edit(_t("model_unknown", target=name, options=", ".join(MODEL_NAMES)), menus.model_menu(_t))
        return

    # ---- effort ----
    if category == "effort":
        action = parts[1]
        if action == "menu":
            await edit("Effort:", menus.effort_menu(_t))
        elif action == "set":
            level = parts[2]
            from tether.targets.claude_desktop import EFFORT_LEVELS
            result = await asyncio.to_thread(state.target.set_effort, level)
            if result:
                await edit(_t("effort_set", level=result), menus.screen_menu(
                    _t, state.config.settings.claude_window_keyword, state.config.settings.avd_window_keyword
                ))
            else:
                await edit(_t("effort_unknown", target=level, options=", ".join(EFFORT_LEVELS)), menus.effort_menu(_t))
        return

    # ---- system / status ----
    if category == "system" and parts[1] == "status":
        from tether.monitors.temps import get_cpu_temp, get_gpu_temp
        status = await asyncio.to_thread(state.target.read_status)
        cpu = get_cpu_temp()
        gpu, fan = get_gpu_temp()
        cpu_str = f"{cpu}°C" if cpu is not None else _t("temp_unavailable")
        gpu_str = f"{gpu}°C" if gpu is not None else _t("temp_unavailable")
        fan_str = fan or _t("temp_unavailable")
        temp_report = _t("temp_report", cpu=cpu_str, gpu=gpu_str, fan=fan_str)
        await edit(_t("model_status", model=status.model or "?", effort=status.effort or "?", usage=temp_report), menus.system_menu(_t))
        return

    # ---- kill ----
    if category == "kill":
        action = parts[1]
        if action == "menu":
            await edit(_t("kill_menu_title"), menus.kill_menu(_t))
            return
        import subprocess
        if action == "terminal":
            from tether.platform import shell
            shell._shell_cwd = __import__("os").path.expanduser("~")
            await edit(_t("kill_terminal_done"), menus.kill_menu(_t))
        elif action == "emulator":
            for proc_name in ("qemu-system-x86_64.exe", "emulator.exe"):
                subprocess.run(["taskkill", "/F", "/T", "/IM", proc_name], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            await edit(_t("kill_emulator_done"), menus.kill_menu(_t))
        elif action == "claude":
            # Path-filtered, not `taskkill /IM Claude.exe`. The Claude Code
            # CLI shares the exe name, so a name-based kill takes that out
            # too - frequently the very agent issuing this command.
            signalled, all_gone = await asyncio.to_thread(state.target.stop_app)
            log.info("kill claude: signalled %d processes, all exited: %s", signalled, all_gone)
            await edit(_t("kill_claude_done"), menus.kill_menu(_t))
        return

    # ---- language ----
    if category == "lang":
        action = parts[1]
        if action == "menu":
            await edit(_t("language_prompt"), menus.language_menu(_t))
        elif action == "set":
            code = parts[2]
            state.config.settings.language = code
            state.config.settings.save()
            new_t = make_translator(code)
            await edit(new_t("language_set", language=menus.LANGUAGE_LABELS.get(code, code)), menus.settings_menu(new_t))
        return

    # ---- output mode ----
    if category == "mode":
        action = parts[1]
        if action == "menu":
            await edit(_t("mode_prompt"), menus.mode_menu(_t))
        elif action == "set":
            m = parts[2]
            state.config.settings.output_mode = m
            state.config.settings.save()
            await edit(_t("mode_set", mode=_t(f"mode_{m}")), menus.settings_menu(_t))
        return

    # ---- confirm toggle ----
    if category == "confirm":
        action = parts[1]
        if action == "menu":
            current = "on" if state.config.settings.confirm_before_send else "off"
            await edit(_t("confirm_prompt", state=_t("confirm_" + current)), menus.confirm_menu(_t))
        elif action == "set":
            on = parts[2] == "on"
            state.config.settings.confirm_before_send = on
            state.config.settings.save()
            await edit(_t("confirm_set", state=_t("confirm_on" if on else "confirm_off")), menus.settings_menu(_t))
        return

    # ---- app lifecycle ----
    if category == "app":
        action = parts[1]
        if action == "cancel":
            await edit(_t("staged_cancelled"))
            return
        if action == "start":
            ok = await asyncio.to_thread(state.target.launch_app)
            if not ok:
                await edit(_t("app_launch_failed"))
                return
            appeared = await asyncio.to_thread(state.target.wait_for_window, 60.0)
            await edit(_t("app_started") if appeared else _t("app_started_no_window"))
            return
        if action == "restart":
            await edit(_t("app_restarting"))
            ok, reason = await asyncio.to_thread(state.target.restart_app)
            if ok:
                # Clear the health baseline so the watcher doesn't report a
                # transition it didn't observe.
                state.app_was_running = True
                state.app_down_notified = False
                await edit(_t("app_restarted"))
            else:
                await edit(_t("app_restart_failed", reason=reason))
            return
        return

    # ---- staged send (confirm-before-send flow) ----
    if category == "staged":
        action = parts[1]
        if action == "send":
            if state.staged_text is None and not state.staged_photo:
                await edit(_t("staged_cancelled"))
                return
            pending_text = state.staged_text
            was_photo = state.staged_photo
            ok = await asyncio.to_thread(state.target.press_enter)
            state.staged_text = None
            state.staged_photo = False
            if not ok:
                await edit(_t("focus_failed"))
                return
            await edit("…")
            import time
            state.pending_send_text = pending_text
            state.pending_send_kind = "image" if was_photo else "text"
            state.pending_send_message_id = query.message.message_id
            state.pending_send_since = time.monotonic()
        elif action == "edit":
            state.staged_text = None
            state.staged_photo = False
            await asyncio.to_thread(state.target.clear_input)
            await edit(_t("staged_edit_prompt"))
        elif action == "cancel":
            state.staged_text = None
            state.staged_photo = False
            await asyncio.to_thread(state.target.clear_input)
            await edit(_t("staged_cancelled"))
        return

    log.warning("unhandled callback_data: %r", data)
