"""
watchdog.py keeps tether running by relaunching it if the process
disappears - the one thing genuinely worth testing here is that it decides
correctly whether to relaunch, and that a launch actually invokes pythonw
against run.py rather than something else.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import watchdog  # noqa: E402


def test_pythonw_prefers_windowless_when_present(monkeypatch, tmp_path):
    fake_pythonw = tmp_path / "pythonw.exe"
    fake_pythonw.write_text("", encoding="utf-8")
    monkeypatch.setattr(watchdog.sys, "executable", str(tmp_path / "python.exe"))
    assert watchdog._pythonw() == str(fake_pythonw)


def test_pythonw_falls_back_to_python_exe_when_no_windowless_variant(monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog.sys, "executable", str(tmp_path / "python.exe"))
    # no pythonw.exe created in tmp_path
    assert watchdog._pythonw() == str(tmp_path / "python.exe")


def test_launch_invokes_pythonw_against_run_py(monkeypatch):
    calls = []
    monkeypatch.setattr(watchdog.subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    monkeypatch.setattr(watchdog, "_pythonw", lambda: "C:\\fake\\pythonw.exe")
    watchdog._launch_tether()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ["C:\\fake\\pythonw.exe", watchdog.RUN_PY]
    assert kwargs["cwd"] == watchdog.SCRIPT_DIR


def test_is_running_true_when_powershell_reports_a_pid(monkeypatch):
    class FakeResult:
        stdout = "12345\n"

    monkeypatch.setattr(watchdog.subprocess, "run", lambda *a, **kw: FakeResult())
    assert watchdog._is_tether_running() is True


def test_is_running_false_when_powershell_reports_nothing(monkeypatch):
    class FakeResult:
        stdout = "\n"

    monkeypatch.setattr(watchdog.subprocess, "run", lambda *a, **kw: FakeResult())
    assert watchdog._is_tether_running() is False


def test_is_running_assumes_true_on_a_check_failure():
    """A transient PowerShell hiccup must not be treated as "definitely
    down" - that would spawn a duplicate tether process running alongside
    a perfectly healthy one."""
    import subprocess as sp

    def _raise(*a, **kw):
        raise sp.TimeoutExpired(cmd="powershell", timeout=15)

    orig_run = watchdog.subprocess.run
    watchdog.subprocess.run = _raise
    try:
        assert watchdog._is_tether_running() is True
    finally:
        watchdog.subprocess.run = orig_run
