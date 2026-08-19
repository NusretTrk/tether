"""
Shared "run the staged command, log it, return the output" logic -
transport/callbacks.py's cmd:confirm callback and the Mini App's own
POST /api/cmd/confirm both go through this, so a command run from
either place gets the exact same audit-logging and output truncation,
not two copies that can quietly drift apart.
"""
from __future__ import annotations

MAX_OUTPUT_LEN = 4000


async def execute_command(command: str) -> tuple[bool, str]:
    """Returns (ok, output_or_error). Always audit-logs BEFORE running,
    matching the existing behavior - a command that times out or crashes
    the shell should still show up in cmd_audit.log."""
    from tether.platform.cmd_audit import log_command
    from tether.platform.shell import run_cmd

    log_command(command)
    try:
        output = await run_cmd(command)
    except Exception as e:
        return False, str(e)
    if len(output) > MAX_OUTPUT_LEN:
        output = output[:MAX_OUTPUT_LEN] + "\n...(truncated)"
    return True, output
