# Security policy

tether is a personal, hobby project shared publicly because it might be
useful to someone else, not a maintained product with a security team or an
SLA. See [DISCLAIMER.md](DISCLAIMER.md) for the full no-warranty terms —
this file is specifically about what's actually protected, what isn't, and
how to report a problem if you find one.

## What tether actually protects against

- **A stranger who doesn't have your bot token or chat ID.** Every command
  handler checks the chat ID; unauthorized chats are silently ignored.
- **A stranger who finds your Mini App's ngrok URL, if you've turned that
  on.** The URL itself isn't treated as secret — every real request still
  needs a Telegram-signed session or a bearer token only you were ever
  shown. See the [Security section of the README](README.md#security) for
  the actual mechanism, not just the claim.
- **Your own Telegram account being compromised**, if you've set the
  optional `BOT_PASSWORD` — chat-ID whitelisting alone doesn't help here,
  since whoever controls your account genuinely is your authorized chat ID
  as far as Telegram is concerned. The password is a real second factor on
  top of that.

## What tether does not, and cannot, protect against

- **Your machine already being compromised.** Tether runs with your own
  account's privileges by design — that's what makes it a remote control at
  all. If someone already has code execution on your PC, tether adds
  nothing to defend against them and nothing they couldn't already do
  another way.
- **Losing your phone or Telegram session unlocked.** Anyone holding an
  authenticated device with your Telegram open has the same access you do.
- **A leaked bot token, `BOT_PASSWORD`, ngrok authtoken, or Mini App
  browser link.** Each of these is a real credential. If one leaks, revoke
  and reissue it (`@BotFather` → `/revoke` for the bot token, `/miniapp
  revoke` for a browser link, a new authtoken from the ngrok dashboard) —
  tether can't retroactively protect a credential that's already out.

## Reporting a vulnerability

If you find a real security issue (not a general bug — see the repo's
regular issue tracker for those), please use GitHub's private vulnerability
reporting instead of opening a public issue or PR: this repo's **Security**
tab → **Report a vulnerability**. That gets it to the maintainer privately
so there's a chance to fix it before any exploit details are public.

There's no bug bounty, no guaranteed response time, and no dedicated
security team behind this — it's one person's spare-time project. A
genuine report will still be read and taken seriously; just don't expect a
formal process on the other end of it.
