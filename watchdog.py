"""
Keeps tether running. Checks periodically whether the main process (run.py)
is alive; if not, relaunches it - unconditionally, regardless of whether it
crashed or was closed from Task Manager on purpose. That's deliberate: this
script has no way to tell those two apart (unlike the in-app self-healing
for Claude Desktop, which uses idle-time as a signal - there's no
equivalent signal for "why did my own process disappear").

To actually stop tether and have it stay stopped, use stop_tether.bat,
which kills this watchdog process too - otherwise it would just relaunch
tether again on the next check.

install_autostart.ps1 points the Startup shortcut at this script instead
of run.py directly, so the same resilience applies whether tether was
started at login or via start_tether.bat.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_PY = os.path.join(SCRIPT_DIR, "run.py")
CHECK_INTERVAL_SEC = 30
STARTUP_GRACE_SEC = 10

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _is_tether_running() -> bool:
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_Process | Where-Object { "
                "$_.CommandLine -like '*run.py*' -and "
                "($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') "
                "}).ProcessId",
            ],
            capture_output=True, text=True, timeout=15, creationflags=_NO_WINDOW,
        )
        return bool(result.stdout.strip())
    except Exception:
        # Can't confirm either way - assume it's running rather than risk
        # spawning a duplicate process on a transient PowerShell hiccup.
        return True


def _pythonw() -> str:
    candidate = sys.executable.replace("python.exe", "pythonw.exe")
    return candidate if os.path.exists(candidate) else sys.executable


def _launch_tether() -> None:
    subprocess.Popen(
        [_pythonw(), RUN_PY],
        cwd=SCRIPT_DIR,
        creationflags=_NO_WINDOW,
    )


def main() -> None:
    while True:
        if not _is_tether_running():
            _launch_tether()
            time.sleep(STARTUP_GRACE_SEC)
        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    main()
