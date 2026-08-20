"""
Local HTTP server for the Mini App, tunneled to the outside world by the
user's own ngrok process (see runner.py) — this module never talks to the
network directly, only to localhost.

Deliberately stdlib-only (http.server), not a new pip dependency: the
whole surface here is a handful of read endpoints plus two small mutating
ones, nowhere near enough to justify pulling in a real web framework, and
the user was explicit that this feature shouldn't add resource weight.

Every /api/* request must carry a valid, freshly-signed Telegram initData
in its Authorization header (see miniapp/auth.py for what "valid" means)
- the ngrok URL itself is not a secret, so this is the actual security
boundary. A repeated run of bad signatures trips the same
LockoutDecider shape /unlock already uses, and (unlike /unlock, whose
failed guesses are already visible to the owner in their own chat) fires
a one-time Telegram alert the moment it trips, since these attempts could
be coming from a total stranger who merely found the URL.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from tether.miniapp.auth import validate_init_data
from tether.miniapp.frontend import INDEX_HTML
from tether.monitors.lockout import LockoutDecider, LockoutPolicy

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 8192
MAX_SEND_TEXT_LENGTH = 4096  # matches Telegram's own message length cap
MAX_CONCURRENT_CONNECTIONS = 20
ALLOWED_LANGUAGES = {"en", "tr", "de", "es"}
ALLOWED_OUTPUT_MODES = {"live", "summary", "quiet", "verbose"}

# Plain on/off feature toggles - each just flips a bool, no extra validation
# beyond "is this actually a bool". Deliberately only the watcher/behavior
# toggles that were previously config.yaml-and-restart-only - not every
# Settings field (window keywords, poll intervals) belongs in a quick
# settings screen, and some (auto_recover_*, BOT_PASSWORD) are either too
# easy to misconfigure remotely or a security control that shouldn't be
# togglable from the same surface it's meant to protect.
BOOL_SETTINGS_KEYS = {
    "confirm_before_send", "mini_app_enabled",
    "dialog_watch_enabled", "stall_watch_enabled", "activity_watch_enabled",
    "app_health_watch_enabled", "usage_limit_continue_enabled", "preserve_user_clipboard",
}
# key -> (min, max) inclusive. Bounds match Settings.validate()'s own sane
# ranges where one exists (temp_emergency_c), otherwise a judgment call
# wide enough to be useful but narrow enough that a fat-fingered value
# can't wedge the bot (e.g. a 0-second idle threshold that fires instantly).
NUMERIC_SETTINGS_KEYS = {
    "temp_emergency_c": (1, 150),
    "defer_when_user_active_sec": (0, 600),
    "auto_send_after_idle_sec": (0, 3600),
}
ALLOWED_SETTINGS_KEYS = BOOL_SETTINGS_KEYS | set(NUMERIC_SETTINGS_KEYS) | {"language", "output_mode"}


class MiniAppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, state, bot, event_loop):
        super().__init__(address, _Handler)
        self.state = state
        self.bot = bot
        self.event_loop = event_loop
        self.lockout = LockoutDecider(LockoutPolicy(max_attempts=8, window_sec=300))
        self.lockout_lock = threading.Lock()
        self._lockout_alerted = False
        self._active_connections = 0
        self._connections_lock = threading.Lock()

    def process_request(self, request, client_address):
        """Caps concurrent connections before a thread is even spawned -
        ThreadingHTTPServer has no built-in limit, so an internet-facing
        instance (this one, via ngrok) would otherwise spawn one OS thread
        per incoming connection with no ceiling, a real resource-exhaustion
        angle for something reachable from outside the owner's own network."""
        with self._connections_lock:
            if self._active_connections >= MAX_CONCURRENT_CONNECTIONS:
                self.shutdown_request(request)
                return
            self._active_connections += 1
        try:
            super().process_request(request, client_address)
        except Exception:
            with self._connections_lock:
                self._active_connections -= 1
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._connections_lock:
                self._active_connections -= 1

    def _bridge_send_message(self, text: str) -> None:
        """Fires a Telegram message from this server's own worker thread by
        scheduling the actual send back onto the bot's asyncio event loop -
        the PTB Bot object's methods are coroutines and aren't safe to call
        directly from a foreign OS thread."""
        chat_id = self.state.config.secrets.chat_id
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.bot.send_message(chat_id, text), self.event_loop,
            )
            future.result(timeout=10)
        except Exception:
            log.warning("mini app: failed to deliver bridged alert", exc_info=True)

    def note_auth_failure(self) -> bool:
        """Records a failed auth attempt, returns True if this call just
        tipped the lockout over (so the caller sends exactly one alert)."""
        with self.lockout_lock:
            now = time.monotonic()
            was_locked = self.lockout.is_locked_out(now)
            self.lockout.record_failure(now)
            just_tripped = (not was_locked) and self.lockout.is_locked_out(now) and not self._lockout_alerted
            if just_tripped:
                self._lockout_alerted = True
            return just_tripped

    def is_locked_out(self) -> bool:
        with self.lockout_lock:
            return self.lockout.is_locked_out(time.monotonic())

    def reset_lockout_alert_flag(self) -> None:
        with self.lockout_lock:
            self._lockout_alerted = False


class _Handler(BaseHTTPRequestHandler):
    server: MiniAppServer  # type: ignore[assignment]
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # silence default stderr access logging
        log.debug("mini app http: " + fmt, *args)

    # ---- plumbing ----

    def _send_json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > MAX_BODY_BYTES:
            return None
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _authorize(self) -> int | None:
        """Returns a signed user id on success, or None + writes an error
        response itself on failure (so callers just check for None).

        Two independent credentials are accepted, either is sufficient:
        a fresh Telegram `tma <initData>` (the normal launch, see auth.py)
        or a `Bearer <token>` matching the current web_token_hash (the
        "add to home screen" path, see webtoken.py - there is no Telegram
        session to sign anything when this page is opened as a bookmarked
        web app instead of a real Mini App launch). Both funnel into the
        same lockout/alert handling below - a flood of bad bearer tokens
        is just as real an attack signal as a flood of bad signatures."""
        if self.server.is_locked_out():
            self._send_json(429, {"error": "too_many_failed_attempts"})
            return None

        state = self.server.state
        header = self.headers.get("Authorization", "")

        if header.startswith("Bearer "):
            from tether.miniapp.webtoken import verify
            if not verify(header[7:], state.web_token_hash):
                self._reject_auth("bad_web_token")
                return None
            user_id = state.config.secrets.chat_id
        else:
            init_data = header[4:] if header.startswith("tma ") else ""
            result = validate_init_data(init_data, state.config.secrets.bot_token, state.config.secrets.chat_id)
            if not result.ok:
                self._reject_auth(result.reason)
                return None
            user_id = result.user_id

        # A validly-signed initData (or a matching web token) only proves "this really is a Telegram
        # session for the authorized chat_id" - exactly the same thing the
        # chat_id check on every other handler proves, and exactly the
        # thing BOT_PASSWORD exists to add a second factor on top of (see
        # transport/handlers.py::restricted's own docstring: the password
        # protects against the owner's own Telegram account being
        # compromised, a scenario where the attacker genuinely IS the
        # authorized chat_id as far as Telegram - and initData - are
        # concerned). Skipping this check would make BOT_PASSWORD
        # meaningless for this entire surface. Not counted as an auth
        # failure/lockout trigger - the signature is genuine, the account
        # just isn't unlocked, a different thing from a forged request.
        if state.config.secrets.bot_password and not state.unlocked:
            self._send_json(423, {"error": "locked"})
            return None

        return user_id

    def _reject_auth(self, reason: str) -> None:
        just_tripped = self.server.note_auth_failure()
        log.warning("mini app: rejected request (%s)", reason)
        if just_tripped:
            self.server._bridge_send_message(
                "⚠️ Mini App: repeated invalid access attempts were just blocked for a few minutes. "
                "If this wasn't you, your ngrok URL may have leaked - consider reclaiming a new static domain, "
                "and run /miniapp revoke if you'd issued a browser link.",
            )
        self._send_json(401, {"error": reason})

    # ---- routing ----

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self._send_html(INDEX_HTML)
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path == "/api/status":
            self._handle_status()
            return
        if path == "/api/sessions":
            self._handle_sessions()
            return
        if path == "/api/transcript":
            self._handle_transcript()
            return
        if path == "/api/settings":
            self._handle_settings_get()
            return
        if path == "/api/models":
            self._handle_models()
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/api/sessions/switch":
            self._handle_session_switch()
            return
        if path == "/api/settings":
            self._handle_settings_post()
            return
        if path == "/api/send":
            self._handle_send()
            return
        if path == "/api/model":
            self._handle_model_set()
            return
        if path == "/api/cmd/stage":
            self._handle_cmd_stage()
            return
        if path == "/api/cmd/confirm":
            self._handle_cmd_confirm()
            return
        if path == "/api/cmd/cancel":
            self._handle_cmd_cancel()
            return
        self._send_json(404, {"error": "not_found"})

    # ---- handlers ----

    def _handle_status(self):
        if self._authorize() is None:
            return
        state = self.server.state
        from tether.monitors.temps import get_cpu_temp, get_gpu_temp
        status = state.target.read_status()
        cpu = get_cpu_temp()
        gpu, fan = get_gpu_temp()
        self._send_json(200, {
            "model": status.model, "effort": status.effort,
            "cpu_c": cpu, "gpu_c": gpu, "fan": fan,
            "output_mode": state.config.settings.output_mode,
            "target": state.active_target_profile or "claude",
        })

    def _handle_sessions(self):
        if self._authorize() is None:
            return
        state = self.server.state
        sessions = state.target.list_sessions()
        self._send_json(200, {"sessions": [{"name": s.name, "running": s.running} for s in sessions]})

    def _handle_session_switch(self):
        if self._authorize() is None:
            return
        body = self._read_json_body()
        name = (body or {}).get("name")
        if not name or not isinstance(name, str):
            self._send_json(400, {"error": "missing_name"})
            return
        ok = self.server.state.target.switch_session(name)
        self._send_json(200 if ok else 409, {"ok": ok})

    def _handle_models(self):
        """Lists switchable models for whatever /target currently points
        at. Claude Desktop has a fixed, known set (MODEL_NAMES) - listing
        it costs nothing. A /target-routed app (GenericTarget) has no
        fixed list of its own; list_models() actually opens its picker
        and OCRs whatever's visible, the same live-read every other
        GenericTarget model operation already does."""
        if self._authorize() is None:
            return
        from tether.transport.target_resolve import active_target
        state = self.server.state
        target = active_target(state)
        if target is state.target:
            from tether.targets.claude_desktop import MODEL_NAMES
            models = list(MODEL_NAMES)
            current = state.target.read_status().model
        else:
            models = target.list_models() if hasattr(target, "list_models") else []
            current = None
        self._send_json(200, {"models": models, "current": current})

    def _handle_model_set(self):
        if self._authorize() is None:
            return
        body = self._read_json_body()
        name = (body or {}).get("name")
        if not name or not isinstance(name, str) or not name.strip():
            self._send_json(400, {"error": "missing_name"})
            return
        from tether.transport.target_resolve import active_target
        target = active_target(self.server.state)
        matched = target.set_model(name.strip())
        self._send_json(200 if matched else 409, {"model": matched})

    def _handle_send(self):
        """Types a message into the target app from the Mini App's own
        compose box - goes through transport.text.send_text_to_target,
        the exact same staging/presence-deferral/confirm_before_send path
        a real Telegram message takes, not a separate shortcut. In
        particular: if the owner is physically at the keyboard right now,
        this is HELD rather than stealing focus, same as always - sending
        it from a phone doesn't bypass that protection."""
        if self._authorize() is None:
            return
        body = self._read_json_body()
        text = (body or {}).get("text")
        if not text or not isinstance(text, str) or not text.strip():
            self._send_json(400, {"error": "missing_text"})
            return
        text = text.strip()
        if len(text) > MAX_SEND_TEXT_LENGTH:
            self._send_json(400, {"error": "text_too_long"})
            return

        state = self.server.state
        from tether.i18n import make_translator
        _t = make_translator(state.config.settings.language)
        chat_id = state.config.secrets.chat_id
        bot = self.server.bot

        async def notify(msg_text, reply_markup=None):
            return await bot.send_message(chat_id, msg_text, reply_markup=reply_markup)

        from tether.transport.text import send_text_to_target
        future = asyncio.run_coroutine_threadsafe(
            send_text_to_target(state, _t, text, notify), self.server.event_loop,
        )
        try:
            status = future.result(timeout=20)
        except Exception:
            log.warning("mini app: /api/send failed", exc_info=True)
            self._send_json(500, {"error": "send_failed"})
            return

        self._send_json(200, {"status": status})

    def _handle_cmd_stage(self):
        if self._authorize() is None:
            return
        body = self._read_json_body()
        command = (body or {}).get("command")
        if not command or not isinstance(command, str) or not command.strip():
            self._send_json(400, {"error": "missing_command"})
            return
        self.server.state.staged_cmd = command.strip()
        self._send_json(200, {"ok": True})

    def _handle_cmd_cancel(self):
        if self._authorize() is None:
            return
        self.server.state.staged_cmd = None
        self._send_json(200, {"ok": True})

    def _handle_cmd_confirm(self):
        """Executes whatever was staged via /api/cmd/stage - the exact
        same stage-then-confirm shape /cmd already uses over Telegram,
        reusing execute_command (audit log + real run) so a command run
        from either interface is identical and identically logged. Also
        posts the result to the actual Telegram chat, not just returning
        it here - the owner should be able to see in their own chat
        history what ran, when, and from where, regardless of which
        interface triggered it - a command run from the Mini App must
        never be a silent side channel invisible from Telegram."""
        if self._authorize() is None:
            return
        state = self.server.state
        command = state.staged_cmd
        state.staged_cmd = None
        if command is None:
            self._send_json(400, {"error": "nothing_staged"})
            return

        from tether.transport.cmd_exec import execute_command
        future = asyncio.run_coroutine_threadsafe(execute_command(command), self.server.event_loop)
        try:
            ok, output = future.result(timeout=65)
        except Exception:
            log.warning("mini app: /api/cmd/confirm failed", exc_info=True)
            self._send_json(500, {"error": "exec_failed"})
            return

        self._notify_cmd_result(command, ok, output)
        self._send_json(200, {"ok": ok, "output": output})

    def _notify_cmd_result(self, command: str, ok: bool, output: str) -> None:
        import html
        from tether.i18n import make_translator
        state = self.server.state
        _t = make_translator(state.config.settings.language)
        key = "cmd_run_via_miniapp" if ok else "cmd_run_via_miniapp_failed"
        text = _t(key, command=html.escape(command), output=html.escape(output))
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.server.bot.send_message(state.config.secrets.chat_id, text, parse_mode="HTML"),
                self.server.event_loop,
            )
            future.result(timeout=10)
        except Exception:
            log.warning("mini app: failed to post cmd result to telegram", exc_info=True)

    def _handle_transcript(self):
        if self._authorize() is None:
            return
        state = self.server.state
        path = state.tailer_path
        if state.active_target_profile:
            path = state.target_tailer_path
        if path is None:
            self._send_json(200, {"events": []})
            return
        from tether.sources.transcript import read_recent_events
        events = read_recent_events(path, limit=60)
        self._send_json(200, {"events": [
            {
                "type": e.type.value, "timestamp": e.timestamp,
                "text": (e.text or "")[:2000], "tool_name": e.tool_name, "is_error": e.is_error,
            }
            for e in events
        ]})

    def _handle_settings_get(self):
        if self._authorize() is None:
            return
        settings = self.server.state.config.settings
        payload = {"language": settings.language, "output_mode": settings.output_mode}
        for key in BOOL_SETTINGS_KEYS | set(NUMERIC_SETTINGS_KEYS):
            payload[key] = getattr(settings, key)
        self._send_json(200, payload)

    def _handle_settings_post(self):
        if self._authorize() is None:
            return
        body = self._read_json_body()
        if not body or "key" not in body or "value" not in body:
            self._send_json(400, {"error": "malformed_body"})
            return
        key, value = body["key"], body["value"]
        if key not in ALLOWED_SETTINGS_KEYS:
            self._send_json(400, {"error": "unknown_key"})
            return
        settings = self.server.state.config.settings

        if key == "language":
            if value not in ALLOWED_LANGUAGES:
                self._send_json(400, {"error": "invalid_value"})
                return
            settings.language = value
        elif key == "output_mode":
            if value not in ALLOWED_OUTPUT_MODES:
                self._send_json(400, {"error": "invalid_value"})
                return
            settings.output_mode = value
        elif key in BOOL_SETTINGS_KEYS:
            if not isinstance(value, bool):
                self._send_json(400, {"error": "invalid_value"})
                return
            setattr(settings, key, value)
        elif key in NUMERIC_SETTINGS_KEYS:
            lo, hi = NUMERIC_SETTINGS_KEYS[key]
            # isinstance(True, int) is True in Python - excluded explicitly
            # so a stray boolean can't sneak into a numeric field.
            if isinstance(value, bool) or not isinstance(value, int) or not (lo <= value <= hi):
                self._send_json(400, {"error": "invalid_value"})
                return
            setattr(settings, key, value)
        else:
            # Unreachable given the ALLOWED_SETTINGS_KEYS check above,
            # unless a key is added there without a branch here to match -
            # refuse rather than silently no-op-ing and reporting success.
            self._send_json(400, {"error": "unknown_key"})
            return

        settings.save()
        self._send_json(200, {"ok": True})

        if key == "mini_app_enabled":
            # Response is already flushed - only now is it safe to
            # possibly tear this very server down (turning the setting
            # off from inside the Mini App is exactly this case). Done
            # on a fresh thread so this request-handler thread returns
            # immediately rather than blocking on its own server's
            # shutdown().
            server_ref = self.server

            def _apply():
                from tether.miniapp.lifecycle import apply_mini_app_state
                apply_mini_app_state(server_ref.state, server_ref.bot, server_ref.event_loop)

            threading.Thread(target=_apply, daemon=True).start()


def start(state, bot, event_loop) -> MiniAppServer:
    port = state.config.settings.mini_app_local_port
    server = MiniAppServer(("127.0.0.1", port), state, bot, event_loop)
    thread = threading.Thread(target=server.serve_forever, name="miniapp-http", daemon=True)
    thread.start()
    log.info("mini app http server listening on 127.0.0.1:%s", port)
    return server
