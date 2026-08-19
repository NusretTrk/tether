# Disclaimer and terms of use

Tether is a personal project, published as-is for anyone who finds it
useful. It is not a product, not a service, and nobody is on call for it.

## No warranty

This software is provided without warranty of any kind, express or implied,
including but not limited to merchantability, fitness for a particular
purpose, and non-infringement. See [LICENSE](LICENSE) for the full text.

## No liability

The authors and contributors accept no responsibility for any loss, damage,
data loss, downtime, unauthorised access, or other harm arising from use or
misuse of this software.

## Understand what you are installing

This is remote control software. Read this part properly before running it.

- **It runs shell commands on your machine.** `/cmd` executes with your
  account's privileges. Anyone able to send commands to your bot can do
  anything you can do from a terminal.
- **It controls your desktop.** It focuses windows, types, sends keystrokes,
  and takes screenshots.
- **It reads your agent transcripts.** Whatever is in those sessions,
  including anything sensitive you typed, can be forwarded to your Telegram
  chat.
- **The primary access control is your Telegram chat ID.** Messages from
  any other chat are ignored. If your bot token leaks, revoke it
  immediately via @BotFather; a leaked token means someone else can drive
  the bot. An optional `BOT_PASSWORD` in `.env` adds a second factor on top
  — worth setting if you want protection that doesn't rely entirely on
  your Telegram account itself never being compromised, since chat-id
  whitelisting alone does nothing against that specific scenario.
- **Telegram's Bot API is not end-to-end encrypted.** It's encrypted in
  transit (TLS) like any HTTPS traffic, but Telegram's actual end-to-end
  feature (Secret Chats) doesn't exist for bots. Don't treat this bot as
  more private than a normal Telegram conversation, because it isn't one.

## Your responsibilities

- Keep `.env` private. Never commit it. Never paste your token anywhere.
- Only run this on a machine you own or are authorised to control.
- Only pair it with your own Telegram account.
- Understand that messages travel through Telegram's servers. Do not use
  this for anything you would not put in a Telegram chat.

## Third-party services

Tether talks to the Telegram Bot API. Your use of Telegram is governed by
Telegram's own terms and privacy policy. This project is not affiliated
with, endorsed by, or connected to Telegram, Anthropic, or any other
company whose software it interoperates with.

## Data

Tether stores nothing remotely. Configuration, logs, and state stay on your
machine. Messages are sent only to the single Telegram chat ID you
configure. There is no telemetry, no analytics, and no external service
beyond Telegram itself.
