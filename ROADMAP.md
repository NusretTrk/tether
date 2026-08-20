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
- Watchdog for tether itself — `watchdog.py` relaunches it if the process
  ever disappears, crash or Task Manager close, deliberate or not.
  `stop_tether`/`start_tether` scripts control both by hand. Confirmed
  live: killed the running process, watched the watchdog bring it back
  within seconds
- `/cmd` confirmation step (it was the one destructive command with none)
  plus a dedicated execution audit log, and a real bug fix found along the
  way — command output was never actually HTML-escaped despite a test file
  claiming it was, because that test only covered a standalone helper and
  never the real code path
- Reading Antigravity's own replies back through Telegram — tails its local
  `transcript.jsonl` (same idea as Claude Code's own transcript, different
  vocabulary) the moment `/target antigravity` is active, prefixed
  `[antigravity]` so it's never confused with the Claude relay. Cursor has
  no equivalent yet — its history lives in an undocumented internal SQLite
  schema, not a plain JSONL, so it's left honestly unbuilt rather than
  reverse-engineered blind
- Model picker OCR search scoped to a region around the click point instead
  of the whole window — an unscoped substring search could otherwise match
  and click unrelated visible text (a file name, a menu label) anywhere
  else in the target app's window
- **Crash-safe state** — `pending_send`, staged messages/photos, staged
  `/cmd`, and a pending `/shutdown` are snapshotted to disk every few
  seconds and restored on the next startup, so a crash or watchdog restart
  mid-flow doesn't just silently drop them. `ask()` was already crash-safe
  before this (its handoff was file-based from the start). Deliberately
  asymmetric: anything that hadn't touched the target window yet comes
  back fully live; a message where Enter was already pressed comes back as
  an honest "couldn't verify delivery" notice instead of faking a
  confirmation a fresh transcript tailer could never actually observe.
- **Telegram Mini App** (optional, off by default) — a Claude-inspired
  mobile-app UI inside Telegram: status (tap the model name for a real
  picker), sessions, a two-way Chat tab, a Command tab reusing `/cmd`'s
  own stage-then-confirm-and-audit flow, and Settings, all themed off the
  active `/target`, backed by the user's own free ngrok static domain.
  `/miniapp link` opens the same app as a bookmarked web page outside
  Telegram entirely (iOS "Add to Home Screen"), authenticated by a
  256-bit bearer token sent as a URL fragment (never reaches any server
  log) instead of Telegram's initData — `/miniapp revoke` kills it
  instantly, the link message self-deletes from chat after 10 minutes.
  Security is app-layer, not URL-secrecy: every request needs a
  Telegram-signed `initData` blob (real HMAC-SHA256, checked for
  freshness and against the one chat_id) or a matching bearer token,
  repeated bad credentials of either kind trip a lockout and a one-time
  alert, concurrent connections are capped and idle ones dropped after
  10s (an internet-facing stdlib server has no built-in limit otherwise —
  confirmed by actually holding a socket open with nothing sent, not
  assumed), the server doesn't advertise its Python version, and the
  ngrok authtoken never touches a command line. The chat menu button is
  kept in sync with actual server state, not the raw setting, so a
  misconfigured "enabled" flag never shows a button pointing at a dead
  URL. `/start` re-syncs it on demand.
- **Customizable everything, first slice** — the Mini App's own settings
  screen now also covers the watcher toggles (dialog/stall/activity/
  app-health), usage-limit auto-continue, clipboard preservation, and
  three numeric thresholds (emergency temp, defer-while-active seconds,
  auto-send-after-idle seconds), all editable live with real bounds
  checking. Window keywords and poll intervals still need config.yaml —
  not everything belongs on a quick toggle screen.

## Next (reliability)

1. **Real macOS/Linux verification** — the window control code is written
   against documented syntax, never run on real hardware. Needs someone
   with a Mac or Linux box to actually try it and report what breaks.

## Then (deeper multi-app control)

2. **Reading Cursor's state** — Antigravity's replies are read back now;
   Cursor's aren't, since its history lives in an undocumented internal
   SQLite schema rather than a plain transcript file.
3. **Customizable everything, the rest** — window keywords, poll
   intervals, and other config.yaml-only fields, if there's a real case
   for editing them remotely rather than at setup time.

## After that (interface)

4. **Voice** — ElevenLabs for output, transcription for input. Interfaces
   already defined in `voice/base.py`, nothing implemented. Telegram has
   no native speech either direction.
5. **Cloud relay + Wake-on-LAN** — a small always-on instance so Telegram
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
