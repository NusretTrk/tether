# Setup

## 1. Create a Telegram bot and get a token

1. Open Telegram, search for **@BotFather** (official, blue checkmark).
2. Send `/newbot`.
3. Give it a display name (e.g. `My PC Controller`).
4. Give it a username — must end in `bot` (e.g. `my_pc_remote_bot`).
5. BotFather replies with an **HTTP API token**
   (looks like `1234567890:ABCdefGHIjklmNOPQrsTUVwxyz`). Copy it — this is
   your `BOT_TOKEN`.

## 2. Get your chat ID

1. In Telegram, search for **@userinfobot** and start it.
2. It replies with your account details, including `Id: 123456789`.
3. Copy that number — this is your `CHAT_ID`.

## 3. Authorize the bot

Bots can't message you first — you have to start the conversation:

1. Open your bot's chat (the `t.me/your_bot_username` link BotFather gave you).
2. Tap **Start** (or send `/start`).

## 4. Configure tether

```bash
cp .env.example .env
```

Edit `.env`:

```
BOT_TOKEN=1234567890:ABCdefGHIjklmNOPQrsTUVwxyz
CHAT_ID=123456789
```

Never share this file or commit it — it's already in `.gitignore`.

## 5. Install and run

```bash
pip install -r requirements.txt
python run.py
```

Message your bot `/start` on Telegram. You should get a reply with the main
keyboard.

Behavior settings (language, intervals, thresholds) live in `config.yaml` —
copy from `config.example.yaml` if you want to customize before first run;
otherwise defaults are used and the file is created on first save via
`/settings`.

## 6. Auto-start on login (optional)

Register a scheduled task that launches tether silently at every Windows
login, in an **elevated** PowerShell:

```powershell
$action = New-ScheduledTaskAction -Execute "pythonw.exe" -Argument '"C:\path\to\tether\run.py"'
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT45S"   # give Wi-Fi/DNS time to come up before first launch
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "Tether" -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited
```

Notes on the flags — both matter, learned the hard way on the previous
version of this bot:

- **`AllowStartIfOnBatteries` / `DontStopIfGoingOnBatteries`** — Windows'
  default task settings silently refuse to start (or kill mid-run) a task
  when not plugged in. On a laptop that's most of the time you'd want it.
- **45s delay** — a login-triggered task can fire before networking is
  actually up, which crashes tether's first connection attempt. tether
  itself also retries indefinitely on startup failure (every 30s) as a
  second line of defense, but the delay avoids the failed attempts entirely.

To remove: `Unregister-ScheduledTask -TaskName "Tether" -Confirm:$false`

## MCP registration

This lets any agent — Claude Code included — notify you or ask you a
question over Telegram, without ever seeing your bot token.

```bash
claude mcp add tether -- python -m tether.mcp.server
```

(Run from the `tether/` directory, or use an absolute path to `run.py`'s
sibling `src/` — the module needs `src` on `PYTHONPATH`, which `run.py`
sets up automatically; for the MCP entry point specifically, register it
with the full path if you're not launching from inside `tether/`:)

```bash
claude mcp add tether -- python -c "import sys; sys.path.insert(0, r'C:\path\to\tether\src'); from tether.mcp.server import main; main()"
```

Once registered, any agent can call:

- `notify(message)` — send you a message, don't wait for a reply.
- `ask(question, timeout_seconds=300)` — send a question and **block until
  you reply** on Telegram, then return your answer to the agent.

For non-MCP tools (plain scripts, opencode, cron), use the CLI fallback
instead — same `.env`, no token on the command line:

```bash
python tools/notify.py "message text"
```

## Troubleshooting

- **Bot doesn't respond at all** — check `tether.log` for the actual error.
  Common cause: `.env` missing or malformed (see the startup error message,
  it names exactly what's missing).
- **"Unauthorized" from Telegram** — token is wrong or was revoked. Get a
  fresh one from BotFather.
- **Bot responds to `/start` but ignores everything else** — check your
  `CHAT_ID` matches the account you're messaging from; the bot silently
  ignores any chat that isn't the configured one, by design.
- **CPU temperature always shows unavailable** — the direct ATKACPI driver
  read only works on ASUS boards with that driver present; this is expected
  on other hardware. GPU temperature (nvidia-smi) is independent and should
  still work if you have an Nvidia GPU.
