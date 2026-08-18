# Setup

## Quick setup (recommended)

```bash
pip install -r requirements.txt
python setup.py
```

`setup.py` walks you through it: you paste a bot token, it checks the token
is valid, then asks you to message the bot and picks up your chat ID
automatically. No copying IDs from other bots, no editing files by hand.

Then start it:

```bash
python run.py
```

Send `/start` to your bot on Telegram and you should get the menu back.

---

## Getting a bot token

If you don't have one yet:

1. Open Telegram and message **@BotFather** (official, blue checkmark).
2. Send `/newbot`.
3. Give it a display name, e.g. `My PC Controller`.
4. Give it a username ending in `bot`, e.g. `my_pc_remote_bot`.
5. It replies with an **HTTP API token** that looks like
   `1234567890:ABCdefGHIjklmNOPQrsTUVwxyz`. That's what `setup.py` wants.

Keep the token private. Anyone who has it controls your bot. If it leaks,
send `/revoke` to BotFather and run `python setup.py` again with the new one.

---

## Manual setup (if you'd rather not use setup.py)

Copy the example file and fill it in yourself:

```bash
cp .env.example .env
```

```
BOT_TOKEN=1234567890:ABCdefGHIjklmNOPQrsTUVwxyz
CHAT_ID=123456789
```

To find your chat ID manually, message **@userinfobot** on Telegram — it
replies with `Id: 123456789`.

`.env` is gitignored and must never be committed.

Behaviour settings (language, intervals, temperature thresholds) live in
`config.yaml`. Copy `config.example.yaml` if you want to change defaults
before first run; otherwise defaults apply and the file gets written when
you change something via `/settings`.

---

## Start automatically at login

```
install_autostart.bat
```

Double-click it, or run:

```bash
powershell -ExecutionPolicy Bypass -File install_autostart.ps1
```

This drops a shortcut in your personal Startup folder pointing at
`pythonw.exe` (the windowless Python), so tether starts silently at login
with no console window.

**No administrator rights required.** This is deliberate — the obvious
alternative, a Task Scheduler entry, needs elevation on most machines and
also refuses to start on battery power by default, which is exactly when a
laptop user wants it running.

To undo:

```bash
powershell -ExecutionPolicy Bypass -File install_autostart.ps1 -Remove
```

---

## Building a standalone .exe (optional)

You don't need this — `pythonw.exe` already runs tether in the background
with no console, and the autostart script above uses it. Build an exe only
if you want to run tether on a machine without Python installed.

```bash
pip install pyinstaller
build_exe.bat
```

That produces `dist/tether.exe`. Run it directly, or point the autostart
shortcut at it instead.

Two things to know:

- `.env` and `config.yaml` are **not** bundled into the exe. Keep them in
  the same folder as `tether.exe`.
- Antivirus software frequently flags PyInstaller output. This is a known
  false positive affecting all PyInstaller binaries, not something specific
  to this project — but it's a reason to prefer the plain Python route
  unless you actually need the exe.

---

## MCP registration

This lets any agent — Claude Code included — message you or ask you a
question over Telegram, without ever having your bot token pasted into it.

From the `tether/` directory:

```bash
claude mcp add tether -- python -m tether.mcp.server
```

If you're registering from elsewhere, give it the full path so `src` lands
on the import path:

```bash
claude mcp add tether -- python -c "import sys; sys.path.insert(0, r'C:\path\to\tether\src'); from tether.mcp.server import main; main()"
```

Once registered, agents can call:

- `notify(message)` — send you a message, don't wait for a reply.
- `ask(question, timeout_seconds=300)` — send a question and **block until
  you reply** on Telegram, then hand your answer back to the agent.

For anything that doesn't speak MCP (plain scripts, cron jobs), use the CLI
fallback instead — same `.env`, no token on the command line:

```bash
python tools/notify.py "message text"
```

---

## Troubleshooting

**Bot doesn't respond at all.** Check `tether.log`. The most common cause is
a missing or malformed `.env`, and the startup error names exactly what's
wrong.

**"Unauthorized" from Telegram.** The token is wrong or was revoked. Get a
fresh one from BotFather and re-run `python setup.py`.

**Bot answers `/start` but ignores everything else.** Your `CHAT_ID` doesn't
match the account you're messaging from. The bot ignores every chat except
the configured one, by design — that's the only thing stopping strangers
from running shell commands on your PC.

**CPU temperature always shows unavailable.** The direct ATKACPI read only
works on ASUS boards with that driver. Expected on other hardware. GPU
temperature comes from `nvidia-smi` and is independent.

**Sessions list is empty.** Claude Desktop has to be running. The list comes
from Windows accessibility data, which Chromium builds lazily — tether
retries automatically, but the very first call after launching Claude can
come back empty.
