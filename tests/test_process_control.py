"""
Process control is path-based, not name-based, for one specific reason:
Claude Desktop is a dozen processes named claude.exe, and the Claude Code
CLI is *also* claude.exe at a different path. A name-based kill hits both.
On this machine the CLI is frequently the agent issuing the command, so
that mistake would have it terminate itself mid-task.
"""
import pytest

from tether.platform.capabilities import CAPABILITIES
from tether.targets.claude_desktop import ClaudeDesktopTarget

pytestmark = pytest.mark.skipif(not CAPABILITIES.window_control, reason="Windows process APIs")


def test_desktop_filter_excludes_the_cli():
    """The critical safety property. If these ever overlap, /restart would
    kill the CLI along with the desktop app."""
    from tether.platform.process import list_processes

    desktop = {p.pid for p in list_processes(name_contains="claude", path_contains="WindowsApps")}
    cli = {p.pid for p in list_processes(name_contains="claude", path_contains="claude-code")}
    assert not (desktop & cli), (
        f"desktop-app filter also matched the Claude Code CLI: {desktop & cli}"
    )


def test_target_app_processes_never_include_claude_code():
    target = ClaudeDesktopTarget("Claude")
    for proc in target.list_app_processes():
        assert "claude-code" not in proc.path.lower(), (
            f"target would kill the Claude Code CLI: {proc.path}"
        )


def test_list_processes_returns_absolute_paths():
    from tether.platform.process import list_processes
    for proc in list_processes(name_contains="claude")[:3]:
        assert ":" in proc.path or proc.path.startswith("\\\\")


def test_is_running_false_for_impossible_pid():
    from tether.platform.process import is_running
    assert is_running(999_999_999) is False


def test_wait_until_gone_returns_immediately_for_dead_pids():
    from tether.platform.process import wait_until_gone
    assert wait_until_gone([999_999_999], timeout=2.0) is True


def test_launch_command_discovered_at_runtime():
    """The package family name has a per-install hash, so it can't be
    hardcoded and still work on anyone else's machine."""
    target = ClaudeDesktopTarget("Claude")
    cmd = target.resolve_launch_command()
    if cmd is not None:  # only assert shape if Claude is actually installed
        assert "shell:AppsFolder" in cmd


def test_configured_launch_command_wins_over_discovery():
    target = ClaudeDesktopTarget("Claude", launch_command="custom.exe --flag")
    assert target.resolve_launch_command() == "custom.exe --flag"


def test_custom_path_filter_is_respected():
    target = ClaudeDesktopTarget("Claude", app_path_filter="definitely-not-a-real-path")
    assert target.list_app_processes() == []
