# Roadmap

Everything asked for, in the order it's getting built. Nothing here is
forgotten — if it's not done, it's below with a reason.

## Done

- Transcript-based reading (no OCR for content)
- Session list + switch via accessibility tree, Running/Idle status
- Done-notifications, dialog/popup alerts, stall detection
- Remote keypad, bare-key shortcuts, per-app keypad profiles
- Photo send, photo + caption in one message
- Model / effort control
- `/cmd` with real output, HTML-escaped
- 4 languages, runtime settings, log redaction
- Cross-platform degradation (monitoring works everywhere)
- App lifecycle: `/restart`, `/launch`, health watcher, path-safe kill
- Security: chat-id gate, key allowlist, structural regression tests

## Next (reliability first)

These come first because none of the exciting features matter if the core
drops work.

1. **Don't steal focus while you're typing** — `GetLastInputInfo` gives
   idle time. If the user is actively at the keyboard, queue the send
   rather than yanking focus mid-sentence.
2. **Clipboard preservation** — every paste currently clobbers whatever
   the user had copied. Save and restore around it.
3. **Self-healing** — health watcher currently only reports. Auto-recover
   the safe cases (app died with nothing running) with hard attempt limits
   so it can't loop.
4. **Watchdog for tether itself** — nothing notices if the bot dies. Last
   remaining single point of failure.
5. **Crash-safe state** — `pending_send`, staged photos, and pending
   `ask()` all live in memory; a restart mid-flow loses them.

## Then (multi-app control)

6. **Cursor / Antigravity / VS Code as full targets** — keypad profiles
   already send keys to them. Missing: typing into them, and reading their
   state. Needs `stage_text` to accept a window target instead of being
   bound to Claude Desktop.
7. **Claude Code in a terminal** — worth noting this is *closer than it
   looks*: the CLI writes the same `~/.claude/projects/*.jsonl` transcripts
   as the desktop app, and discovery already picks the newest across all
   projects. Reading a terminal session may already work; only the typing
   target needs redirecting.
8. **Customizable everything** — more settings editable from Telegram
   rather than config.yaml + restart. Keypad profiles exist; extend the
   same pattern to window keywords, intervals, thresholds, watcher toggles.

## After that (interface)

9. **Telegram Mini App** — real UI inside Telegram: scrollable transcript,
   session list, settings forms instead of nested button menus. Needs free
   static hosting plus a tunnel to reach the PC.
10. **Voice** — ElevenLabs for output, transcription for input. Interfaces
    already defined in `voice/base.py`, nothing implemented. Telegram has
    no native speech either direction.
11. **Cloud relay + Wake-on-LAN** — a small always-on instance so Telegram
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

## Open, needs a decision

- **GitHub push** — still not pushed. Needs a repo name and public/private
  from the user.
