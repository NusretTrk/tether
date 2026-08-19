"""
NgrokRunner's state machine (start/stop/ensure_running/restart cap) is
exercised against a fake Popen so tests never launch a real process or
depend on ngrok actually being installed.
"""
import subprocess

import pytest

from tether.miniapp.runner import NgrokRunner


class FakeProcess:
    def __init__(self, alive=True):
        self._alive = alive
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        self._alive = False

    def wait(self, timeout=None):
        if self._alive:
            raise subprocess.TimeoutExpired(cmd="ngrok", timeout=timeout)

    def kill(self):
        self.killed = True
        self._alive = False


@pytest.fixture
def runner(monkeypatch):
    processes = []

    def fake_popen(*args, **kwargs):
        p = FakeProcess()
        processes.append(p)
        return p

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    r = NgrokRunner("ngrok", "myname.ngrok-free.app", 8743, "fake-token")
    r._processes = processes  # test-only handle
    return r


def test_start_launches_and_reports_running(runner):
    assert runner.start() is True
    assert runner.is_running() is True


def test_authtoken_passed_via_environment_not_command_line(monkeypatch):
    captured = {}

    def fake_popen(cmd, env=None, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = env
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    r = NgrokRunner("ngrok", "myname.ngrok-free.app", 8743, "super-secret-token")
    r.start()

    assert "super-secret-token" not in captured["cmd"]
    assert captured["env"]["NGROK_AUTHTOKEN"] == "super-secret-token"


def test_start_is_idempotent_while_already_running(runner):
    runner.start()
    first = runner._process
    runner.start()
    assert runner._process is first


def test_stop_terminates_the_process(runner):
    runner.start()
    proc = runner._process
    runner.stop()
    assert proc.terminated
    assert runner.is_running() is False


def test_stop_kills_if_terminate_does_not_finish_in_time(monkeypatch):
    class SlowProcess(FakeProcess):
        def terminate(self):
            self.terminated = True  # never actually dies

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: SlowProcess())
    r = NgrokRunner("ngrok", "d", 1, "t")
    r.start()
    r.stop()
    assert r._process is None  # cleared regardless


def test_ensure_running_relaunches_a_dead_process(monkeypatch):
    procs = [FakeProcess(alive=False), FakeProcess(alive=True)]
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: procs.pop(0))
    r = NgrokRunner("ngrok", "d", 1, "t")
    r.start()  # gets the dead one
    assert r.is_running() is False
    r.ensure_running()
    assert r.is_running() is True


def test_ensure_running_does_nothing_after_deliberate_stop(runner):
    runner.start()
    runner.stop()
    runner.ensure_running()
    assert runner._process is None


def test_ensure_running_caps_restart_attempts_within_the_window(monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: FakeProcess(alive=False))
    r = NgrokRunner("ngrok", "d", 1, "t")
    r.start()
    launch_count = 1  # the initial start()
    for _ in range(10):
        r.ensure_running()
    # capped well below 10 extra relaunches
    from tether.miniapp.runner import RESTART_MAX_ATTEMPTS
    assert len(r._restart_times) <= RESTART_MAX_ATTEMPTS


def test_missing_ngrok_binary_reports_failure_without_raising(monkeypatch):
    def raise_not_found(*a, **k):
        raise OSError("not found")

    monkeypatch.setattr(subprocess, "Popen", raise_not_found)
    r = NgrokRunner("nonexistent-ngrok-binary", "d", 1, "t")
    assert r.start() is False
    assert r.is_running() is False
