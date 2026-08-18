"""
Inline keyboard builders. Callback data uses a consistent "category:action"
prefix scheme so the single dispatcher in bot.py can route by splitting on
the first colon rather than needing one handler per button.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from tether.config import SUPPORTED_LANGUAGES, OUTPUT_MODES
from tether.targets.claude_desktop import EFFORT_LEVELS, MODEL_NAMES

LANGUAGE_LABELS = {"en": "English", "tr": "Türkçe", "de": "Deutsch", "es": "Español"}


def main_reply_keyboard(_t) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [_t("btn_status"), _t("btn_screen")],
            [_t("btn_stop"), _t("btn_sessions")],
            [_t("btn_menu")],
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


def screen_menu(_t) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Claude", callback_data="screen:claude")],
        [InlineKeyboardButton("AVD", callback_data="screen:avd")],
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


def keypad_menu(_t) -> InlineKeyboardMarkup:
    """Remote keyboard for answering prompts the agent puts on screen."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data="key:1"),
         InlineKeyboardButton("2", callback_data="key:2"),
         InlineKeyboardButton("3", callback_data="key:3")],
        [InlineKeyboardButton(_t("key_yes"), callback_data="key:y"),
         InlineKeyboardButton(_t("key_no"), callback_data="key:n"),
         InlineKeyboardButton(_t("key_enter"), callback_data="key:enter")],
        [InlineKeyboardButton(_t("key_escape"), callback_data="key:escape"),
         InlineKeyboardButton(_t("key_tab"), callback_data="key:tab"),
         InlineKeyboardButton(_t("key_mode"), callback_data="key:shift+tab")],
        [InlineKeyboardButton("↑", callback_data="key:up"),
         InlineKeyboardButton("↓", callback_data="key:down")],
        [back_button(_t)],
    ])


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


def staged_message_keyboard(_t) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(_t("staged_send"), callback_data="staged:send"),
        InlineKeyboardButton(_t("staged_edit"), callback_data="staged:edit"),
        InlineKeyboardButton(_t("staged_cancel"), callback_data="staged:cancel"),
    ]])
