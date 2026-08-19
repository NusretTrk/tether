# Setup

## Quick setup (recommended)

```bash
pip install -r requirements.txt
python setup.py
```

`setup.py` walks you through it: you paste a bot token, it checks the token
is valid, then gives you a link that carries a one-time code baked in. Only
a reply containing that exact code counts as proof it's really you — not
just whoever happened to message the bot first, which matters for a
freshly created bot whose username is guessable for a short window. No
copying IDs from other bots, no editing files by hand.

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

Optional: add a second-factor password on top of the chat-id check.

```
BOT_PASSWORD=something only you know
```

Leave it out and nothing changes — the bot behaves exactly as before. Set
it and every command except `/start`, `/unlock`, and `/help` is locked
until you send `/unlock <password>`; `/lock` re-locks on demand. This
matters specifically if your Telegram account itself were ever
compromised, since the chat-id check alone can't tell that situation apart
from you.

Behaviour settings (language, intervals, temperature thresholds, keypad
profiles for other apps) live in `config.yaml`. Copy `config.example.yaml`
if you want to change defaults before first run; otherwise defaults apply
and the file gets written when you change something via `/settings`.

---

## Telegram Mini App (optional)

A real scrollable UI inside Telegram — status, sessions, a live
transcript view, settings — instead of nested button menus. Off by
default. Skip this section entirely if you're happy with the buttons.

**Read this before turning it on.** The Mini App needs your PC reachable
over a public HTTPS URL, via a tunnel (ngrok) that you run alongside
tether. The URL itself is treated as *not secret* — anyone who finds it
can load the empty page shell, but every actual request requires a
freshly-signed Telegram `initData` blob proving it came from your own
Telegram session for this exact bot, which nobody without your bot token
can forge (see `miniapp/auth.py` if you want to read the actual check).
So the real thing to protect is the same thing you're already
protecting: `BOT_TOKEN` and `NGROK_AUTHTOKEN`, both in `.env`, neither
ever committed or logged.

**One-time setup per install** (not per session — do this once):

1. Create a free ngrok account: https://dashboard.ngrok.com/signup
2. Claim your one free static domain from the ngrok dashboard
   (Domains → New Domain) — something like `yourname.ngrok-free.app`.
   It's yours permanently, it never rotates, and it costs nothing.
3. Install the ngrok agent (https://ngrok.com/download) and make sure
   `ngrok` runs from a terminal, or note the full path to the binary.
4. Copy your authtoken from https://dashboard.ngrok.com/get-started/your-authtoken.
   Set it and your domain either by hand, or from inside the bot itself —
   both work, pick whichever's easier:

   **From the bot** (no file editing): `/settings` → Mini App →
   Configure ngrok → Authtoken / Domain. Paste the token as a plain
   message when asked; the bot tries to delete that message from the
   chat immediately after reading it, shows you only a masked
   confirmation (never the full value again), and asks you to confirm
   before writing anything. The token is written straight to `.env` —
   never through any other file, never logged. Takes effect immediately,
   no restart needed.

   **By hand**, in `.env`:
   ```
   NGROK_AUTHTOKEN=your token here
   ```
   and in `config.yaml`:
   ```yaml
   mini_app_ngrok_domain: "yourname.ngrok-free.app"
   mini_app_ngrok_path: ngrok   # only change this if it's not on PATH
   ```
5. Turn it on: `/settings` → Mini App → on (refuses with a clear message
   if the token or domain isn't set yet — nothing half-starts).
6. Message **@BotFather**, send `/mybots`, pick your bot → **Bot
   Settings → Menu Button → Configure menu button**, and send it
   `https://yourname.ngrok-free.app/` as the URL. (This pairs the domain
   with your bot — a one-time step Telegram requires, done through
   BotFather rather than the Bot API, since domain pairing isn't
   something a bot can do to itself.)
7. If you set the token/domain by hand (not through the bot), restart
   tether now so it picks up the file changes — the bot-side path in
   step 4 already applied everything live. Either way, your chat's menu
   button (bottom-left, next to the text box) now opens the Mini App.
   `/start` re-syncs the button any time it looks stale.

**Turning it off:** `/settings` → Mini App → off, or flip the same
switch from inside the Mini App itself. Either way, the tunnel and local
server actually stop (not just the button) — this isn't a hidden
service running whether you use it or not.

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
with no console window. It launches `watchdog.py` rather than `run.py`
directly — see the next section for what that buys you.

**No administrator rights required.** This is deliberate — the obvious
alternative, a Task Scheduler entry, needs elevation on most machines and
also refuses to start on battery power by default, which is exactly when a
laptop user wants it running.

To undo:

```bash
powershell -ExecutionPolicy Bypass -File install_autostart.ps1 -Remove
```

## Stopping and starting manually

```
stop_tether.bat
start_tether.bat
```

(or the `.ps1` files directly, same as above). `stop_tether` kills both
tether and its watchdog, so it actually stays stopped rather than coming
back on the watchdog's next check. `start_tether` is safe to run even if
tether is already up — it checks first instead of spawning a duplicate.

**The watchdog.** `start_tether.bat` and the autostart shortcut both launch
`watchdog.py`, not `run.py` directly. It checks every 30 seconds whether
tether is still running and relaunches it if not — unconditionally,
whether it crashed or got closed from Task Manager, deliberately or by
accident. There's no way for the watchdog to tell those apart (unlike
`/restart`'s own recovery logic, which uses idle time as a signal for "the
person at the keyboard probably meant to do that" — the watchdog has no
equivalent signal about its own process disappearing). If you want tether
off for a while, use `stop_tether.bat`, not Task Manager — Task Manager
alone just gets it relaunched within half a minute.

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

## Uninstalling

Two separate scripts, because they do different things and one of them
touches packages that might be shared with other projects:

```
uninstall.bat
```

Stops tether (and its watchdog), removes the Startup shortcut, and asks
whether to also delete `.env`/`config.yaml`/logs/`state/` — your bot token
and settings. Leaves the project folder, your Python packages, and your
BotFather bot alone. Delete the folder yourself if you want it gone
entirely, and send `/revoke` to @BotFather if you want the token dead too.

```
uninstall_packages.bat
```

Lists everything in `requirements.txt` and asks before removing each one
that's actually installed. There's no way to know which of these you
already had installed for another project before tether — answer "n" for
anything you want to keep. This is why it's a separate script and asks
per-package rather than uninstall.bat just wiping them all.

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

**`/target <name>` doesn't seem to type anywhere.** Some apps don't put
keyboard focus in their chat/input panel just because the window came to
the foreground — confirmed live against Antigravity, where a message sent
without a click landed nowhere. Add `input_click: {x, y}` to that profile
in `config.yaml` (window-relative percentages, see the commented example
for `antigravity`) to click the panel before pasting.

**Bot says "Locked" and won't do anything.** You've set `BOT_PASSWORD`.
Send `/unlock <password>`. If you're locked out from too many wrong
guesses, wait out the window (5 minutes by default) and try again.

**Mini App menu button doesn't appear, or opens a blank/error page.**
Check `tether.log` for `could not launch ngrok` (binary not found — fix
`mini_app_ngrok_path`) or `mini_app_ngrok_domain or NGROK_AUTHTOKEN is
missing` (one of the two isn't set). If the button itself just looks
stale, send `/start` — it re-syncs it. If ngrok's dashboard shows the
tunnel as active but the page still won't load, double check step 6 in
the Mini App section above (the domain has to be paired with your bot
through @BotFather, not just running in ngrok).
