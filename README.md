# tether

**Keep hold of your coding agent when you walk away.**

Tether puts a running Claude Code session on your phone through Telegram:
watch it work in real time, answer the prompts that would otherwise block
it for hours, switch sessions, change model, run commands, grab a file the
agent just wrote, and get told when something finishes, needs you, or hits
a wall.

> Personal-use tool, published as-is. It runs shell commands and controls
> your desktop on your behalf, gated by your Telegram chat ID (and
> optionally a second password on top). Read [DISCLAIMER.md](DISCLAIMER.md)
> before installing.

## Platform support

| | Watch and get notified | Control the app | Session list, dialogs, model/effort |
|---|---|---|---|
| **Windows** | yes | yes | yes |
| **macOS** | yes | basic, unverified | not yet |
| **Linux** | yes | basic, unverified | not yet |

Reading a session works anywhere — it comes from a transcript file on disk,
not the screen. `sys.platform` picks the right code path automatically at
startup; there's nothing to configure and no setup-time question about
which OS you're on.

Driving the app (typing, pressing Enter, taking a screenshot) now has a
real implementation on macOS (`osascript`/System Events) and Linux
(`xdotool`, X11 only — this doesn't work under Wayland). Both are marked
**unverified**: built against documented syntax, never run against a real
Mac or Linux box, because this project is developed on Windows. If you try
it there, an issue with what broke is genuinely useful.

Session list, dialog detection, and the `/model`/`/effort` picker stay
Windows-only — those go through Windows UI Automation, which has no macOS
(Accessibility API) or Linux (AT-SPI) port here yet. They report cleanly
that they're unavailable rather than crashing or guessing.

None of this cross-platform code costs anything on the platform it isn't
for. The macOS and Linux modules are only ever imported when the process
is actually running on that OS — on Windows they sit on disk, unread.

## What it does

- **Live view** — streams what Claude is thinking/doing/replying, read
  straight from Claude Code's own transcript log. Not a screenshot: exact
  text, regardless of scroll position or window layout. Costs nothing extra
  — it's a file tail plus a Telegram API call, no LLM involved.
- **Type from your phone** — send a message, it lands in Claude's input
  box. Confirmed against the transcript (ground truth), not a screenshot
  compare.
- **Route messages elsewhere with `/target`** — plain text can go to Cursor,
  Antigravity, a terminal, or anything with a window, not just Claude
  Desktop; `/model` follows it there too, switching whatever app is
  currently targeted instead of always meaning Claude's model. Reuses the
  same named profiles `/keys` already uses. Lower fidelity than the Claude
  Desktop path on purpose (see below), but confirmed actually working —
  sent real messages into both a live Antigravity and a live Cursor
  window and got real replies back, and switched Antigravity's model
  live and back again, not just assumed any of it. That testing caught
  two real things worth knowing: Cursor doesn't reliably keep its chat
  panel focused (a message can land in its terminal and run as a command
  instead — fixed with a click before every paste), and both apps anchor
  their input box to the bottom of the panel once there's a real
  conversation, not wherever it sits on an empty one — so a coordinate
  calibrated against a fresh panel quietly stops working. Cursor's model
  picker also turned out to be paywalled on a free account; Antigravity's
  wasn't.
- **Reads Antigravity's replies back, too** — `/target antigravity` doesn't
  just send messages into it, it tails Antigravity's own local
  `transcript.jsonl` (same idea as Claude Code's own transcript, different
  vocabulary) and relays its actual answers back through Telegram,
  prefixed `[antigravity]` so it's never confused with the Claude relay
  running in parallel. Cursor doesn't have this yet — its history lives in
  an undocumented internal SQLite schema, not a plain transcript file.
- **Telegram Mini App (optional)** — a real scrollable UI inside Telegram
  (status, sessions, live transcript, settings) instead of nested button
  menus, backed by your own free ngrok tunnel. Off by default; see
  [docs/SETUP.md](docs/SETUP.md) for the one-time setup. The tunnel URL
  itself is never treated as secret — every request has to carry a
  Telegram-signed proof of who's asking, checked against your chat ID, the
  same way everything else in this bot is gated.
- **Crash-safe state** — a pending send, a staged message/photo, a staged
  `/cmd`, or a pending `/shutdown` survive a crash or watchdog restart
  instead of silently vanishing. `ask()` already did (its handoff was
  file-based from the start).
- **Fetch a file with `/files` and `/file`** — the agent writes a `.md`
  file mid-session and you're not at the machine to read it. `/files`
  lists recent ones as tap-to-fetch buttons; `/file <path>` grabs one
  directly. Sandboxed to the active project's own directory.
- **Session list that's actually reliable** — reads Windows' own
  accessibility data, not OCR. Shows Running/Idle status; tap to switch.
- **Start/done notifications** — pings you when a session starts and when
  it goes idle, so you don't have to keep checking. Quiet mode gives you
  exactly that plus questions, nothing else.
- **Dialog/popup alerts** — flags things like a "sign in again" banner
  instead of silently doing nothing while you're away.
- **Answer prompts remotely** — agent tools ask for permission with numbered
  choices or y/n. A keypad sends those keystrokes, so a session blocked on a
  prompt doesn't sit there until you get back to the desk. If a tool call
  goes 90 seconds without a result you get told, with the keypad attached.
- **Usage-limit auto-continue** — reads the actual reset time out of
  Claude's own message ("resets at 3pm", "resets in 2 hours"), and once
  that time passes it automatically sends a message to resume the session
  and tells you it did. Turn it off to only get the "hit the limit"
  notice. Cancels itself cleanly if the session resumes on its own first —
  including via Claude Desktop's own native auto-continue checkbox, which
  ships a similar feature now but doesn't notify you remotely.
- **`/shutdown <minutes>`** — schedules the machine to actually power off,
  confirmed before it runs, with a warning shortly before it fires. `/shutdown
  cancel` aborts it.
- **Model & effort control** — `/model`, `/effort`, or the menu.
- **Real command output** — `/cmd` runs PowerShell and shows you the actual
  output, not just "done."
- **CPU/GPU temperature monitoring** — periodic checks, emergency alerts.
- **Optional second-factor password** — `/unlock <password>` gates
  everything if you set `BOT_PASSWORD`, independent of the chat-id check.
  Off by default; worth turning on if you want protection that doesn't
  depend entirely on your Telegram account never being compromised.
- **4 languages** — English, Turkish, German, Spanish. `/language` to switch.
- **Agents can reach you** — an MCP server exposes `notify` and `ask` so any
  agent can message you, or ask a question and wait for your answer,
  without ever seeing your bot token.

## Quick start

```bash
git clone <your-fork-url> tether
cd tether
pip install -r requirements.txt
python setup.py
```

`setup.py` asks for a bot token (from Telegram's @BotFather), verifies it,
then gives you a link to tap that carries a one-time code — only a reply
containing that exact code is accepted as proof it's really you messaging
the bot, not just whoever happened to message it first. No hunting for IDs,
no editing config files, and no race condition on a freshly created bot.

Then:

```bash
python run.py
```

Message your bot `/start` and you're going.

**Start it automatically at login** (no admin rights needed):

```
install_autostart.bat
```

This runs tether behind a small watchdog that relaunches it if it ever
stops unexpectedly — crash or a Task Manager close, deliberate or not.
`stop_tether.bat` / `start_tether.bat` control both by hand, anytime.

Full instructions, including building a standalone `.exe` and registering
the MCP server: [docs/SETUP.md](docs/SETUP.md).

## Commands

| Command | Does |
|---|---|
| `/menu` | Full inline menu — sessions, screen, system, settings |
| `/sessions` | List sessions with Running/Idle status, tap to switch |
| `/screen <window>` | Screenshot any window by title keyword |
| `/files` | Recent files (.md by default) in the active project, tap to fetch |
| `/file <path>` | Fetch one specific file by path |
| `/target [name]` | Where plain messages go — Claude Desktop, or a named profile (Cursor, Antigravity, a terminal) |
| `/model <fable\|opus\|sonnet\|haiku>` | Switch model (no arg = show current) |
| `/effort <low\|medium\|high\|extra\|max\|ultracode>` | Switch effort |
| `/cmd <command>` | Run a PowerShell command, see real output |
| `/clear` | Clear the input box |
| `/stop` | Stop the current generation |
| `/keys [profile]` | Remote keypad — answer prompts the agent is blocked on |
| `/kill` | Close terminal/emulator/Claude |
| `/restart` | Restart Claude Desktop cleanly, confirmed first |
| `/launch` | Start Claude Desktop if it isn't running |
| `/shutdown <minutes>\|cancel` | Shut down this PC, confirmed first, cancellable |
| `/unlock <password>` / `/lock` | Second-factor gate, if `BOT_PASSWORD` is set |
| `/status` | Current model, effort, temperatures |
| `/language` | Switch language |
| `/mode` | Output verbosity: live / summary / quiet / verbose |
| `/confirm on\|off` | Stage Send/Edit/Cancel before delivering, or send instantly |
| `/miniapp [on\|off]` | Mini App status (actually-running, not just the setting), or turn it on/off directly |
| `/settings` | View and edit runtime settings |

Plain text (not a command) is typed into Claude's input box, or wherever
`/target` currently points.

## How it works

Reading and writing are split, because they have opposite requirements.

- **Reading** goes through Claude Code's own transcript file
  (`~/.claude/projects/.../*.jsonl`, tailed live) and Windows UI Automation
  (session list, status, dialogs). Both are exact and cheap — no
  screenshots, no OCR, no guessing.
- **Writing** — typing a message, picking a model — still drives the real
  window, since Claude Desktop's composer isn't exposed to accessibility
  tools. This is the only part that's pixel-based, and for Claude Desktop
  it's verified against the transcript afterward rather than trusted
  blindly. A message routed via `/target` to a different app skips that
  verification (there's no transcript to check it against) and gets marked
  "sent (not verified)" instead — an honest gap, not a silent one.

Full design rationale: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Configuration

Two files, two purposes:

- **`.env`** — secrets (bot token, chat ID, optional password). Never
  commit this.
- **`config.yaml`** — behavior (intervals, thresholds, language, keypad
  profiles, etc). Copy from `config.example.yaml`; also editable live via
  `/settings`. A bad value falls back to its default with a logged warning,
  not a crash.

## Security

- The bot only responds to the chat ID in your `.env` — every handler
  checks this. Anyone else messaging it gets ignored, silently (replying
  would just confirm the bot exists).
- **Optional second factor**: set `BOT_PASSWORD` in `.env` and everything
  except `/start`, `/unlock`, and `/help` is locked until you send
  `/unlock <password>`. This exists because chat-id whitelisting alone does
  nothing if your own Telegram account gets compromised — whoever's in
  control of it genuinely is the authorized chat id as far as Telegram is
  concerned. Guess attempts are capped (5 per 5 minutes by default) so a
  compromised account can't brute-force a weak password.
- **On encryption**: Telegram's Bot API is encrypted in transit (TLS), but
  it is not end-to-end encrypted the way Telegram's own Secret Chats are —
  that feature is explicitly unavailable for bots, a platform limitation
  tether can't retrofit while keeping messages readable in your normal
  Telegram app. If someone has your Telegram account, they can read the
  chat regardless of transport encryption, the same way you can. The
  password above is the actual defense against that scenario.
- Never commit `.env` or `config.yaml` (both gitignored by default).
- Logs are redacted — a filter strips any bot-token-shaped string before it
  reaches disk, since Telegram puts the token in every outbound request URL.
- If you ever suspect your token leaked, revoke it via `@BotFather` →
  `/revoke` and update `.env`.
- `/cmd` runs shell commands with your account's privileges. This is the
  feature, not a flaw: a remote control that cannot run commands is not a
  remote control. It is gated behind the chat-id check (and the optional
  password) like everything else, and that boundary is covered by tests
  specifically because it is the only thing protecting it.
- `/file` and `/files` are sandboxed to the active project's own directory
  — path traversal, an absolute path elsewhere, and a symlink resolving
  outside that directory are all refused identically, so a probe can't be
  used to learn what exists outside it.
- The keypad only sends keys from a fixed allowlist, checked before the
  window is touched, so a message can never become arbitrary desktop input.
- Unauthorised chats get no reply at all. Answering would confirm the bot
  exists and let a stranger burn the account's rate limit.
- **Mini App, if you turn it on**: the ngrok URL itself is not treated as
  secret — a stranger who finds it gets an empty page and nothing else.
  Every actual API request has to carry either a Telegram-signed `initData`
  blob (verified with the real HMAC-SHA256 algorithm Telegram documents,
  checked for freshness, and checked against your one chat ID — nobody
  without your bot token can forge one) or a bearer token from `/miniapp
  link` (see below). Repeated bad signatures or bad tokens get locked out
  (same mechanism as `/unlock`) and you get a one-time Telegram alert when
  that trips, since it could be a stranger who found the URL rather than
  you. A locked `BOT_PASSWORD` blocks both credential types the same way.
  Concurrent connections are capped and idle ones are dropped after 10s,
  since an internet-reachable server with no limit is a resource-exhaustion
  target — this was found by actually opening a socket and never sending
  anything, not assumed. The server doesn't advertise its Python version.
  The ngrok authtoken never appears on a command line (visible via Task
  Manager) — it's handed to the subprocess through its own environment.
- **Opening the Mini App outside Telegram (`/miniapp link`)**: there's no
  Telegram session to sign anything when the app is opened as a bookmarked
  web page (iOS "Add to Home Screen") instead of launched from Telegram
  itself, so this needs its own credential. `/miniapp link` issues a
  random 256-bit token and sends it as a URL *fragment*
  (`https://yourdomain/#t=...`) — fragments are never sent to any server by
  the browser, so this token never touches ngrok's logs or tether's own.
  Only its SHA-256 hash is ever written to disk (`state/web_token.json`,
  gitignored). `/miniapp revoke` invalidates it instantly, and the link
  message deletes itself from the chat after 10 minutes regardless, since
  it's a live credential sitting in plain text. Treat that link exactly
  like a password — anyone who gets it has the same access you do.

## What's not built yet

Scoped out on purpose, not forgotten:

- **Reading Cursor's state** — Antigravity's replies are read back now
  (see above); Cursor's aren't, since its history lives in an undocumented
  internal SQLite schema rather than a plain transcript file.
- **Real macOS/Linux verification** — the window-control code there is
  written against documented syntax, never run on real hardware.
- **Voice** — interfaces are defined (`tether/voice/base.py`) for future
  ElevenLabs integration, not implemented.
- **Remote MCP/skill editing.**
- **Cloud relay / Wake-on-LAN** — Telegram still needs the PC actually
  running; there's no always-on relay that queues commands or wakes it.

## Development

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

427 tests, almost all GUI-independent — they run on any machine, no Claude
window or Windows accessibility stack required. (One skips without
elevated/developer-mode permissions to create a symlink, which a couple of
the file-security tests need.)

## License

MIT — see [LICENSE](LICENSE). Please also read
[DISCLAIMER.md](DISCLAIMER.md).
