"""
Inline keyboard builders. Callback data uses a consistent "category:action"
prefix scheme so the single dispatcher in bot.py can route by splitting on
the first colon rather than needing one handler per button.
"""
from __future__ import annotations

from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from tether.config import SUPPORTED_LANGUAGES, OUTPUT_MODES
from tether.targets.claude_desktop import EFFORT_LEVELS, MODEL_NAMES

LANGUAGE_LABELS = {"en": "English", "tr": "Türkçe", "de": "Deutsch", "es": "Español"}


def main_reply_keyboard(_t) -> ReplyKeyboardMarkup:
    """The physical keyboard row, always visible without opening any menu.
    Mirrors the original bot's layout (direct screenshot buttons, keypad
    shortcuts as physical buttons) rather than requiring /keys or /screen
    every time — those commands still work too, this is just the fast path."""
    return ReplyKeyboardMarkup(
        [
            [_t("btn_screen_claude"), _t("btn_keypad")],
            ["1", "2", "3"],
            [_t("key_yes"), _t("key_no"), _t("key_enter")],
            [_t("btn_status"), _t("btn_sessions")],
            [_t("btn_stop"), _t("btn_menu")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def main_menu(_t) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("menu_session"), callback_data="menu:session")],
        [InlineKeyboardButton(_t("menu_screen"), callback_data="menu:screen")],
        [InlineKeyboardButton(_t("btn_keypad"), callback_data="menu:keypad")],
        [InlineKeyboardButton(_t("menu_system"), callback_data="menu:system")],
        [InlineKeyboardButton(_t("menu_settings"), callback_data="menu:settings")],
    ])


def back_button(_t, to: str = "menu:root") -> InlineKeyboardButton:
    return InlineKeyboardButton(_t("btn_back"), callback_data=to)


def session_menu(_t, sessions: list) -> InlineKeyboardMarkup:
    rows = []
    for s in sessions:
        emoji = "🟢" if s.running else "⚪"
        rows.append([InlineKeyboardButton(f"{emoji} {s.name}", callback_data=f"session:switch:{s.name}")])
    rows.append([back_button(_t)])
    return InlineKeyboardMarkup(rows)


def screen_menu(_t, claude_keyword: str = "Claude", avd_keyword: str = "Emulator") -> InlineKeyboardMarkup:
    """Button labels show the actual configured window keyword, not a fixed
    'AVD' — that name never changes even after /window avd renames the
    target, which made the button misleading once you'd actually used it."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(claude_keyword, callback_data="screen:claude")],
        [InlineKeyboardButton(avd_keyword, callback_data="screen:avd")],
        [InlineKeyboardButton("Model", callback_data="model:menu"), InlineKeyboardButton("Effort", callback_data="effort:menu")],
        [back_button(_t)],
    ])


def model_menu(_t) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(n, callback_data=f"model:set:{n.lower()}")] for n in MODEL_NAMES]
    rows.append([back_button(_t, "menu:screen")])
    return InlineKeyboardMarkup(rows)


def effort_menu(_t) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(lvl, callback_data=f"effort:set:{lvl.lower()}")] for lvl in EFFORT_LEVELS]
    rows.append([back_button(_t, "menu:screen")])
    return InlineKeyboardMarkup(rows)


def system_menu(_t) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("btn_status"), callback_data="system:status")],
        [InlineKeyboardButton(_t("kill_menu_title"), callback_data="kill:menu")],
        [back_button(_t)],
    ])


def kill_menu(_t) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("kill_terminal"), callback_data="kill:terminal")],
        [InlineKeyboardButton(_t("kill_emulator"), callback_data="kill:emulator")],
        [InlineKeyboardButton(_t("kill_claude"), callback_data="kill:claude")],
        [back_button(_t, "menu:system")],
    ])


def settings_menu(_t) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 " + _t("language_prompt"), callback_data="lang:menu")],
        [InlineKeyboardButton("📡 " + _t("mode_prompt"), callback_data="mode:menu")],
        [InlineKeyboardButton("✅ " + _t("confirm_prompt").split(" ")[0], callback_data="confirm:menu")],
        [InlineKeyboardButton("🚀 " + _t("miniapp_prompt").split(":")[0], callback_data="miniapp:menu")],
        [back_button(_t)],
    ])


def language_menu(_t) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"lang:set:{code}")] for code, label in LANGUAGE_LABELS.items()]
    rows.append([back_button(_t, "menu:settings")])
    return InlineKeyboardMarkup(rows)


def mode_menu(_t) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(_t(f"mode_{m}"), callback_data=f"mode:set:{m}")] for m in OUTPUT_MODES]
    rows.append([back_button(_t, "menu:settings")])
    return InlineKeyboardMarkup(rows)


def confirm_menu(_t) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("confirm_on"), callback_data="confirm:set:on"),
         InlineKeyboardButton(_t("confirm_off"), callback_data="confirm:set:off")],
        [back_button(_t, "menu:settings")],
    ])


def miniapp_menu(_t) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("confirm_on"), callback_data="miniapp:set:on"),
         InlineKeyboardButton(_t("confirm_off"), callback_data="miniapp:set:off")],
        [back_button(_t, "menu:settings")],
    ])


def keypad_menu(_t, custom_keys: dict[str, str] | None = None) -> InlineKeyboardMarkup:
    """Remote keyboard for answering prompts the agent puts on screen.

    Rows cover the full ALLOWED_KEYS set in claude_desktop.py — a key that
    can be sent but has no button is a dead feature, which is exactly what
    4/5/a/space/backspace/left/right were until this covered them too.
    `custom_keys` (from Settings.custom_keys, label -> key) appends
    whatever the user has defined in config.yaml as extra rows."""
    rows = [
        [InlineKeyboardButton("1", callback_data="key:1"),
         InlineKeyboardButton("2", callback_data="key:2"),
         InlineKeyboardButton("3", callback_data="key:3")],
        [InlineKeyboardButton("4", callback_data="key:4"),
         InlineKeyboardButton("5", callback_data="key:5"),
         InlineKeyboardButton(_t("key_all"), callback_data="key:a")],
        [InlineKeyboardButton(_t("key_yes"), callback_data="key:y"),
         InlineKeyboardButton(_t("key_no"), callback_data="key:n"),
         InlineKeyboardButton(_t("key_enter"), callback_data="key:enter")],
        [InlineKeyboardButton(_t("key_escape"), callback_data="key:escape"),
         InlineKeyboardButton(_t("key_tab"), callback_data="key:tab"),
         InlineKeyboardButton(_t("key_mode"), callback_data="key:shift+tab")],
        [InlineKeyboardButton("↑", callback_data="key:up"),
         InlineKeyboardButton("↓", callback_data="key:down"),
         InlineKeyboardButton("←", callback_data="key:left"),
         InlineKeyboardButton("→", callback_data="key:right")],
        [InlineKeyboardButton(_t("key_space"), callback_data="key:space"),
         InlineKeyboardButton(_t("key_backspace"), callback_data="key:backspace")],
        [InlineKeyboardButton(_t("btn_screen_claude"), callback_data="screen:claude"),
         InlineKeyboardButton(_t("btn_screen_avd"), callback_data="screen:avd")],
    ]
    for label, key in (custom_keys or {}).items():
        rows.append([InlineKeyboardButton(label, callback_data=f"key:{key}")])
    rows.append([back_button(_t)])
    return InlineKeyboardMarkup(rows)


def prompt_reply_keyboard(_t) -> InlineKeyboardMarkup:
    """Compact version attached to a detected prompt notification, so the
    answer is one tap from the alert instead of navigating a menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data="key:1"),
         InlineKeyboardButton("2", callback_data="key:2"),
         InlineKeyboardButton("3", callback_data="key:3")],
        [InlineKeyboardButton(_t("key_yes"), callback_data="key:y"),
         InlineKeyboardButton(_t("key_no"), callback_data="key:n"),
         InlineKeyboardButton(_t("key_escape"), callback_data="key:escape")],
        [InlineKeyboardButton(_t("btn_keypad"), callback_data="menu:keypad")],
    ])


def profile_keypad_menu(_t, profile_name: str, keys: dict[str, str]) -> InlineKeyboardMarkup:
    """A user-defined keypad for a non-default target (Cursor, a terminal,
    Antigravity) — labels and keys come straight from config.yaml, two
    buttons per row. Every key is still re-validated against
    ClaudeDesktopTarget.is_valid_key_spec when pressed; this only decides
    what gets offered as a shortcut."""
    rows = []
    items = list(keys.items())
    for i in range(0, len(items), 2):
        row = [InlineKeyboardButton(label, callback_data=f"pkey:{profile_name}:{key}")
               for label, key in items[i:i + 2]]
        rows.append(row)
    rows.append([back_button(_t)])
    return InlineKeyboardMarkup(rows)


def profile_list_menu(_t, profile_names: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("Claude (default)", callback_data="menu:keypad")]]
    rows += [[InlineKeyboardButton(name, callback_data=f"pkeymenu:{name}")] for name in profile_names]
    rows.append([back_button(_t)])
    return InlineKeyboardMarkup(rows)


def app_down_keyboard(_t) -> InlineKeyboardMarkup:
    """Attached to the "Claude isn't running" alert so it can be started
    from the notification itself."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("app_start"), callback_data="app:start")],
    ])


def restart_confirm_keyboard(_t) -> InlineKeyboardMarkup:
    """Restarting kills whatever session is live, including the one issuing
    the command if an agent is driving it - always confirmed, never
    automatic."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("app_restart_confirm_yes"), callback_data="app:restart"),
         InlineKeyboardButton(_t("staged_cancel"), callback_data="app:cancel")],
    ])


def recent_files_menu(root: Path, files: list[Path]) -> InlineKeyboardMarkup:
    """One button per file, labelled with its path relative to the project
    root. Sends by index (file:send:<i>), not by path - a real path can
    easily exceed Telegram's 64-byte callback_data limit."""
    rows = []
    for i, f in enumerate(files):
        try:
            label = str(f.relative_to(root))
        except ValueError:
            label = f.name
        rows.append([InlineKeyboardButton(label[:60], callback_data=f"file:send:{i}")])
    return InlineKeyboardMarkup(rows)


def cmd_confirm_keyboard(_t) -> InlineKeyboardMarkup:
    """/cmd runs arbitrary shell commands with the user's own privileges -
    always confirmed, never automatic, same as restart/shutdown."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("cmd_confirm_yes"), callback_data="cmd:confirm"),
         InlineKeyboardButton(_t("staged_cancel"), callback_data="cmd:cancel")],
    ])


def shutdown_confirm_keyboard(_t) -> InlineKeyboardMarkup:
    """Shutting down ends the whole machine, not just Claude's session -
    always confirmed, never automatic."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("shutdown_confirm_yes"), callback_data="shutdown:confirm"),
         InlineKeyboardButton(_t("staged_cancel"), callback_data="shutdown:cancel")],
    ])


def deferred_keyboard(_t) -> InlineKeyboardMarkup:
    """Shown when a message is held back because someone is using the
    machine. Nothing has been typed yet at this point."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("deferred_send_now"), callback_data="defer:send"),
         InlineKeyboardButton(_t("staged_cancel"), callback_data="defer:cancel")],
    ])


def staged_message_keyboard(_t) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(_t("staged_send"), callback_data="staged:send"),
        InlineKeyboardButton(_t("staged_edit"), callback_data="staged:edit"),
        InlineKeyboardButton(_t("staged_cancel"), callback_data="staged:cancel"),
    ]])
