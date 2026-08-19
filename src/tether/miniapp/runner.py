"""
Manages the local ngrok subprocess that tunnels the Mini App server to a
stable public HTTPS URL. Never auto-downloads ngrok - launches whatever
binary the user already installed themselves (mini_app_ngrok_path), same
trust boundary as tesseract.exe already had. The authtoken is handed to
the subprocess through its own environment (NGROK_AUTHTOKEN), never as a
command-line argument - a command-line argument is visible to anything
that can list processes (Task Manager, any other program running as the
same user) for as long as the process lives; an environment variable of
a spawned child is not.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time

log = logging.getLogger(__name__)

RESTART_MAX_ATTEMPTS = 5
RESTART_WINDOW_SEC = 600


class NgrokRunner:
    def __init__(self, ngrok_path: str, domain: str, local_port: int, authtoken: str):
        self.ngrok_path = ngrok_path
        self.domain = domain
        self.local_port = local_port
        self.authtoken = authtoken
        self._process: subprocess.Popen | None = None
        self._stop_requested = False
        self._restart_times: list[float] = []
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            self._stop_requested = False
            if self._process is not None and self._process.poll() is None:
                return True
            env = dict(os.environ)
            env["NGROK_AUTHTOKEN"] = self.authtoken
            try:
                self._process = subprocess.Popen(
                    [self.ngrok_path, "http", f"--domain={self.domain}", str(self.local_port)],
                    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError:
                log.error("could not launch ngrok at %r - is it installed?", self.ngrok_path, exc_info=True)
                return False
            log.info("ngrok tunnel starting: %s -> localhost:%s", self.domain, self.local_port)
            return True

    def stop(self) -> None:
        with self._lock:
            self._stop_requested = True
            process, self._process = self._process, None
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def ensure_running(self) -> None:
        """Relaunches ngrok if it died on its own since the last check.
        Capped within a rolling window so a persistent failure (bad
        authtoken, domain already claimed elsewhere, no internet) can't
        loop forever hammering ngrok's own servers - same rolling-window
        shape as monitors/recovery.py, just without the idle-gating that
        doesn't apply to a background tunnel process."""
        with self._lock:
            if self._stop_requested:
                return
            if self._process is not None and self._process.poll() is None:
                return
            now = time.monotonic()
            self._restart_times = [t for t in self._restart_times if now - t < RESTART_WINDOW_SEC]
            if len(self._restart_times) >= RESTART_MAX_ATTEMPTS:
                return
            self._restart_times.append(now)
        self.start()
