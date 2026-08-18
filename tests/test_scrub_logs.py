import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from scrub_logs import scrub_file  # noqa: E402


def test_scrub_file_redacts_and_rewrites(tmp_path):
    path = tmp_path / "bot.log"
    path.write_text(
        "2026-01-01 INFO POST https://api.telegram.org/bot123456789:FAKEtokenFAKEtokenFAKEtokenFAKEtoken/getUpdates\n"
        "2026-01-01 INFO normal line, nothing to see here\n",
        encoding="utf-8",
    )
    count = scrub_file(path)
    assert count == 1
    text = path.read_text(encoding="utf-8")
    assert "FAKEtoken" not in text
    assert "bot***REDACTED***" in text
    assert "normal line" in text


def test_scrub_file_missing_returns_zero(tmp_path):
    assert scrub_file(tmp_path / "nope.log") == 0


def test_scrub_file_no_token_present_no_change(tmp_path):
    path = tmp_path / "clean.log"
    original = "2026-01-01 INFO nothing sensitive here\n"
    path.write_text(original, encoding="utf-8")
    count = scrub_file(path)
    assert count == 0
    assert path.read_text(encoding="utf-8") == original
