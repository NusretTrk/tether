"""
Locating and safely resolving files inside the active project, for /file
and /files - fetching a doc (often a freshly-generated .md) the agent wrote
mid-session, without needing to be at the machine to read it.

resolve_safe_path is the one function that actually matters for security:
this bot already lets its owner run arbitrary shell commands via /cmd, so
this isn't adding a new capability so much as a more convenient one - but
it must still refuse anything that resolves outside the project root
(traversal, absolute paths elsewhere, symlinks pointing out) rather than
trusting the caller to only ask for things inside it.
"""
from __future__ import annotations

import json
from pathlib import Path

_SKIP_DIR_NAMES = {".git", "node_modules", "venv", ".venv", "__pycache__", ".claude", "dist", "build", ".idea", ".vscode"}


def read_project_cwd(transcript_path: Path, max_lines: int = 5) -> Path | None:
    """The first few lines of a Claude Code transcript carry a `cwd` field
    with the real project directory. This beats trying to reverse the
    filename-mangled slug the transcript itself is stored under (that
    mangling is lossy - spaces, colons, and dashes all collapse to the same
    character, so it can't be reliably reversed)."""
    try:
        with transcript_path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cwd = data.get("cwd")
                if cwd:
                    return Path(cwd)
    except OSError:
        return None
    return None


def resolve_safe_path(root: Path, requested: str) -> Path | None:
    """Resolves `requested` against `root`, returning the resolved absolute
    path only if it's a real file that stays inside root. Returns None for
    every failure mode - traversal, an absolute path elsewhere, a symlink
    that escapes root, a directory, or a file that doesn't exist - rather
    than distinguishing them, so a probe can't be used to learn what does
    or doesn't exist outside the allowed tree."""
    if not requested or not requested.strip():
        return None
    requested_path = Path(requested)
    candidate = requested_path if requested_path.is_absolute() else root / requested_path
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        return None
    if not resolved.is_file():
        return None
    return resolved


def list_recent_files(root: Path, extensions: tuple[str, ...], limit: int) -> list[Path]:
    """Most-recently-modified files under root matching one of extensions
    (case-insensitive), skipping common noise directories (.git,
    node_modules, build output, ...) that would otherwise dominate a glob
    over a real project."""
    if not root.exists():
        return []
    extensions_lower = {e.lower() for e in extensions}
    candidates: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in extensions_lower:
            continue
        try:
            parts = p.relative_to(root).parts[:-1]
        except ValueError:
            continue
        if any(part in _SKIP_DIR_NAMES for part in parts):
            continue
        candidates.append(p)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[:limit]
