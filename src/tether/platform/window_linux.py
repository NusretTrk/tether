"""
Linux window find/focus/capture, via `xdotool` (X11 only — this is
XTest-based input simulation, which does not exist under Wayland; a Wayland
session needs a different mechanism entirely, e.g. per-compositor portals,
not implemented here). Requires xdotool and xclip installed.

UNVERIFIED: written against documented xdotool/xclip syntax, never run
against a real Claude Desktop window on Linux. Same caveat as the macOS
module - the window-find/focus/rect primitives here are the load-bearing
ones for basic remote control; the pixel-OCR-driven model/effort picker was
tuned against the Windows build's layout and may need real adjustment.
"""
from __future__ import annotations

import io
import logging
import subprocess
import time

import pyautogui
from PIL import Image

from tether.platform.capabilities import CAPABILITIES, UnsupportedOnThisPlatform

log = logging.getLogger(__name__)


def _require_linux(feature: str) -> None:
    if not CAPABILITIES.window_control:
        raise UnsupportedOnThisPlatform(feature)


def _xdotool(*args: str) -> str:
    result = subprocess.run(
        ["xdotool", *args], capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"xdotool exited {result.returncode}")
    return result.stdout.strip()


def _geometry(window_id: int) -> dict[str, int]:
    out = _xdotool("getwindowgeometry", "--shell", str(window_id))
    dims: dict[str, int] = {}
    for line in out.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            try:
                dims[key] = int(value)
            except ValueError:
                pass
    return dims


def find_window_by_keyword(keyword: str, path_contains: str | None = None) -> int | None:
    """Picks the largest-area match, same reasoning as the Windows
    implementation - a toolbar/side-panel window can also match the
    keyword, the real app window is usually the biggest.

    `path_contains` is accepted for signature compatibility with the
    Windows implementation (which rejects a title match whose owning
    process lives somewhere unexpected, e.g. a browser tab outranking the
    real app purely by title) but not applied here yet - doing this
    properly needs real Linux hardware to verify against, which this
    project doesn't have (see the module-level "unverified" note)."""
    _require_linux("Finding a window")
    try:
        out = _xdotool("search", "--name", keyword)
    except RuntimeError as e:
        log.warning("find_window_by_keyword (Linux/xdotool) failed: %s", e)
        return None
    ids = [int(x) for x in out.splitlines() if x.strip().isdigit()]
    if not ids:
        return None

    def _area(wid: int) -> int:
        dims = _geometry(wid)
        return dims.get("WIDTH", 0) * dims.get("HEIGHT", 0)

    return max(ids, key=_area)


def get_window_rect(window_id: int) -> tuple[int, int, int, int]:
    _require_linux("Getting window rect")
    dims = _geometry(window_id)
    x, y = dims.get("X", 0), dims.get("Y", 0)
    w, h = dims.get("WIDTH", 0), dims.get("HEIGHT", 0)
    return (x, y, x + w, y + h)


def focus_window(window_id: int, retries: int = 4) -> bool:
    _require_linux("Focusing a window")
    for _ in range(retries):
        try:
            _xdotool("windowactivate", "--sync", str(window_id))
        except RuntimeError as e:
            log.warning("focus_window (Linux/xdotool) failed: %s", e)
        try:
            active = int(_xdotool("getactivewindow"))
            if active == window_id:
                return True
        except (RuntimeError, ValueError):
            pass
        time.sleep(0.15)
    log.error("focus_window (Linux): could not confirm active window for %s", window_id)
    return False


def capture_window(window_id: int) -> Image.Image:
    """Screen-region grab of the window's current bounds (see the macOS
    module's capture_window for why this isn't a true per-window buffer
    capture - same tradeoff applies here)."""
    _require_linux("Capturing a window")
    left, top, right, bottom = get_window_rect(window_id)
    return pyautogui.screenshot(region=(left, top, right - left, bottom - top))


def set_clipboard_image(image_bytes: bytes) -> bool:
    _require_linux("Setting clipboard image")
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        result = subprocess.run(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-i"],
            input=buf.getvalue(), capture_output=True, timeout=15,
        )
        return result.returncode == 0
    except Exception as e:
        log.warning("set_clipboard_image (Linux/xclip) failed: %s", e)
        return False
