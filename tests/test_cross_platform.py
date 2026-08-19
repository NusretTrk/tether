"""
The bot must load and run its monitoring half on any OS. Only the control
features (window, accessibility) are Windows-only, and those must fail with
a clear message rather than an ImportError from deep in the stack.

These run in a subprocess with the capability flags forced off, because the
platform modules read them at import time.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run_simulating_unsupported(body: str):
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, r"{ROOT / 'src'}")
        import tether.platform.capabilities as caps
        caps.CAPABILITIES = caps.Capabilities(
            window_control=False, accessibility=False,
            hardware_temps=False, shell=True, power_control=False,
        )
        {textwrap.indent(textwrap.dedent(body), '        ').strip()}
    """)
    return subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)


def test_all_modules_import_without_windows_libraries():
    r = _run_simulating_unsupported("""
        from tether.platform import window, uia, shell, ocr
        from tether.monitors import temps, activity, dialogs
        from tether.sources import transcript, discovery
        from tether.targets import claude_desktop
        from tether import events, config, i18n, logsetup
        print("OK")
    """)
    assert r.returncode == 0, f"import failed on simulated non-Windows:\n{r.stderr}"
    assert "OK" in r.stdout


def test_control_features_raise_a_clear_error():
    r = _run_simulating_unsupported("""
        from tether.platform import window
        from tether.platform.capabilities import UnsupportedOnThisPlatform
        try:
            window.find_window_by_keyword("anything")
            print("NO_ERROR")
        except UnsupportedOnThisPlatform as e:
            print("CLEAN" if "only implemented on Windows" in str(e) else "UNCLEAR")
    """)
    assert "CLEAN" in r.stdout, f"got: {r.stdout} {r.stderr}"


def test_target_reports_unavailable_rather_than_crashing():
    r = _run_simulating_unsupported("""
        from tether.targets.claude_desktop import ClaudeDesktopTarget
        t = ClaudeDesktopTarget("Claude")
        assert t.is_available() is False
        assert t.list_sessions() == []
        assert t.detect_dialogs() == []
        assert t.switch_session("x") is False
        print("OK")
    """)
    assert "OK" in r.stdout, f"got: {r.stdout} {r.stderr}"


def test_monitoring_half_still_works():
    r = _run_simulating_unsupported("""
        from tether.monitors.temps import get_cpu_temp
        from tether.sources.discovery import find_active_transcript
        assert get_cpu_temp() is None          # degrades, does not raise
        find_active_transcript()               # must not raise
        print("OK")
    """)
    assert "OK" in r.stdout, f"got: {r.stdout} {r.stderr}"


def _run_simulating_real_platform(platform_value: str, body: str):
    """Unlike _run_simulating_unsupported, this patches sys.platform BEFORE
    tether.platform.capabilities is ever imported, so detect() actually runs
    its real macOS/Linux branch - exercising the window.py dispatch to
    window_macos.py/window_linux.py, not just the "everything off" path."""
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, r"{ROOT / 'src'}")
        sys.platform = "{platform_value}"
        {textwrap.indent(textwrap.dedent(body), '        ').strip()}
    """)
    return subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)


def test_macos_capabilities_enable_window_control_not_accessibility():
    r = _run_simulating_real_platform("darwin", """
        from tether.platform.capabilities import detect
        caps = detect()
        assert caps.window_control is True
        assert caps.accessibility is False
        assert caps.power_control is False
        print("OK")
    """)
    assert "OK" in r.stdout, f"got: {r.stdout} {r.stderr}"


def test_linux_capabilities_enable_window_control_not_accessibility():
    r = _run_simulating_real_platform("linux", """
        from tether.platform.capabilities import detect
        caps = detect()
        assert caps.window_control is True
        assert caps.accessibility is False
        assert caps.power_control is False
        print("OK")
    """)
    assert "OK" in r.stdout, f"got: {r.stdout} {r.stderr}"


def test_macos_window_dispatch_selects_the_macos_module_by_source():
    """Can't actually import window_macos.py here to check identity - it
    imports pyautogui, which on a real Mac needs pyobjc (Quartz/AppKit)
    installed, and this dev machine is Windows with no way to fake that
    native dependency the way sys.platform can be faked. So this checks the
    dispatch wiring the same way a human reviewer would: read window.py's
    source and confirm the macOS branch actually points at window_macos."""
    source = (ROOT / "src" / "tether" / "platform" / "window.py").read_text(encoding="utf-8")
    assert "from tether.platform.window_macos import" in source
    assert "from tether.platform.window_linux import" in source
    assert "if IS_MACOS:" in source
    assert "elif IS_LINUX:" in source


def test_macos_and_linux_window_modules_declare_the_same_primitives_as_windows():
    """Structural parity check: whatever window.py exposes on Windows must
    exist under the same name in both platform modules, or the dispatch
    silently leaves a stale/undefined name on that platform."""
    import ast

    def _top_level_function_names(path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        return {n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}

    base = ROOT / "src" / "tether" / "platform"
    windows_names = _top_level_function_names(base / "window.py")
    macos_names = _top_level_function_names(base / "window_macos.py")
    linux_names = _top_level_function_names(base / "window_linux.py")

    required = {"find_window_by_keyword", "focus_window", "capture_window", "get_window_rect", "set_clipboard_image"}
    assert required <= windows_names
    assert required <= macos_names, f"window_macos.py missing: {required - macos_names}"
    assert required <= linux_names, f"window_linux.py missing: {required - linux_names}"
