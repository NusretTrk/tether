"""
Dedicated audit trail for every /cmd actually executed (never staged-and-
cancelled ones). Separate from tether.log on purpose: "what commands ran,
when" should be a quick, obvious thing to check without wading through
job-scheduler noise, and shouldn't compete with the main log's rotation
for space - the main log fills with a poll-interval's worth of routine
lines every few seconds, this one only grows when something was actually
run.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_LOG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "cmd_audit.log"
_logger: logging.Logger | None = None


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    logger = logging.getLogger("tether.cmd_audit")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # never duplicate into the main log/console
    handler = logging.handlers.RotatingFileHandler(
        _LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    _logger = logger
    return _logger


def log_command(command: str) -> None:
    _get_logger().info(command)
