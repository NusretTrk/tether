# tether

Remote control and monitoring for Claude Desktop on Windows, from Telegram.
Watch it work, type into it, switch sessions, get pinged when a task
finishes or something needs your attention — all from your phone.

> Personal-use tool. It executes shell commands and controls your desktop on
> your behalf. Only ever pair it with your own Telegram chat ID (enforced —
> see [Security](#security)).

## What it does

- **Live view** — streams what Claude is thinking/doing/replying, read
  straight from Claude Code's own transcript log. Not a screenshot: exact
  text, regardless of scroll position or window layout.
- **Type from your phone** — send a message, it lands in Claude's input box.
  Confirmed against the transcript (ground truth), not a screenshot compare.
- **Session list that's actually reliable** — reads Windows' own
  accessibility data, not OCR. Shows Running/Idle status; tap to switch.
- **Done-notifications** — pings you when a running session goes idle, so
  you don't have to keep checking.
- **Dialog/popup alerts** — flags things like a "sign in again" banner
  instead of silently doing nothing while you're away.
- **Model & effort control** — `/model`, `/effort`, or the menu.
- **Real command output** — `/cmd` runs PowerShell and shows you the actual
  output, not just "done."
- **CPU/GPU temperature monitoring** — periodic checks, emergency alerts.
- **4 languages** — English, Turkish, German, Spanish. `/language` to switch.
- **Agents can reach you** — an MCP server exposes `notify` and `ask` so any
  agent (this one included) can message you, or ask a question and wait for
  your answer, without ever seeing your bot token.

## Quick start

1. **Clone and install:**
   ```bash
   git clone <your-fork-url> tether
   cd tether
   pip install -r requirements.txt
   ```
2. **Get a bot token and chat ID** — see [docs/SETUP.md](docs/SETUP.md), takes
   about 2 minutes.
3. **Configure:**
   ```bash
   cp .env.example .env
   # edit .env: paste your BOT_TOKEN and CHAT_ID
   ```
4. **Run:**
   ```bash
   python run.py
   ```
5. Message your bot `/start` on Telegram.

Optional: register the MCP server so agents can notify/ask you —
see [docs/SETUP.md](docs/SETUP.md#mcp-registration).

## Commands

| Command | Does |
|---|---|
| `/menu` | Full inline menu — sessions, screen, system, settings |
| `/sessions` | List sessions with Running/Idle status, tap to switch |
| `/screen <window>` | Screenshot any window by title keyword |
| `/model <fable\|opus\|sonnet\|haiku>` | Switch model (no arg = show current) |
| `/effort <low\|medium\|high\|extra\|max\|ultracode>` | Switch effort |
| `/cmd <command>` | Run a PowerShell command, see real output |
| `/clear` | Clear the input box |
| `/stop` | Stop the current generation |
| `/kill` | Close terminal/emulator/Claude |
| `/status` | Current model, effort, temperatures |
| `/language` | Switch language |
| `/mode` | Output verbosity: live / summary / quiet / verbose |
| `/confirm on\|off` | Stage Send/Edit/Cancel before delivering, or send instantly |
| `/settings` | View and edit runtime settings |

Plain text (not a command) is typed into Claude's input box.

## How it works

Reading and writing are split, because they have opposite requirements.

- **Reading** goes through Claude Code's own transcript file
  (`~/.claude/projects/.../*.jsonl`, tailed live) and Windows UI Automation
  (session list, status, dialogs). Both are exact and cheap — no
  screenshots, no OCR, no guessing.
- **Writing** — typing a message, picking a model — still drives the real
  window, since Claude Desktop's composer isn't exposed to accessibility
  tools. This is the only part that's pixel-based, and it's verified
  against the transcript afterward rather than trusted blindly.

Full design rationale: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Configuration

Two files, two purposes:

- **`.env`** — secrets (bot token, chat ID). Never commit this.
- **`config.yaml`** — behavior (intervals, thresholds, language, etc).
  Copy from `config.example.yaml`; also editable live via `/settings`.
  A bad value falls back to its default with a logged warning, not a crash.

## Security

- The bot only responds to the chat ID in your `.env` — every handler checks
  this. Anyone else messaging it gets ignored.
- Never commit `.env` or `config.yaml` (both gitignored by default).
- Logs are redacted — a filter strips any bot-token-shaped string before it
  reaches disk, since Telegram puts the token in every outbound request URL.
- If you ever suspect your token leaked, revoke it via `@BotFather` →
  `/revoke` and update `.env`.
- `/cmd` runs arbitrary PowerShell with your account's privileges. That's
  the point of a remote-control tool — just be aware of what "remote" means
  here.

## What's not built yet

Scoped out on purpose, not forgotten:

- **Other IDEs** (Cursor, Antigravity, VS Code) — the `Target` interface
  supports adding these; only the Claude Desktop adapter ships today.
- **Terminal agents** (opencode, etc.) inside an IDE terminal.
- **Voice** — interfaces are defined (`tether/voice/base.py`) for future
  ElevenLabs integration, not implemented.
- **Remote MCP/skill editing.**
- **Web dashboard** — would mean exposing this machine; Telegram avoids that.

## Development

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

All 49 tests are GUI-independent — they run on any machine, no Claude
window or Windows accessibility stack required.

## License

MIT — see [LICENSE](LICENSE).
