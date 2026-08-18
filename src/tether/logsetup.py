"""
Logging setup with mandatory token redaction. The filter runs on every record
before it reaches any handler — a rotating file handler is the main target,
but this must catch console output too, since Telegram bot tokens end up in
outbound HTTP URLs (python-telegram-bot logs the request URL at INFO level).
"""
from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path

_TOKEN_RE = re.compile(r"bot\d{6,12}:[A-Za-z0-9_-]{30,50}")


class RedactTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _TOKEN_RE.sub("bot***REDACTED***", record.msg)
        if record.args:
            record.args = tuple(
                _TOKEN_RE.sub("bot***REDACTED***", a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def setup_logging(log_path: Path, level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    redact = RedactTokenFilter()

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    file_handler.addFilter(redact)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    console_handler.addFilter(redact)

    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # httpx/telegram are chatty at INFO with every poll — keep WARNING+ only
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
