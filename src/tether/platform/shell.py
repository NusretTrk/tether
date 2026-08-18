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

_shell_cwd = os.path.expanduser("~")


async def run_cmd(command: str, timeout: int = 60) -> str:
    global _shell_cwd
    script = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        f"Set-Location -LiteralPath '{_shell_cwd}'; "
        f"{command}; "
        'Write-Output "___CWD___$((Get-Location).Path)"'
    )
    proc = await asyncio.create_subprocess_exec(
        "powershell", "-NoLogo", "-NoProfile", "-Command", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
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
