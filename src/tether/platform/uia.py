"""
Windows UI Automation wrapper. Chromium/Electron builds its accessibility
tree lazily on first assistive-tech query — verified live: an immediate
first walk of Claude Desktop returned 23 nodes, an immediate second walk
returned 249. warm_up() queries, waits, and re-queries until the node count
stabilizes (or a retry budget runs out), so callers can trust the tree.

All UIA calls are COM-based and blocking. Callers MUST run this module's
functions in a worker thread, never directly on the asyncio event loop.
"""
from __future__ import annotations

import concurrent.futures
import logging
import threading
import time

import pythoncom
import uiautomation as auto

log = logging.getLogger(__name__)

# uiautomation's _AutomationClient is a process-wide singleton bound to
# whichever thread first creates it (a COM single-threaded-apartment
# object). asyncio.to_thread() dispatches onto a general pool with multiple
# threads, and calling the cached client from a different thread than the
# one that created it fails with a misleading "CoInitialize has not been
# called" — verified live: two independent jobs each landing on their own
# to_thread() pool thread crashed the second one every time. Routing every
# UIA call through one persistent dedicated thread sidesteps the whole
# class of cross-apartment marshaling problems, since it's always the same
# thread using it.
_UIA_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="uia-worker")
_com_initialized = threading.local()


def run_on_uia_thread(func, *args, **kwargs):
    """Runs func on the single dedicated UIA worker thread and blocks (via
    .result()) until it completes. Safe to call from any thread, including
    from within an outer asyncio.to_thread() dispatch — this just hands the
    actual COM work to the one consistent thread and waits."""
    return _UIA_EXECUTOR.submit(func, *args, **kwargs).result()


def _ensure_com_initialized() -> None:
    """CoInitialize still needs to be called at least once on the
    dedicated UIA thread before first use."""
    if getattr(_com_initialized, "done", False):
        return
    try:
        pythoncom.CoInitialize()
    except OSError:
        pass  # already initialized on this thread — fine
    _com_initialized.done = True

# Standard app-chrome buttons that appear on every screen — not session rows,
# not dialogs. Used to filter noise out of session lists and dialog detection.
_CHROME_BUTTONS = {
    "minimize", "maximize", "restore", "close", "menu", "search",
    "back", "forward", "home", "code", "new", "artifacts", "customize",
    "collapse sidebar", "expand sidebar", "filter", "send feedback",
}

_DIALOG_TRIGGER_KEYWORDS = (
    "sign in", "sign back in", "security", "session expired", "reconnect",
    "update available", "relaunch", "restart required", "connection lost",
    "failed to", "error occurred", "try again", "something went wrong",
)


def find_root_window(keyword: str):
    _ensure_com_initialized()
    for w in auto.GetRootControl().GetChildren():
        if keyword.lower() in (w.Name or "").lower():
            return w
    return None


def _walk_count(control, max_depth: int = 25) -> int:
    count = 0

    def _rec(c, d):
        nonlocal count
        if d > max_depth:
            return
        for ch in c.GetChildren():
            count += 1
            _rec(ch, d + 1)

    _rec(control, 0)
    return count


def warm_up(control, retries: int = 4, settle_delay: float = 0.4) -> int:
    """Repeatedly walks the tree until the node count stops growing (or the
    retry budget is spent). Returns the final node count."""
    last = -1
    for _ in range(retries):
        current = _walk_count(control)
        if current == last and current > 0:
            return current
        last = current
        time.sleep(settle_delay)
    return last


def collect_named_controls(control, max_depth: int = 25) -> list[tuple[str, str]]:
    """Returns [(control_type, name), ...] for every named descendant."""
    out: list[tuple[str, str]] = []

    def _rec(c, d):
        if d > max_depth:
            return
        for ch in c.GetChildren():
            name = (ch.Name or "").strip()
            if name:
                out.append((ch.ControlTypeName, name))
            _rec(ch, d + 1)

    _rec(control, 0)
    return out


def find_control_by_name(control, name: str, control_type: str | None = None, max_depth: int = 25):
    """Walks and returns the first descendant control whose Name matches
    exactly (and ControlTypeName too, if given) — for clicking, not just
    reading, since collect_named_controls only returns name strings."""
    result = [None]

    def _rec(c, d):
        if d > max_depth or result[0] is not None:
            return
        for ch in c.GetChildren():
            if result[0] is not None:
                return
            if (ch.Name or "").strip() == name and (control_type is None or ch.ControlTypeName == control_type):
                result[0] = ch
                return
            _rec(ch, d + 1)

    _rec(control, 0)
    return result[0]


def parse_sessions(named_controls: list[tuple[str, str]]) -> list[tuple[str, bool]]:
    """Extracts (session_name, is_running) from sidebar button names of the
    observed form 'Running <name>' / 'Idle <name>'. Non-session chrome
    buttons and per-session sub-buttons ('More options for ...', 'New
    session in ...') are filtered out."""
    sessions: list[tuple[str, bool]] = []
    seen = set()
    for ctype, name in named_controls:
        if ctype != "ButtonControl":
            continue
        low = name.lower()
        if low in _CHROME_BUTTONS:
            continue
        if any(low.startswith(p) for p in ("more options for", "new session in", "search")):
            continue
        running = None
        if low.startswith("running "):
            running, label = True, name[len("Running "):]
        elif low.startswith("idle "):
            running, label = False, name[len("Idle "):]
        else:
            continue
        if label not in seen:
            seen.add(label)
            sessions.append((label, running))
    return sessions


def detect_dialogs(named_controls: list[tuple[str, str]]) -> list[tuple[str, list[str]]]:
    """Best-effort: flags TextControl entries containing known trigger
    phrases, paired with any non-chrome button names present in the same
    scan (Claude Desktop's dialogs/banners aren't a distinct UIA region, so
    this can't precisely scope buttons to their dialog — reported as a flat
    list per the spec's safety rule: only a documented allowlist may ever be
    auto-clicked, everything else is surfaced for a human decision)."""
    texts = [name for ctype, name in named_controls if ctype == "TextControl"]
    buttons = [
        name for ctype, name in named_controls
        if ctype == "ButtonControl"
        and name.lower() not in _CHROME_BUTTONS
        and not any(name.lower().startswith(p) for p in (
            "more options for", "new session in", "running ", "idle ",
        ))
    ]
    dialogs = []
    for text in texts:
        low = text.lower()
        if any(k in low for k in _DIALOG_TRIGGER_KEYWORDS):
            dialogs.append((text, buttons))
    return dialogs
