# Tether — Remote Agent Control: Design Spec

**Date:** 2026-08-18
**Status:** Approved for implementation (Phases 1–3)
**Supersedes:** ad-hoc `bot.py` / `claude_kontrol.py`

> **Name:** working title `tether` (a tether to your PC). Rename freely before publishing —
> it appears only in the folder name, package name, and README.

---

## 1. Problem

The existing bot (`bot.py`, 1049 lines, single file) drives Claude Desktop entirely by
screenshotting the window and running OCR over the pixels. Everything is derived from
what is visually on screen. This produces a standing set of failures:

| Symptom | Root cause |
|---|---|
| Text won't paste when the right panel (browser / md viewer) is open | Layout shifts; OCR anchor and click coordinates go stale |
| Proof screenshot captures the wrong region / only part of the text | Crop is computed from guessed pixel ratios |
| Long or scrolled-up output can't be read | Only the visible viewport is captured |
| `/cmd` output never reaches Telegram | Output is only ever rendered into the app window, never read back |
| Session switching is flaky | Session list parsed from OCR line-gap heuristics |
| Silent death when a modal/banner appears | Nothing detects dialogs |
| High idle cost | Screenshot + Tesseract loop on a timer |

Secondary problems: the bot token is hardcoded in **two** source files, present in a
**third** location (a private memory file), and appears in **23,851 log lines across
4.2 MB** of logs — blocking publication. There is no settings system, no i18n, and no
way to change behaviour without editing source.

## 2. Key discoveries (validated, not assumed)

These were tested live against the running Claude Desktop instance before writing this spec.

1. **Claude Code writes a complete live transcript to disk.**
   `~/.claude/projects/<project-slug>/<session-id>.jsonl` is appended in real time —
   verified with a file whose mtime was 1 second old. It contains every user message,
   assistant message, thinking block, tool call, and tool result (including shell output).
   Reading it is effectively free.

2. **Windows UI Automation exposes Claude Desktop's sidebar as structured data.**
   Session names *and* live status are readable as named controls, e.g.
   `'Running Telegram PC control bot with window capture'`,
   `'Idle HalallO architecture audit and execution plan'`.
   Popups/banners are likewise addressable by name (`'Sign in again'`).

3. **UIA requires a warm-up query.** Chromium builds its accessibility tree lazily on
   first assistive-tech request. First walk returned **23** nodes; an immediate second
   walk returned **249**. Any implementation must query, wait, and re-query.

4. **UIA does NOT reach the chat area or composer.** The main content renderer stays
   unpopulated (zero-size `DocumentControl`s) even after warm-up. Typing and the
   model/effort picker must remain pixel-driven.

5. **Bot API 10.1 added Rich Messages** (`sendRichMessageDraft`) explicitly for streaming
   partial AI replies. **python-telegram-bot 22.8 (latest) only supports API 10.0**, so it
   is not available yet. API 9.4 added inline-button `style` (colour) and
   `icon_custom_emoji_id`.

6. **Telegram has no native TTS/transcription.** Voice features require an external
   provider (ElevenLabs for output; a transcription service for input).

## 3. Architecture: split reading from writing

The central decision. Reading and writing have opposite requirements, so they use
different mechanisms.

```
                 ┌──────────────────────────────────────┐
   READ PATH     │  transcript .jsonl  (tail, live)     │ ← messages, thinking,
   (perfect,     │  UIA sidebar        (poll, cheap)    │   tool calls, cmd output,
    ~free)       │  UIA dialogs        (poll, cheap)    │   session list + status
                 └──────────────────────────────────────┘
                                   │
                          normalized Event stream
                                   │
                 ┌──────────────────────────────────────┐
                 │        Telegram transport            │
                 └──────────────────────────────────────┘
                                   │
   WRITE PATH    ┌──────────────────────────────────────┐
   (occasional,  │  focus window → type → send          │ ← the ONLY pixel-driven
    contained)   │  model / effort picker               │   surface that remains
                 └──────────────────────────────────────┘
                                   │
                        verify via READ PATH
```

**Consequences:**

- OCR shrinks from "the entire system" to two narrow jobs: typing and the model dropdown.
- Send-confirmation is verified by watching the transcript for the message to appear —
  **ground truth**, replacing the screenshot-compare heuristic that misfires today.
- Screenshots become an explicit user-requested *feature*, not the reading mechanism.
- Idle cost collapses: tailing a file + a slow UIA poll, instead of a screenshot/OCR loop.

### 3.1 Target adapter interface

Multi-IDE support (Phase 5) is not built now, but the seam is defined now so it costs
nothing later. Cursor, VS Code, and Antigravity are all Electron/Chromium, so the same
UIA + transcript techniques apply.

```python
class Target(Protocol):
    name: str
    def is_available(self) -> bool: ...
    def focus(self) -> bool: ...
    def send_text(self, text: str) -> SendResult: ...
    def list_sessions(self) -> list[Session]: ...      # UIA
    def switch_session(self, session_id: str) -> bool: ...
    def read_status(self) -> TargetStatus: ...          # model, effort, running/idle
    def set_model(self, model: str) -> bool: ...
    def set_effort(self, level: str) -> bool: ...
    def detect_dialogs(self) -> list[Dialog]: ...       # UIA
    def transcript_source(self) -> TranscriptSource | None: ...
```

Phase 3 ships exactly one implementation: `ClaudeDesktopTarget`.

## 4. Repository layout

New clean folder, git-ready. The old files are **left untouched** during migration and
removed only after the new one is confirmed working.

```
tether/
├── .env.example              # documented, no real values
├── .gitignore                # .env, *.log, __pycache__, screenshots
├── README.md                 # what it is, setup, commands, screenshots
├── LICENSE                   # MIT (see §11)
├── requirements.txt
├── run.py                    # entry point
├── config.example.yaml       # user-editable runtime settings
├── src/tether/
│   ├── config.py             # .env + YAML, validation, live reload
│   ├── events.py             # normalized Event model
│   ├── i18n/
│   │   ├── __init__.py       # loader, fallback chain
│   │   ├── en.json  tr.json  de.json  es.json
│   ├── transport/
│   │   ├── bot.py            # handlers, wiring
│   │   ├── menus.py          # inline keyboards, menu tree
│   │   ├── streaming.py      # throttled edit; rich-draft seam
│   │   └── formatting.py     # chunking, code blocks, truncation
│   ├── sources/
│   │   ├── transcript.py     # JSONL tail + parse
│   │   └── discovery.py      # locate active session file
│   ├── targets/
│   │   ├── base.py           # Target protocol
│   │   ├── claude_desktop.py
│   │   └── registry.py
│   ├── platform/
│   │   ├── window.py         # find/focus/capture (from bot.py)
│   │   ├── uia.py            # UIA + warm-up handling
│   │   └── ocr.py            # contained OCR helpers
│   ├── monitors/
│   │   ├── temps.py          # CPU (ATKACPI) + GPU (nvidia-smi)
│   │   ├── dialogs.py        # popup watcher
│   │   └── activity.py       # running/idle → done-notification
│   ├── mcp/
│   │   └── server.py         # notify / ask tools
│   └── voice/                # Phase 6 seam — interfaces only, no impl
│       └── base.py
├── tools/
│   ├── notify.py             # CLI fallback for non-MCP agents
│   └── scrub_logs.py         # one-shot token redaction for old logs
└── docs/
    ├── SETUP.md              # bot creation walkthrough
    └── ARCHITECTURE.md
```

**Module size rule:** if a file passes ~300 lines, split it. The 1049-line monolith is a
primary cause of the current bug density.

## 5. Phase 1 — Foundation & publishable repo

### 5.1 Secrets

- `BOT_TOKEN`, `CHAT_ID` move to `.env`, loaded via `python-dotenv`.
- **The user's existing values are carried over verbatim** — nothing to re-obtain.
- `.env` is gitignored; `.env.example` ships with placeholders and comments.
- Startup fails fast with a clear, actionable message if `.env` is missing/incomplete.

### 5.2 Log redaction (mandatory)

Telegram places the token in the URL path, so every HTTP log line leaks it.

- A `logging.Filter` regex-replaces `bot<digits>:<token>` with `bot***REDACTED***` on
  every record, before it reaches any handler.
- `tools/scrub_logs.py` rewrites the existing 4.2 MB of logs in place.
- Rotating file handler retained (2 MB × 3).

**Post-implementation user action:** revoke the token via `@BotFather` → `/revoke`, then
put the new one in `.env`. Required — the current token has appeared in logs, in two
source files, in a memory file, and in chat transcripts. Also update
`~/.claude/projects/C--dev-Repertu/memory/repertu-telegram-notify.md`, which contains it.

### 5.3 Settings system

Two tiers:

- **Secrets** → `.env` (never committed).
- **Behaviour** → `config.yaml` (committed as `config.example.yaml`), covering intervals,
  thresholds, language, confirmation mode, output mode, window keywords, feature flags.

Editable at runtime from Telegram (`/settings`), written back to `config.yaml`, applied
without restart. Every value validated on load with a typed schema; invalid values log a
warning and fall back to the documented default rather than crashing.

### 5.4 i18n

- JSON catalogues keyed by string ID; `t("key", **params)`.
- Ships **English, Turkish, German, Spanish**. English is the fallback for any missing key.
- `/language` presents an inline keyboard; choice persists to `config.yaml`.
- **All existing Turkish strings move into `tr.json`** — no user-facing literals remain in
  code. A test asserts every key present in `en.json` exists in all other catalogues.

### 5.5 Docs

- `README.md`: what it does, screenshots, feature list, install, security note, licence.
- `docs/SETUP.md`: the BotFather walkthrough (adapted from the user's existing text),
  getting a chat ID, `.env` setup, running, autostart, and MCP registration.
- `requirements.txt` pinned to known-good versions.

## 6. Phase 2 — Read through the transcript

### 6.1 Transcript source

- Locate the active session `.jsonl` under `~/.claude/projects/<slug>/`.
- Slug derivation is Claude Code's own path-mangling scheme; discovery picks the
  most-recently-modified file for the target project and re-checks periodically so a
  session switch is picked up.
- Tail incrementally by byte offset — never re-read the file (they reach 50 MB+).
- Parse each line into a normalized `Event`:
  `UserMessage | AssistantText | Thinking | ToolCall | ToolResult | Error | SessionEnd`
- Malformed/partial trailing lines (mid-write) are tolerated: retry on next poll.
- Poll interval configurable, default 1 s. Cost is a `seek` + short read.

### 6.2 What this delivers

| Feature | Mechanism |
|---|---|
| Live "watch it think" | `Thinking` + `AssistantText` events streamed |
| Real `/cmd` output | `ToolResult` events carry full stdout/stderr |
| Complete text, never truncated by scroll | Read from file, not viewport |
| Send confirmation | Wait for matching `UserMessage` to appear |
| Usage-limit detection | Error events — replaces OCR keyword matching |
| Token/cost reporting | Aggregated from transcript metadata |

### 6.3 Streaming to Telegram

- **Now:** accumulate into a buffer, `edit_message_text` on a throttle (default 2.5 s,
  configurable) — well inside rate limits. Final edit on completion.
- **Seam:** `Streamer` interface with `ThrottledEditStreamer` as the only implementation.
  When PTB exposes `sendRichMessageDraft`, add `RichDraftStreamer` and feature-detect.
  No other code changes.
- Long output is chunked at Telegram's 4096-char limit on line boundaries; code blocks
  are fenced and language-tagged; very long tool results are truncated with a
  "show full" button that sends the remainder as a file.

### 6.4 Output modes

`/mode` — controls how much reaches the phone:

- `live` — stream thinking + text as it happens
- `summary` (default) — final assistant messages only
- `quiet` — nothing unless it's an alert, a question, or you ask
- `verbose` — everything including tool calls and results

### 6.5 Confirmation toggle

`/confirm on|off`. When on, a message is staged with **Send / Edit / Cancel** inline
buttons before delivery. When off, it sends immediately.

Default: **on**, preserving today's behaviour. A refactor should not silently change a
UX default the user deliberately built. The argument for `off` is that confirmation
existed to compensate for unreliable pasting, which transcript verification now solves —
but that is the user's call to make with one command, not ours to make by default.

## 7. Phase 3 — Accessibility: sessions, status, dialogs

### 7.1 UIA layer

- `platform/uia.py` wraps `uiautomation` with the **warm-up protocol**: query, brief
  sleep, re-query, and only then trust the tree. Node count is compared to catch a
  still-dormant tree, with bounded retries.
- All UIA work runs in a worker thread — the library is COM-based and blocking; it must
  never block the asyncio loop.
- Results cached with a short TTL so repeated queries don't re-walk the tree.

### 7.2 Sessions

- `list_sessions()` reads sidebar buttons, parsing the `"<Status> <Name>"` convention
  observed live (`Running …` / `Idle …`).
- `/sessions` renders an **inline keyboard, one button per session**, status shown with a
  leading emoji. Tapping switches — no more `/switch 3` index-counting.
- Falls back to the existing OCR path if UIA returns an implausible tree, so a Claude
  Desktop UI change degrades rather than breaks.

### 7.3 Done-notification (new)

`monitors/activity.py` watches session status transitions. On `Running → Idle`, it pushes
*"✅ &lt;session&gt; finished"*. This is the single highest-value addition — the user
currently has no way to know a long task completed without polling manually.

Debounced so brief flickers don't spam.

### 7.4 Dialog / roadblock watcher (new)

Polls UIA for dialogs, modals, and banners by name. On a new one:

- Push a notification naming the dialog and its buttons.
- Offer inline buttons to click a **safe** action.
- **Safety rule:** only buttons on an explicit allowlist may be auto-clicked
  (e.g. `Relaunch to update` is *not* auto-clicked; nothing destructive is ever
  auto-clicked). Anything else is reported for a human decision. Authentication prompts
  are **always** reported, never actioned — the bot must not touch sign-in flows.

The live example that motivated this: a `For your security, sign in again to keep using
Claude.` banner with a `Sign in again` button was present on the user's machine during
design, and today's bot would have gone silent with no explanation.

## 8. UX redesign

Replacing a flat list of a dozen slash commands.

### 8.1 Structure

- **Persistent reply keyboard** — 4–6 highest-frequency actions only:
  `📊 Status` `📸 Screen` `⏹ Stop` `📋 Sessions` `⚙️ Menu`
- **`/menu`** — inline keyboard, grouped, with back-navigation:
  - *Session* — sessions, switch, new, stop, clear
  - *Screen* — screenshot (window / region / full), model, effort
  - *System* — temps, shell, processes
  - *Settings* — language, mode, confirm, intervals
- **Contextual buttons** attached to the message they concern (e.g. a staged message
  carries Send/Edit/Cancel; a long result carries "show full").
- **Slash commands remain** as power-user shortcuts and stay registered via
  `setMyCommands` so `/` autocompletes.

### 8.2 Command changes

| Old | New | Why |
|---|---|---|
| `/switch <n>` | tap a session button | no index counting |
| `/screenshot <kw>` | `/screen` + target buttons | discoverable |
| `/killterm`,`/killemulator`,`/killclaude` | `/kill` + buttons | 3 commands → 1 |
| `/cmd <c>` | unchanged (+ real output) | already good |
| — | `/menu` `/settings` `/language` `/mode` `/confirm` `/status` `/ask` | new |

### 8.3 Styling

Bot API 9.4 button `style` (colour) and `icon_custom_emoji_id` are used **only if the
runtime reports support**, degrading silently to plain buttons. No hard dependency.

## 9. MCP server — replacing the secret URL

Today, agents are handed a raw `https://api.telegram.org/bot<TOKEN>/sendMessage` URL
stored in a private memory file. It embeds a credential, can't be published, and must be
re-taught to every agent.

**Replacement: an MCP server exposing two tools.**

| Tool | Behaviour |
|---|---|
| `notify(message, level?)` | Push a message to the user. Returns immediately. |
| `ask(question, options?, timeout?)` | Push a question **and block until the user replies**, returning their answer. |

- Token is read from `.env` by the server; **agents never see a credential**.
- Registered with one documented command; works identically for anyone who clones the repo.
- `ask` is the direct implementation of the "no roadblocks" requirement: an agent hitting
  a decision point asks and waits, instead of stalling until the user returns.
- `tools/notify.py` provides the same push for non-MCP consumers (plain scripts, cron,
  opencode) — reads the same `.env`, no secrets on the command line.

Timeouts on `ask` are bounded and configurable; on timeout it returns a documented
sentinel so a waiting agent fails predictably rather than hanging forever.

## 10. Voice (Phase 6 — seam only, not built now)

Not implemented in this spec. Interfaces defined so it drops in without refactoring:

```python
class SpeechOut(Protocol):      # ElevenLabs impl later
    def synthesize(self, text: str) -> bytes: ...
class SpeechIn(Protocol):       # transcription impl later
    def transcribe(self, audio: bytes) -> str: ...
```

Planned shape: assistant replies optionally delivered as Telegram voice messages;
inbound voice notes transcribed and sent to the agent. `ELEVENLABS_API_KEY` is listed in
`.env.example` as optional and commented out. Telegram has no native TTS/transcription,
so both directions require an external provider.

## 11. Publishing

- **Licence:** MIT — permissive, standard, keeps future commercial options open.
- **No secrets in any tracked file**; `.gitignore` covers `.env`, `*.log`, `*.png`.
- README documents the security model explicitly: the bot executes shell commands and
  controls the desktop, so it must only ever be paired with the operator's own chat ID.
  `CHAT_ID` allowlisting is retained and enforced on every handler.
- A note that this is a personal-use tool, not a hardened multi-tenant service.

## 12. Non-goals (explicitly out of scope)

- Web dashboard / Mini App — deferred; would require exposing the machine.
- Multi-user or multi-tenant support.
- Multi-IDE targets (Cursor / Antigravity / VS Code) — Phase 5; only the interface lands now.
- Terminal-agent control (opencode) — Phase 5.
- Remote editing of MCP configs and skills — Phase 6.
- Headless `claude -p` session spawning — possible later; the Target interface allows it.

## 13. Testing

- **Unit, no GUI:** transcript parsing (incl. malformed lines, partial writes, rotation),
  event normalization, i18n completeness, config validation/fallback, log redaction,
  message chunking.
- **Fixtures:** a recorded `.jsonl` sample drives transcript tests with no Claude running.
- **Integration, guarded:** UIA and window tests skip cleanly when no target window exists,
  so the suite passes on CI and on a fresh clone.
- **Manual checklist** in `docs/`: send/receive, panel-open paste, session switch,
  done-notification, dialog alert, `/cmd` output, language switch, streaming.

Every fix in §1 gets a regression test where it is testable without a GUI.

## 14. Risks

| Risk | Mitigation |
|---|---|
| Claude Code changes transcript format | Parser tolerates unknown event types; falls back to raw text; version-sniffed |
| Claude Desktop UI change breaks UIA names | OCR fallback retained for sessions; failures reported, not silent |
| UIA warm-up flaky under load | Bounded retries + node-count sanity check + cached last-good result |
| Transcript path scheme changes | Discovery by newest-mtime rather than hardcoded slug |
| Token still leaked somewhere | Redaction filter is global; scrub tool for history; revoke is a required step |
| Blocking COM calls stall the bot | All UIA/OCR work confined to a worker thread |

## 15. Migration

1. Build `tether/` alongside the existing files — **nothing deleted**.
2. Run both; verify feature parity against the manual checklist.
3. Scrub logs, revoke token, update `.env` and the Repertu memory file.
4. Only then archive `bot.py` / `claude_kontrol.py` into `legacy/` (or delete once the
   user confirms).
5. Update the autostart scheduled task to point at `run.py`.

## 16. Success criteria

- [ ] No secret in any tracked file; logs redacted; token revoked and replaced
- [ ] Paste works with the right-hand panel open
- [ ] `/cmd` returns real output to Telegram
- [ ] Full message text available regardless of scroll position
- [ ] Live streaming of thinking/replies, mode-switchable
- [ ] Confirmation toggleable; when on, verified against transcript
- [ ] Session list + switch via buttons, backed by UIA
- [ ] Notification when a session finishes
- [ ] Notification when a dialog/banner blocks progress
- [ ] `/language` switches all user-facing strings
- [ ] Agents can `notify` and `ask` with no credential exposure
- [ ] Idle CPU measurably below the current screenshot/OCR loop
- [ ] Repo is clone-and-run for a stranger, following README only
