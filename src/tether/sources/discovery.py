"""
Finds the transcript file for whatever Claude Code session the user is
actively working in — not necessarily the same project tether itself lives
in. There is no reliable static mapping from "current project" to a
transcript filename (Claude Code's slug scheme is an internal detail), so
discovery instead picks the most-recently-modified .jsonl across the whole
projects tree: freshness of the file *is* "the session being interacted
with right now". Re-run periodically so switching to a different session
elsewhere is picked up automatically.
"""
from __future__ import annotations

from pathlib import Path


def default_projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def find_active_transcript(root: Path | None = None) -> Path | None:
    root = root or default_projects_root()
    if not root.exists():
        return None
    candidates = [p for p in root.glob("*/*.jsonl") if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
