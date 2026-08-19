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
