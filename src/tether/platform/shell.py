"""
PowerShell command execution with a tracked working directory. Each /cmd
spawns a fresh hidden PowerShell (CREATE_NO_WINDOW) and exits immediately —
no lingering background process to leak or manage. Working directory is
tracked here in Python and re-applied each call, so `cd` still carries over
between commands the way a real session would feel. Ported unchanged from
the original bot.py.
"""
from __future__ import annotations

import asyncio
import os
import subprocess

from tether.platform.capabilities import CAPABILITIES

_shell_cwd = os.path.expanduser("~")

# CREATE_NO_WINDOW only exists on Windows; passing it elsewhere raises.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


async def run_cmd(command: str, timeout: int = 60) -> str:
    global _shell_cwd
    if CAPABILITIES.window_control:  # Windows
        # PowerShell escapes a single quote inside a single-quoted string by
        # doubling it. Without this, any directory with an apostrophe in the
        # name breaks the generated script.
        safe_cwd = _shell_cwd.replace("'", "''")
        script = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            f"Set-Location -LiteralPath '{safe_cwd}'; "
            f"{command}; "
            'Write-Output "___CWD___$((Get-Location).Path)"'
        )
        argv = ["powershell", "-NoLogo", "-NoProfile", "-Command", script]
    else:
        # POSIX shells take the same approach: single quotes, with embedded
        # quotes closed and re-opened.
        safe_cwd = _shell_cwd.replace("'", "'\''")
        script = f"cd '{safe_cwd}' && {command}; printf '___CWD___%s\n' \"$(pwd)\""
        argv = ["/bin/sh", "-c", script]

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        creationflags=_NO_WINDOW,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return "(timeout)"

    text = stdout.decode("utf-8", errors="replace")
    output_lines = []
    for line in text.splitlines():
        if line.startswith("___CWD___"):
            _shell_cwd = line[len("___CWD___"):].strip()
        else:
            output_lines.append(line)
    return "\n".join(output_lines).strip() or "(no output)"
