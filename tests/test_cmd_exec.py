"""
execute_command is the shared "run it, log it, truncate it" logic behind
both the Telegram /cmd confirm button and the Mini App's own confirm
endpoint - exercised directly so both callers are guaranteed identical
behavior.
"""
import asyncio

from tether.platform import cmd_audit, shell
from tether.transport.cmd_exec import MAX_OUTPUT_LEN, execute_command


def test_successful_command_is_logged_and_returns_output(monkeypatch):
    logged = []
    monkeypatch.setattr(cmd_audit, "log_command", lambda cmd: logged.append(cmd))

    async def fake_run_cmd(command, **kwargs):
        return "hello output"

    monkeypatch.setattr(shell, "run_cmd", fake_run_cmd)

    ok, output = asyncio.run(execute_command("echo hello"))

    assert ok is True
    assert output == "hello output"
    assert logged == ["echo hello"]


def test_command_is_logged_before_running_even_if_it_raises(monkeypatch):
    """A command that crashes the shell should still show up in
    cmd_audit.log - logging must happen before execution, not after."""
    logged = []
    monkeypatch.setattr(cmd_audit, "log_command", lambda cmd: logged.append(cmd))

    async def fake_run_cmd(command, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(shell, "run_cmd", fake_run_cmd)

    ok, output = asyncio.run(execute_command("bad-command"))

    assert ok is False
    assert "boom" in output
    assert logged == ["bad-command"]


def test_long_output_is_truncated(monkeypatch):
    monkeypatch.setattr(cmd_audit, "log_command", lambda cmd: None)

    async def fake_run_cmd(command, **kwargs):
        return "x" * 10000

    monkeypatch.setattr(shell, "run_cmd", fake_run_cmd)

    ok, output = asyncio.run(execute_command("big-output"))

    assert ok is True
    assert len(output) <= MAX_OUTPUT_LEN + len("\n...(truncated)")
    assert output.endswith("...(truncated)")


def test_short_output_is_not_truncated(monkeypatch):
    monkeypatch.setattr(cmd_audit, "log_command", lambda cmd: None)

    async def fake_run_cmd(command, **kwargs):
        return "short"

    monkeypatch.setattr(shell, "run_cmd", fake_run_cmd)

    ok, output = asyncio.run(execute_command("echo short"))
    assert output == "short"
