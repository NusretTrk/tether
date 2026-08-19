# Roadmap

Everything asked for, in the order it's getting built. Nothing here is
forgotten — if it's not done, it's below with a reason.

## Done

- Transcript-based reading (no OCR for content)
- Session list + switch via accessibility tree, Running/Idle status
- Start/done notifications, dialog/popup alerts, stall detection
- Remote keypad, bare-key shortcuts, per-app keypad profiles
- Photo send, photo + caption in one message
- Model / effort control
- `/cmd` with real output, HTML-escaped
- 4 languages, runtime settings, log redaction
- App lifecycle: `/restart`, `/launch`, health watcher, path-safe kill
- Security: chat-id gate, optional `BOT_PASSWORD` second factor with a
  capped-attempts lockout, key allowlist, structural regression tests
- Focus-safe sending — messages queue instead of stealing focus while
  the user is actively at the keyboard (`GetLastInputInfo`)
- Clipboard preservation around every paste (Windows; text only)
- Self-healing — health watcher auto-recovers the safe case (app died
  while nobody was at the keyboard), hard attempt cap so it can't loop
- Usage-limit auto-continue — parses the actual reset time out of
  Claude's own message, resumes automatically after it, cancels itself
  cleanly if the session recovers first (including via Claude Desktop's
  own native auto-continue checkbox)
- `/shutdown <minutes>|cancel` — confirmed, cancellable, warns before firing
- `/files` and `/file <path>` — fetch a file the agent wrote, sandboxed
  to the active project's own directory
- `/target` — route plain messages to Cursor/Antigravity/a terminal/any
  window instead of Claude Desktop, via the existing keypad_profiles
  config, with an optional `input_click` for apps that don't auto-focus
  their input panel (confirmed necessary and working live, not assumed,
  against a real Antigravity window)
- Basic macOS/Linux window control (find/focus/type/screenshot) —
  unverified on real hardware, developed on Windows only
- Idle backoff — UIA polling (session list, dialogs) skips entirely once
  the app is confirmed not running, instead of polling every 3s regardless

## Next (reliability)

1. **Watchdog for tether itself** — nothing notices if the bot process
   dies. Last remaining single point of failure.
2. **Crash-safe state** — `pending_send`, staged photos, and pending
   `ask()` all live in memory; a restart mid-flow loses them.
3. **Real macOS/Linux verification** — the window control code is written
   against documented syntax, never run on real hardware. Needs someone
   with a Mac or Linux box to actually try it and report what breaks.

## Then (deeper multi-app control)

4. **Reading Cursor/Antigravity state** — `/target` covers typing and
   sending now; reading their session/state doesn't exist, since that
   needs each app's own accessibility surface rather than window
   automation, the same gap that keeps macOS/Linux at "basic" control.
5. **Customizable everything** — more settings editable from Telegram
   rather than config.yaml + restart. Keypad profiles (and now target
   profiles) exist as the pattern; extend it to window keywords,
   intervals, thresholds, watcher toggles.

## After that (interface)

6. **Telegram Mini App** — real UI inside Telegram: scrollable transcript,
   session list, settings forms instead of nested button menus. Needs free
   static hosting plus a tunnel to reach the PC.
7. **Voice** — ElevenLabs for output, transcription for input. Interfaces
   already defined in `voice/base.py`, nothing implemented. Telegram has
   no native speech either direction.
8. **Cloud relay + Wake-on-LAN** — a small always-on instance so Telegram
   still answers when the PC is off: reports offline, queues commands, can
   wake the machine. Constraint: only one process may poll a bot token, so
   the relay has to own polling and forward to the PC rather than run
   alongside it.

## Deliberately not doing

- **Auto-clicking dialogs.** Detection reports only. Auto-clicking
  something like a sign-in prompt or an installer is how a helper becomes a
  liability.
- **Auto-restart without limits.** Any self-healing gets an attempt cap.
  A restart loop fighting a real problem is worse than staying down.
- **Faking end-to-end encryption.** Telegram's Bot API doesn't support it;
  encrypting message bodies while still needing them readable in a normal
  Telegram client isn't a real option, so this stays honestly out of scope
  rather than half-implemented.
