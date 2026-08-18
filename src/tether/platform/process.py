"""
Process discovery and lifecycle control.

Deliberately path-based rather than image-name based. Claude Desktop runs
as a dozen Electron processes all named claude.exe, and the Claude Code
CLI is *also* called claude.exe while living somewhere completely
different. A `taskkill /IM Claude.exe` matches both - killing the desktop
app would also kill the CLI, which on this machine is frequently the agent
doing the killing. Every operation here filters on the executable's real
path so one can be targeted without touching the other.
"""
from __future__ import annotations

import ctypes
import logging
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass

from tether.platform.capabilities import CAPABILITIES

log = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_TERMINATE = 0x0001
STILL_ACTIVE = 259

if CAPABILITIES.window_control:
    _psapi = ctypes.WinDLL("psapi", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    path: str


def _enum_pids(max_count: int = 4096) -> list[int]:
    arr = (wintypes.DWORD * max_count)()
    needed = wintypes.DWORD()
    if not _psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(needed)):
        return []
    return list(arr[: needed.value // ctypes.sizeof(wintypes.DWORD)])


def _process_path(pid: int) -> str | None:
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        _kernel32.CloseHandle(handle)


def list_processes(name_contains: str | None = None, path_contains: str | None = None) -> list[ProcessInfo]:
    """Processes matching both filters (case-insensitive substring match).
    Processes whose path can't be read - system processes, or anything
    running as another user - are skipped rather than guessed at."""
    if not CAPABILITIES.window_control:
        return []
    out: list[ProcessInfo] = []
    for pid in _enum_pids():
        if pid == 0:
            continue
        path = _process_path(pid)
        if not path:
            continue
        name = path.rsplit("\\", 1)[-1]
        if name_contains and name_contains.lower() not in name.lower():
            continue
        if path_contains and path_contains.lower() not in path.lower():
            continue
        out.append(ProcessInfo(pid=pid, name=name, path=path))
    return out


def is_running(pid: int) -> bool:
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if _kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return code.value == STILL_ACTIVE
        return False
    finally:
        _kernel32.CloseHandle(handle)


def terminate(pid: int) -> bool:
    handle = _kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(_kernel32.TerminateProcess(handle, 1))
    finally:
        _kernel32.CloseHandle(handle)


def wait_until_gone(pids: list[int], timeout: float = 15.0, poll: float = 0.25) -> bool:
    """Blocks until every pid has actually exited.

    This is the step that matters for relaunching: Windows keeps file
    handles open until the last process in the tree is really gone, and
    starting the app again too early produces "Another program is currently
    using this file". Returns False on timeout so callers can report rather
    than relaunch into a broken state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(is_running(p) for p in pids):
            return True
        time.sleep(poll)
    return not any(is_running(p) for p in pids)


def kill_all(processes: list[ProcessInfo], timeout: float = 15.0) -> tuple[int, bool]:
    """Terminates every given process and waits for the handles to release.
    Returns (how many were signalled, whether they all actually exited)."""
    pids = [p.pid for p in processes]
    signalled = sum(1 for pid in pids if terminate(pid))
    return signalled, wait_until_gone(pids, timeout=timeout)


def launch(command: str) -> bool:
    """Starts an app. Store/MSIX packages have no launchable exe path that
    works directly (the one under WindowsApps refuses to start with a
    permissions error), so those are launched through the shell by
    AppUserModelID - the same mechanism the Start menu uses."""
    if not CAPABILITIES.window_control:
        return False
    try:
        subprocess.Popen(command, shell=True, creationflags=_NO_WINDOW)
        return True
    except Exception as e:
        log.warning("launch(%r) failed: %s", command, e)
        return False


def find_appx_launch_command(package_name_contains: str) -> str | None:
    """Builds a shell:AppsFolder launch command for an installed Store app,
    discovered at runtime rather than hardcoded - the package family name
    contains a per-install hash, so it differs between machines."""
    if not CAPABILITIES.window_control:
        return None
    ps = (
        f"$p = Get-AppxPackage | Where-Object {{ $_.Name -like '*{package_name_contains}*' }} | Select-Object -First 1; "
        "if ($p) { "
        "$id = (Get-AppxPackageManifest $p).Package.Applications.Application.Id; "
        "Write-Output \"$($p.PackageFamilyName)!$id\" }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoLogo", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=20, creationflags=_NO_WINDOW,
        )
        aumid = result.stdout.strip().splitlines()
        if not aumid or not aumid[0].strip():
            return None
        return "explorer.exe shell:AppsFolder\\" + aumid[0].strip()
    except Exception as e:
        log.warning("find_appx_launch_command(%r) failed: %s", package_name_contains, e)
        return None
