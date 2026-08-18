# Architecture

Full design rationale, discovery notes, and decision log:
[docs/superpowers/specs/2026-08-18-tether-remote-agent-control-design.md](superpowers/specs/2026-08-18-tether-remote-agent-control-design.md).
This file is a short map of the code; read the spec for *why*.

## The split: reading vs. writing

```
READ (exact, cheap)          WRITE (pixel-driven, verified after)
  transcript .jsonl  ──┐        window focus/click/type
  UIA sidebar         ─┼──►     model/effort picker
  UIA dialogs         ─┘             │
         │                           ▼
         └──────────────►  confirmed against the READ path
```

Claude Code writes a live transcript to
`~/.claude/projects/<slug>/<session>.jsonl`. Tailing it gives exact message
text, tool calls, and tool output — no OCR, no scroll-position limits.
Windows UI Automation exposes the sidebar (session names, Running/Idle
status) and dialogs/banners as structured data, once "warmed up" (Chromium
builds its accessibility tree lazily on first query — see
`platform/uia.py::warm_up`).

The composer and model picker are **not** in the accessibility tree
(verified live, not assumed), so typing and model/effort switching stay
pixel-driven — the only OCR left in the system. Every write is verified
afterward through the read path: a sent message is confirmed by watching
for it to appear in the transcript, not by re-screenshotting the input box.

## Module map

```
src/tether/
├── config.py          .env + config.yaml, validated with fallback
├── events.py           Transcript line → normalized Event
├── i18n/                en/tr/de/es catalogues + loader
├── logsetup.py          Rotating logs + mandatory token redaction
├── sources/
│   ├── discovery.py     Finds the active transcript (newest mtime)
│   └── transcript.py    Byte-precise incremental tailer
├── platform/
│   ├── window.py         Find/focus/capture (Win32)
│   ├── ocr.py             Tesseract, scoped to composer + model picker
│   ├── uia.py             UI Automation wrapper + warm-up protocol
│   └── shell.py           PowerShell execution for /cmd
├── targets/
│   ├── base.py            Target protocol (seam for other IDEs later)
│   ├── claude_desktop.py  The one implementation that ships
│   └── registry.py
├── monitors/
│   ├── temps.py           CPU (ATKACPI) + GPU (nvidia-smi)
│   ├── activity.py        Running→Idle transition watcher
│   └── dialogs.py         Popup/banner watcher (detect-only, never clicks)
├── mcp/
│   ├── server.py          notify/ask tools
│   └── shared_state.py    File handoff for ask() (see below)
├── transport/
│   ├── bot.py              App wiring, handler + job registration
│   ├── handlers.py         Command handlers
│   ├── callbacks.py        Inline-button dispatcher
│   ├── text.py              Plain-message routing (send / stage / MCP answer)
│   ├── menus.py              Inline keyboard builders
│   ├── jobs.py                Background jobs (transcript, temps, watchers)
│   ├── streaming.py            Throttled-edit streamer (+ rich-draft seam)
│   ├── formatting.py            Chunking for Telegram's 4096-char limit
│   └── state.py                  AppState — all mutable runtime state
└── voice/base.py         Future ElevenLabs seam, not implemented
```

## Why `ask()` needs a file handoff

Telegram's `getUpdates` (receiving messages) allows only **one** active
long-poll connection per bot token. The main bot already holds it. The MCP
server runs as a separate process (spawned by whatever agent registered it)
and can't also poll — so `ask()` writes a pending-question file, and the
main bot's text handler checks for one on every incoming message, routing
the reply back through an answer file instead of a second polling
connection. `notify()` has no such problem — sending is a stateless HTTP
call, any number of processes can do it concurrently.

## Threading

UI Automation and window/OCR calls are blocking, COM-based, or both. They
must never run directly on the asyncio event loop — every call site uses
`asyncio.to_thread`. Grep for `to_thread` in `transport/` to see every
crossing point.

## Known simplifications (by design, not oversight)

- **Dialog detection is heuristic** — Claude Desktop's popups aren't a
  distinct UIA region, so `detect_dialogs` matches trigger keywords in
  visible text rather than a precise dialog boundary. It only ever reports;
  nothing is auto-clicked (see spec §7.4 for the safety rule).
- **Live/verbose transcript granularity is per-block, not per-token** —
  Claude Code appears to write complete thinking/text/tool blocks rather
  than incremental deltas, so "live" mode shows each block within about a
  second of it landing, not a token-by-token typewriter effect.
- **Rich Messages** (Bot API 10.1's `sendRichMessageDraft`, built for
  exactly this streaming use case) aren't used — python-telegram-bot 22.8
  doesn't expose them yet. `streaming.py::has_rich_message_draft` is the
  single switch point for adding it later.
