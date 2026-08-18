"""
Two-tier settings: secrets in .env (never committed), behaviour in config.yaml
(committed as config.example.yaml). Invalid values in config.yaml fall back to
the documented default with a logged warning rather than crashing — this file
is meant to be hand-edited and occasionally gets a typo'd value.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, fields, asdict
from pathlib import Path

import yaml
from dotenv import load_dotenv

log = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = SCRIPT_DIR / ".env"
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
CONFIG_EXAMPLE_PATH = SCRIPT_DIR / "config.example.yaml"

SUPPORTED_LANGUAGES = ("en", "tr", "de", "es")
OUTPUT_MODES = ("live", "summary", "quiet", "verbose")


class ConfigError(RuntimeError):
    pass


@dataclass
class Secrets:
    bot_token: str
    chat_id: int
    claude_projects_dir: str | None = None
    elevenlabs_api_key: str | None = None

    @staticmethod
    def load() -> "Secrets":
        if ENV_PATH.exists():
            load_dotenv(ENV_PATH)
        token = os.environ.get("BOT_TOKEN", "").strip()
        chat_id_raw = os.environ.get("CHAT_ID", "").strip()
        missing = []
        if not token:
            missing.append("BOT_TOKEN")
        if not chat_id_raw:
            missing.append("CHAT_ID")
        if missing:
            raise ConfigError(
                f"Missing required setting(s) in .env: {', '.join(missing)}. "
                f"Copy .env.example to .env and fill them in — see docs/SETUP.md. "
                f"(expected at {ENV_PATH})"
            )
        try:
            chat_id = int(chat_id_raw)
        except ValueError:
            raise ConfigError(f"CHAT_ID in .env must be a number, got: {chat_id_raw!r}")
        return Secrets(
            bot_token=token,
            chat_id=chat_id,
            claude_projects_dir=os.environ.get("CLAUDE_PROJECTS_DIR") or None,
            elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY") or None,
        )


@dataclass
class Settings:
    """Behaviour settings — hand-editable, changeable at runtime via Telegram."""
    language: str = "en"
    output_mode: str = "summary"
    confirm_before_send: bool = True

    claude_window_keyword: str = "Claude"
    avd_window_keyword: str = "Emulator"

    temp_check_interval_sec: int = 300
    temp_report_every_n_checks: int = 3
    temp_emergency_c: int = 90

    usage_limit_check_interval_sec: int = 300
    usage_limit_confirm_streak: int = 3

    stream_edit_throttle_sec: float = 2.5
    transcript_poll_interval_sec: float = 1.0
    uia_poll_interval_sec: float = 3.0

    dialog_watch_enabled: bool = True
    stall_watch_enabled: bool = True
    activity_watch_enabled: bool = True

    def validate(self) -> list[str]:
        """Returns a list of problems found (empty = all good). Does not raise —
        callers decide whether to fall back per-field or reject the whole file."""
        problems = []
        if self.language not in SUPPORTED_LANGUAGES:
            problems.append(f"language={self.language!r} not in {SUPPORTED_LANGUAGES}")
        if self.output_mode not in OUTPUT_MODES:
            problems.append(f"output_mode={self.output_mode!r} not in {OUTPUT_MODES}")
        if self.temp_emergency_c <= 0 or self.temp_emergency_c > 150:
            problems.append(f"temp_emergency_c={self.temp_emergency_c!r} out of sane range")
        if self.stream_edit_throttle_sec < 0.5:
            problems.append(f"stream_edit_throttle_sec={self.stream_edit_throttle_sec!r} too low (Telegram rate limits)")
        if self.transcript_poll_interval_sec <= 0:
            problems.append(f"transcript_poll_interval_sec={self.transcript_poll_interval_sec!r} must be positive")
        return problems

    @staticmethod
    def load() -> "Settings":
        path = CONFIG_PATH if CONFIG_PATH.exists() else CONFIG_EXAMPLE_PATH
        if not path.exists():
            log.warning("No config.yaml or config.example.yaml found, using built-in defaults")
            return Settings()
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            log.warning("config.yaml failed to parse (%s), using built-in defaults", e)
            return Settings()

        known = {f.name for f in fields(Settings)}
        unknown = set(raw) - known
        if unknown:
            log.warning("config.yaml has unknown key(s), ignored: %s", sorted(unknown))
        clean = {k: v for k, v in raw.items() if k in known}

        settings = Settings(**{**asdict(Settings()), **clean})
        problems = settings.validate()
        if problems:
            log.warning("config.yaml has invalid value(s), falling back to defaults for those: %s", problems)
            defaults = Settings()
            bad_fields = set()
            for p in problems:
                bad_fields.add(p.split("=")[0])
            for f in bad_fields:
                setattr(settings, f, getattr(defaults, f))
        return settings

    def save(self) -> None:
        CONFIG_PATH.write_text(
            yaml.safe_dump(asdict(self), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


@dataclass
class Config:
    secrets: Secrets
    settings: Settings

    @staticmethod
    def load() -> "Config":
        return Config(secrets=Secrets.load(), settings=Settings.load())
