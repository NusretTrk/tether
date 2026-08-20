"""
The Mini App's entire client is one self-contained HTML string - no
build step, no framework, matching the "don't add resource weight"
constraint this feature was built under. The only external resource is
Telegram's own official WebApp SDK script, which is required for a Mini
App to function at all (it's what supplies initData, theme colors, and
haptics) and isn't a third-party dependency in the supply-chain sense.
No web fonts, no CSS framework, no icon package: the typography rides on
locally-installed system faces and every icon is inline SVG.

Visual design: a deliberate, self-owned palette in Claude's own warm
family (cream/off-white light mode, warm-charcoal dark mode, terracotta
accent) rather than a mirror of the host's arbitrary Telegram theme -
`Telegram.WebApp.colorScheme` is used purely as a light/dark *signal*,
not as a source of colors, so the app looks like itself on every
person's customized Telegram.

Security note: a visitor who finds the ngrok URL and loads it in a plain
browser (not through Telegram) gets exactly this shell and nothing else -
`Telegram.WebApp.initData` is only ever populated by a genuine Telegram
WebApp launch, so the guard at the top of `boot()` stops everything
before a single API call is made. The real auth boundary is server-side
(see miniapp/auth.py) - this client-side guard is a courtesy, not the
security control.
"""

INDEX_HTML = r"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover">
<title>tether</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    /* Warm cream light mode - Claude-family neutrals, never stark white */
    --bg: #F0EEE6;
    --surface: #FBFAF7;
    --surface-2: #F3F1EA;
    --surface-3: #E9E6DC;
    --text: #1F1E1D;
    --text-2: #6D6A61;
    --text-3: #97938A;
    --line: rgba(31,30,29,0.09);
    --line-strong: rgba(31,30,29,0.16);
    --accent: #C15F3C;
    --accent-press: #A94F30;
    --accent-soft: rgba(193,95,60,0.10);
    --accent-ink: #FFFFFF;
    --ok: #3E8B5F;
    --warn: #A9702A;
    --danger: #C0402F;
    --shadow-sm: 0 1px 2px rgba(31,30,29,0.05), 0 1px 3px rgba(31,30,29,0.04);
    --shadow: 0 1px 2px rgba(31,30,29,0.04), 0 6px 20px -6px rgba(31,30,29,0.10);
    --shadow-lift: 0 -1px 0 var(--line), 0 -10px 30px -14px rgba(31,30,29,0.18);
    --r-lg: 20px; --r-md: 14px; --r-sm: 10px;
    --ease: cubic-bezier(0.32, 0.72, 0, 1);
    --ease-soft: cubic-bezier(0.4, 0, 0.2, 1);
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI Variable Text", "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, ui-serif, serif;
    --mono: ui-monospace, "SF Mono", "Cascadia Mono", "Segoe UI Mono", Menlo, Consolas, monospace;
  }
  html[data-theme="dark"] {
    /* Warm charcoal dark mode - same terracotta family, warmed neutrals */
    --bg: #1B1A18;
    --surface: #262523;
    --surface-2: #2F2E2B;
    --surface-3: #3A3835;
    --text: #F2F0E9;
    --text-2: #A6A299;
    --text-3: #7C786F;
    --line: rgba(255,255,255,0.08);
    --line-strong: rgba(255,255,255,0.14);
    --accent: #D97757;
    --accent-press: #C4643F;
    --accent-soft: rgba(217,119,87,0.14);
    --accent-ink: #23130D;
    --ok: #6FBF8D;
    --warn: #D6A15C;
    --danger: #E8796A;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.30);
    --shadow: 0 2px 6px rgba(0,0,0,0.30), 0 10px 28px -10px rgba(0,0,0,0.45);
    --shadow-lift: 0 -1px 0 var(--line), 0 -12px 30px -16px rgba(0,0,0,0.7);
  }
  /* ---------- target-aware accents ----------
     /target can point tether at another app, and the app should look
     like it knows that. Only the accent family is re-tinted - the warm
     cream/charcoal ground, the serif headings and every shape stay
     exactly as they are, so it still reads as the same app talking to a
     different thing rather than a different app. The :not() guard on
     the light blocks keeps them from out-ordering the dark base above;
     an unrecognised /target name lands on [data-target="custom"] and
     gets its own plum tint rather than silently masquerading as
     Claude. */
  html[data-target="antigravity"]:not([data-theme="dark"]) {
    --accent: #4E57A8; --accent-press: #3E4690;
    --accent-soft: rgba(78,87,168,0.10); --accent-ink: #FFFFFF;
  }
  html[data-target="antigravity"][data-theme="dark"] {
    --accent: #8E96E0; --accent-press: #7A82CC;
    --accent-soft: rgba(142,150,224,0.16); --accent-ink: #14162F;
  }
  html[data-target="cursor"]:not([data-theme="dark"]) {
    --accent: #1F7A6B; --accent-press: #175F53;
    --accent-soft: rgba(31,122,107,0.10); --accent-ink: #FFFFFF;
  }
  html[data-target="cursor"][data-theme="dark"] {
    --accent: #4FBFA8; --accent-press: #3EA890;
    --accent-soft: rgba(79,191,168,0.16); --accent-ink: #07211C;
  }
  html[data-target="custom"]:not([data-theme="dark"]) {
    --accent: #8A4F72; --accent-press: #74405F;
    --accent-soft: rgba(138,79,114,0.10); --accent-ink: #FFFFFF;
  }
  html[data-target="custom"][data-theme="dark"] {
    --accent: #C98BAE; --accent-press: #B4789A;
    --accent-soft: rgba(201,139,174,0.16); --accent-ink: #2A1220;
  }

  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body {
    margin: 0; padding: 0; height: 100%;
    overscroll-behavior-y: none;
  }
  body {
    background: var(--bg); color: var(--text);
    font-family: var(--sans);
    font-size: 15px; line-height: 1.45;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
    display: flex; flex-direction: column;
    transition: background-color 240ms var(--ease-soft), color 240ms var(--ease-soft);
  }
  button, input, select, textarea { font-family: inherit; font-size: inherit; color: inherit; }
  ::selection { background: var(--accent-soft); }

  /* ---------- gate (shown when opened outside Telegram) ---------- */
  #gate {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    min-height: 100vh; min-height: 100dvh; padding: 32px 28px; text-align: center; gap: 18px;
  }
  #gate .mark {
    width: 56px; height: 56px; display: grid; place-items: center;
    border-radius: 18px; background: var(--accent-soft); color: var(--accent);
    animation: rise 600ms var(--ease) both;
  }
  #gate h1 {
    margin: 0; font-family: var(--serif); font-size: 28px; font-weight: 500;
    letter-spacing: -0.01em; animation: rise 600ms 60ms var(--ease) both;
  }
  #gate p {
    margin: 0; max-width: 30ch; color: var(--text-2); font-size: 15px;
    animation: rise 600ms 120ms var(--ease) both;
  }
  #gate .fine { font-size: 13px; color: var(--text-3); animation: rise 600ms 180ms var(--ease) both; }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

  /* ---------- app shell ---------- */
  #app {
    display: none; flex-direction: column;
    /* 100dvh is the fallback for a plain browser tab; inside Telegram's
       iOS WebView, dvh does NOT shrink when the on-screen keyboard opens
       (a known WebView quirk, not a bug in this CSS), which is what let
       the composer/tabbar sit underneath the keyboard instead of above
       it. --tg-vh is set from Telegram.WebApp.viewportHeight in JS,
       updated live on the SDK's own viewportChanged event - the actual
       visible height, keyboard included, which is the one signal that's
       reliably accurate here. */
    height: 100dvh;
    height: var(--tg-vh, 100dvh);
  }
  .appbar {
    flex: none; padding: calc(10px + env(safe-area-inset-top)) 20px 8px;
    background: var(--bg);
  }
  .brandline { display: flex; align-items: center; gap: 8px; height: 24px; }
  .brandline .mark { color: var(--accent); display: flex; }
  .wordmark {
    font-family: var(--serif); font-size: 16px; letter-spacing: 0.01em;
    color: var(--text-2);
  }
  .brandline .spacer { flex: 1; }
  .pill {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 11.5px; font-weight: 500; letter-spacing: 0.01em;
    padding: 4px 10px; border-radius: 999px;
    background: var(--surface); color: var(--text-2);
    box-shadow: var(--shadow-sm);
  }
  .pill .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-3); }
  .pill.live .dot { background: var(--ok); box-shadow: 0 0 0 0 rgba(62,139,95,0.5); animation: pulse 2.4s var(--ease-soft) infinite; }
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(62,139,95,0.45); }
    70% { box-shadow: 0 0 0 7px rgba(62,139,95,0); }
    100% { box-shadow: 0 0 0 0 rgba(62,139,95,0); }
  }
  .screen-title {
    margin: 6px 0 2px; font-family: var(--serif); font-weight: 500;
    font-size: 30px; line-height: 1.1; letter-spacing: -0.02em;
  }
  .screen-sub { margin: 2px 0 0; font-size: 13px; color: var(--text-3); }

  main {
    flex: 1; min-height: 0; overflow-y: auto; -webkit-overflow-scrolling: touch;
    padding: 12px 20px 20px; overscroll-behavior: contain;
  }
  .view { display: none; }
  .view.active { display: block; animation: fadein 180ms var(--ease-soft) both; }
  @keyframes fadein { from { opacity: 0.4; } to { opacity: 1; } }
  /* the transcript is a chat surface: it manages its own scroll + no fade */
  #view-transcript.active { animation: none; }

  /* ---------- cards & rows ---------- */
  .card {
    background: var(--surface); border-radius: var(--r-lg);
    box-shadow: var(--shadow); padding: 4px 16px; margin-bottom: 14px;
  }
  .card.flush { padding: 16px; }
  .section-label {
    margin: 22px 4px 8px; font-size: 11.5px; font-weight: 600;
    letter-spacing: 0.07em; text-transform: uppercase; color: var(--text-3);
  }
  .section-label:first-child { margin-top: 4px; }
  .row {
    display: flex; align-items: center; justify-content: space-between; gap: 14px;
    padding: 13px 0; min-height: 52px;
  }
  .row + .row { box-shadow: inset 0 1px 0 var(--line); }
  .row .label { font-weight: 450; }
  .row .sublabel { display: block; font-size: 12px; color: var(--text-3); margin-top: 1px; font-weight: 400; }
  .row .value { color: var(--text-2); font-variant-numeric: tabular-nums; text-align: right; }
  .hint { color: var(--text-3); font-size: 12.5px; line-height: 1.5; margin: -4px 6px 18px; }

  /* ---------- status hero + metric tiles ---------- */
  .hero {
    background: var(--surface); border-radius: var(--r-lg); box-shadow: var(--shadow);
    padding: 18px; margin-bottom: 14px; position: relative; overflow: hidden;
  }
  .hero::after {
    content: ""; position: absolute; inset: 0;
    background: radial-gradient(120% 80% at 100% 0%, var(--accent-soft), transparent 62%);
    pointer-events: none;
  }
  .hero .eyebrow { font-size: 11.5px; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase; color: var(--accent); }
  .hero .model { font-family: var(--serif); font-size: 25px; letter-spacing: -0.015em; margin: 6px 0 2px; word-break: break-word; }
  .hero .meta { font-size: 13px; color: var(--text-2); }
  /* the model line is a control, not a label - .hero::after is
     pointer-events:none, but the stacking context still needs the
     button lifted above it to take the tap */
  .model-tap {
    position: relative; z-index: 1;
    display: flex; align-items: flex-start; gap: 8px;
    width: 100%; text-align: left; margin: 6px 0 2px; padding: 0;
    transform-origin: left center;
    transition: transform 160ms var(--ease), opacity 160ms var(--ease-soft);
  }
  .model-tap:active { transform: scale(0.985); opacity: 0.7; }
  .model-tap .model { margin: 0; min-width: 0; }
  .model-tap .chev { flex: none; color: var(--text-3); display: flex; margin-top: 9px; }

  /* ---------- bottom sheet ---------- */
  .sheet { position: fixed; inset: 0; z-index: 60; display: none; }
  .sheet.open { display: block; }
  .sheet-scrim {
    position: absolute; inset: 0; background: rgba(31,30,29,0.34);
    opacity: 0; transition: opacity 220ms var(--ease-soft);
  }
  html[data-theme="dark"] .sheet-scrim { background: rgba(0,0,0,0.58); }
  .sheet.in .sheet-scrim { opacity: 1; }
  .sheet-panel {
    position: absolute; left: 0; right: 0; bottom: 0;
    display: flex; flex-direction: column; max-height: 82%;
    background: var(--surface); border-radius: 22px 22px 0 0;
    box-shadow: 0 -10px 40px -12px rgba(31,30,29,0.38);
    padding: 6px 18px calc(18px + env(safe-area-inset-bottom));
    transform: translateY(101%); transition: transform 300ms var(--ease);
  }
  .sheet.in .sheet-panel { transform: none; }
  .sheet-grip { flex: none; width: 38px; height: 4px; border-radius: 2px; background: var(--line-strong); margin: 6px auto 12px; }
  .sheet-title { flex: none; font-family: var(--serif); font-size: 21px; letter-spacing: -0.015em; }
  .sheet-sub { flex: none; font-size: 12.5px; color: var(--text-3); margin-top: 3px; }
  .sheet-body { margin-top: 14px; overflow-y: auto; -webkit-overflow-scrolling: touch; overscroll-behavior: contain; }
  .sheet-loading { display: flex; align-items: center; gap: 9px; color: var(--text-2); font-size: 13.5px; padding: 16px 4px 22px; }
  .sheet-msg { color: var(--text-2); font-size: 13.5px; padding: 12px 4px 20px; text-align: center; }
  .sheet-actions { display: flex; gap: 10px; margin-top: 16px; }
  .sheet-actions .btn { flex: 1; padding: 12px 16px; }
  .btn.danger { background: var(--danger); color: #fff; }
  .btn.danger:active { background: var(--danger); filter: brightness(0.88); }

  .opt {
    display: flex; align-items: center; gap: 10px; width: 100%; text-align: left;
    padding: 13px 14px; border-radius: var(--r-md); background: var(--surface-2);
    margin-bottom: 8px; font-weight: 450;
    transition: transform 160ms var(--ease), background-color 160ms var(--ease-soft), opacity 160ms var(--ease-soft);
  }
  .opt:active { transform: scale(0.985); background: var(--surface-3); }
  .opt .nm { flex: 1; min-width: 0; word-break: break-word; }
  .opt .tick { flex: none; color: var(--accent); display: none; }
  .opt.cur { background: var(--accent-soft); box-shadow: inset 0 0 0 1.5px var(--accent); }
  .opt.cur .tick { display: flex; }
  .opt .opt-spin {
    display: none; flex: none; width: 15px; height: 15px; border-radius: 50%;
    border: 2px solid var(--line-strong); border-top-color: var(--accent);
    animation: spin 640ms linear infinite;
  }
  .sheet.working .opt { pointer-events: none; opacity: 0.42; transform: none; }
  .sheet.working .opt.busy { opacity: 1; }
  .opt.busy .opt-spin { display: block; }
  .opt.busy .tick { display: none; }

  /* ---------- command view ---------- */
  /* .card.flush already sets padding - match its specificity to win */
  .card.cmd-box { display: flex; align-items: center; gap: 10px; padding: 10px 11px; margin-bottom: 10px; }
  .cmd-field {
    flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px;
    background: var(--surface-2); border-radius: var(--r-sm); padding: 0 12px;
    transition: box-shadow 160ms var(--ease-soft), background-color 160ms var(--ease-soft);
  }
  .cmd-field.focus { box-shadow: inset 0 0 0 1.5px var(--accent); }
  .cmd-field .sigil { flex: none; font-family: var(--mono); font-size: 13px; color: var(--text-3); }
  #cmd-input {
    flex: 1; min-width: 0; border: none; outline: none; background: none;
    font-family: var(--mono); font-size: 16px; /* 16px avoids iOS zoom-on-focus */
    padding: 11px 0;
  }
  #cmd-input::placeholder { color: var(--text-3); font-family: var(--sans); }
  .cmd-item {
    background: var(--surface); border-radius: var(--r-md); box-shadow: var(--shadow-sm);
    padding: 12px; margin-bottom: 10px; animation: pop 220ms var(--ease) both;
  }
  .cmd-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 9px; }
  .cmd-head .c { flex: 1; min-width: 0; font-family: var(--mono); font-size: 12.5px; word-break: break-all; }
  .cmd-head .c::before { content: "> "; color: var(--text-3); }
  .cmd-head .ts { flex: none; font-size: 11px; color: var(--text-3); font-variant-numeric: tabular-nums; }
  .cmd-badge {
    font-size: 10.5px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--danger); margin-bottom: 7px;
  }
  .cmd-running { display: flex; align-items: center; gap: 9px; color: var(--text-3); font-size: 13px; padding: 5px 2px 3px; }
  /* Output is the one place a terminal look is honest: it IS console
     text, and it stays dark in both themes so it never gets mistaken
     for the app's own chrome. */
  .term {
    background: #171614; color: #E4E0D5;
    font-family: var(--mono); font-size: 12.5px; line-height: 1.5;
    border-radius: var(--r-sm); padding: 11px 12px; margin: 0;
    white-space: pre-wrap; word-break: break-word;
    max-height: 320px; overflow: auto; -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain;
  }
  .term.quiet { color: #8E887B; font-style: italic; }
  .cmd-item.fail .term { color: #F2AFA3; box-shadow: inset 0 0 0 1.5px var(--danger); }

  .tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px; }
  .tile {
    background: var(--surface); border-radius: var(--r-md); box-shadow: var(--shadow-sm);
    padding: 13px 14px;
  }
  .tile .k { font-size: 11.5px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-3); }
  .tile .v { font-size: 21px; margin-top: 3px; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
  .tile .v small { font-size: 13px; color: var(--text-3); margin-left: 1px; }
  .tile.muted .v { color: var(--text-3); font-size: 17px; }
  .tile.hot .v { color: var(--danger); }

  /* ---------- buttons ---------- */
  button {
    border: none; background: none; padding: 0; cursor: pointer;
    transition: transform 160ms var(--ease), background-color 160ms var(--ease-soft), opacity 160ms var(--ease-soft);
  }
  .btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    border-radius: 999px; padding: 9px 16px; font-size: 14px; font-weight: 550;
    background: var(--accent); color: var(--accent-ink);
  }
  .btn:active { transform: scale(0.955); background: var(--accent-press); }
  .btn.ghost { background: var(--surface-2); color: var(--text); }
  .btn.ghost:active { background: var(--surface-3); }
  .btn.tiny { padding: 6px 12px; font-size: 13px; }
  .btn:disabled { opacity: 0.45; transform: none; cursor: default; }

  /* ---------- switch ---------- */
  .switch {
    position: relative; width: 48px; height: 29px; border-radius: 999px; flex: none;
    background: var(--surface-3); cursor: pointer;
    transition: background-color 200ms var(--ease-soft);
  }
  .switch::after {
    content: ""; position: absolute; top: 2.5px; left: 2.5px;
    width: 24px; height: 24px; border-radius: 50%; background: #fff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.24);
    transition: transform 220ms var(--ease), width 180ms var(--ease);
  }
  .switch.on { background: var(--accent); }
  .switch.on::after { transform: translateX(19px); }
  .switch:active::after { width: 28px; }
  .switch.on:active::after { transform: translateX(15px); }

  /* ---------- selects & number fields ---------- */
  .select-wrap { position: relative; display: inline-flex; align-items: center; }
  .select-wrap svg { position: absolute; right: 10px; pointer-events: none; color: var(--text-3); }
  select {
    -webkit-appearance: none; appearance: none; border: none; outline: none;
    background: var(--surface-2); color: var(--text);
    border-radius: var(--r-sm); padding: 8px 30px 8px 12px; font-size: 14px; font-weight: 500;
    transition: background-color 160ms var(--ease-soft);
  }
  select:active { background: var(--surface-3); }
  input.num {
    width: 78px; text-align: right; border: none; outline: none;
    background: var(--surface-2); color: var(--text);
    border-radius: var(--r-sm); padding: 8px 11px; font-size: 14px; font-weight: 500;
    font-variant-numeric: tabular-nums;
    transition: box-shadow 160ms var(--ease-soft), background-color 160ms var(--ease-soft);
  }
  input.num:focus { box-shadow: inset 0 0 0 1.5px var(--accent); }
  input.num.bad { box-shadow: inset 0 0 0 1.5px var(--danger); }

  /* ---------- sessions ---------- */
  .session {
    display: flex; align-items: center; gap: 12px;
    background: var(--surface); border-radius: var(--r-md); box-shadow: var(--shadow-sm);
    padding: 14px 14px; margin-bottom: 10px; width: 100%; text-align: left;
    transition: transform 160ms var(--ease), background-color 160ms var(--ease-soft);
  }
  .session:active { transform: scale(0.985); background: var(--surface-2); }
  .session .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-3); flex: none; }
  .session.running .dot { background: var(--ok); }
  .session .name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 450; }
  .session .state { font-size: 12px; color: var(--text-3); flex: none; }
  .session.running .state { color: var(--ok); }
  .session .chev { color: var(--text-3); flex: none; display: flex; }
  .session.busy { opacity: 0.55; }

  /* ---------- transcript / chat ---------- */
  #view-transcript { display: none; }
  #view-transcript.active { display: flex; flex-direction: column; min-height: 100%; }
  .thread { display: flex; flex-direction: column; gap: 10px; padding-bottom: 6px; }
  .msg { max-width: 84%; display: flex; flex-direction: column; gap: 4px; animation: pop 220ms var(--ease) both; }
  @keyframes pop { from { opacity: 0; transform: translateY(6px) scale(0.99); } to { opacity: 1; transform: none; } }
  .msg.mine { align-self: flex-end; align-items: flex-end; }
  .msg.theirs { align-self: flex-start; align-items: flex-start; }
  .bubble {
    padding: 10px 14px; border-radius: 18px; white-space: pre-wrap; word-break: break-word;
    font-size: 15px; line-height: 1.45;
  }
  .msg.mine .bubble { background: var(--accent); color: var(--accent-ink); border-bottom-right-radius: 6px; }
  .msg.theirs .bubble { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); border-bottom-left-radius: 6px; }
  .msg.theirs.err .bubble { background: var(--surface); color: var(--danger); box-shadow: inset 0 0 0 1px var(--danger); }
  .msg .stamp { font-size: 11px; color: var(--text-3); padding: 0 4px; display: flex; align-items: center; gap: 5px; }
  .msg .stamp.warn { color: var(--warn); }
  .msg .stamp.bad { color: var(--danger); }
  .msg .stamp .retry { color: var(--accent); font-weight: 600; font-size: 11px; text-decoration: underline; }
  .sending .bubble { opacity: 0.72; }

  .aside {
    align-self: flex-start; max-width: 92%;
    display: flex; align-items: flex-start; gap: 7px;
    font-size: 12.5px; color: var(--text-3); padding: 1px 4px;
    animation: pop 220ms var(--ease) both;
  }
  .aside .ico { flex: none; margin-top: 2px; opacity: 0.8; display: flex; }
  .aside .body { min-width: 0; }
  .aside .body b { font-weight: 600; color: var(--text-2); font-family: var(--mono); font-size: 11.5px; }
  .aside .body .t {
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden; word-break: break-word; white-space: pre-wrap;
  }
  .aside.thinking .body .t { font-style: italic; }
  .aside.err { color: var(--danger); }
  .daymark { align-self: center; font-size: 11px; color: var(--text-3); padding: 6px 0 2px; letter-spacing: 0.03em; }

  /* ---------- composer ---------- */
  #composer { display: none; flex: none; }
  #app.on-transcript #composer { display: block; }
  .composer-inner {
    padding: 10px 14px;
    background: var(--bg); box-shadow: var(--shadow-lift);
  }
  .composer-bar {
    display: flex; align-items: flex-end; gap: 8px;
    background: var(--surface); border-radius: 24px; padding: 6px 6px 6px 16px;
    box-shadow: var(--shadow-sm);
    transition: box-shadow 200ms var(--ease-soft);
  }
  .composer-bar.focus { box-shadow: var(--shadow-sm), 0 0 0 1.5px var(--accent-soft); }
  #compose-input {
    flex: 1; min-width: 0; border: none; outline: none; background: none; resize: none;
    padding: 8px 0; max-height: 132px; line-height: 1.4; font-size: 16px; /* 16px avoids iOS zoom-on-focus */
  }
  #compose-input::placeholder { color: var(--text-3); }
  .send-btn {
    flex: none; width: 38px; height: 38px; border-radius: 50%;
    background: var(--accent); color: var(--accent-ink);
    display: grid; place-items: center;
    transition: transform 150ms var(--ease), opacity 150ms var(--ease-soft), background-color 150ms var(--ease-soft);
  }
  .send-btn:active { transform: scale(0.9); background: var(--accent-press); }
  .send-btn:disabled { opacity: 0.35; transform: none; }
  .composer-note {
    font-size: 11.5px; color: var(--text-3); padding: 6px 8px 0; text-align: center;
    min-height: 0; overflow: hidden;
  }

  /* ---------- tabbar ---------- */
  .tabbar {
    flex: none; display: flex; gap: 2px; padding: 6px 10px calc(6px + env(safe-area-inset-bottom));
    background: var(--bg); box-shadow: inset 0 1px 0 var(--line);
  }
  .tab {
    flex: 1; display: flex; flex-direction: column; align-items: center; gap: 3px;
    padding: 7px 0 5px; border-radius: var(--r-md); color: var(--text-3);
    font-size: 10.5px; font-weight: 550; letter-spacing: 0.01em;
    transition: color 140ms var(--ease-soft), background-color 140ms var(--ease-soft), transform 140ms var(--ease);
  }
  .tab .ico { display: flex; }
  .tab:active { transform: scale(0.94); }
  .tab.active { color: var(--accent); background: var(--accent-soft); }

  /* ---------- skeletons, spinner, empty ---------- */
  .sk { background: var(--surface-2); border-radius: 8px; position: relative; overflow: hidden; }
  .sk::after {
    content: ""; position: absolute; inset: 0; transform: translateX(-100%);
    background: linear-gradient(90deg, transparent, var(--surface-3), transparent);
    animation: shimmer 1.5s var(--ease-soft) infinite;
  }
  @keyframes shimmer { 100% { transform: translateX(100%); } }
  .sk-line { height: 12px; margin: 12px 0; }
  .spin {
    width: 15px; height: 15px; border-radius: 50%; flex: none;
    border: 2px solid var(--line-strong); border-top-color: var(--accent);
    animation: spin 640ms linear infinite; display: inline-block; vertical-align: -2px;
  }
  .spin.dim { border-top-color: currentColor; opacity: 0.7; width: 10px; height: 10px; border-width: 1.5px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .empty {
    display: flex; flex-direction: column; align-items: center; gap: 8px;
    color: var(--text-3); text-align: center; padding: 52px 22px; font-size: 14px;
  }
  .empty .big { color: var(--text-2); font-family: var(--serif); font-size: 19px; }
  .empty .btn { margin-top: 8px; }

  /* ---------- toast ---------- */
  #toast {
    position: fixed; left: 50%; bottom: calc(78px + env(safe-area-inset-bottom));
    transform: translate(-50%, 16px); opacity: 0; pointer-events: none;
    max-width: calc(100% - 40px);
    background: var(--surface); color: var(--text);
    box-shadow: var(--shadow); border-radius: 14px; padding: 11px 16px;
    font-size: 13.5px; line-height: 1.4; text-align: center; z-index: 70;
    transition: opacity 220ms var(--ease-soft), transform 260ms var(--ease);
  }
  #toast.show { opacity: 1; transform: translate(-50%, 0); }
  #toast.bad { box-shadow: var(--shadow), inset 0 0 0 1px var(--danger); color: var(--danger); }
  /* a sheet owns the bottom of the screen, so the toast moves to the top
     rather than landing on top of the sheet's own buttons */
  body.sheet-on #toast { top: calc(12px + env(safe-area-inset-top)); bottom: auto; transform: translate(-50%, -16px); }
  body.sheet-on #toast.show { transform: translate(-50%, 0); }

  @media (prefers-reduced-motion: reduce) {
    *, *::after, *::before { animation-duration: 1ms !important; animation-iteration-count: 1 !important; transition-duration: 1ms !important; }
  }
</style>
</head>
<body>

<div id="gate">
  <div class="mark">
    <svg width="30" height="30" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2.6c.5 0 .9.4.9.9v6.1l4.3-4.3a.9.9 0 1 1 1.3 1.3l-4.3 4.3h6.1a.9.9 0 0 1 0 1.8h-6.1l4.3 4.3a.9.9 0 1 1-1.3 1.3l-4.3-4.3v6.1a.9.9 0 1 1-1.8 0v-6.1l-4.3 4.3a.9.9 0 0 1-1.3-1.3l4.3-4.3H3.5a.9.9 0 0 1 0-1.8h6.1L5.3 6.6a.9.9 0 0 1 1.3-1.3l4.3 4.3V3.5c0-.5.4-.9.9-.9z"/></svg>
  </div>
  <h1>tether</h1>
  <p>This is a Telegram Mini App. Open it from your tether bot inside Telegram to sign in.</p>
  <p class="fine">Nothing loads here on its own.</p>
</div>

<div id="app">
  <header class="appbar">
    <div class="brandline">
      <span class="mark" id="brand-mark"><svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2.6c.5 0 .9.4.9.9v6.1l4.3-4.3a.9.9 0 1 1 1.3 1.3l-4.3 4.3h6.1a.9.9 0 0 1 0 1.8h-6.1l4.3 4.3a.9.9 0 1 1-1.3 1.3l-4.3-4.3v6.1a.9.9 0 1 1-1.8 0v-6.1l-4.3 4.3a.9.9 0 0 1-1.3-1.3l4.3-4.3H3.5a.9.9 0 0 1 0-1.8h6.1L5.3 6.6a.9.9 0 0 1 1.3-1.3l4.3 4.3V3.5c0-.5.4-.9.9-.9z"/></svg></span>
      <span class="wordmark">tether</span>
      <span class="spacer"></span>
      <span class="pill" id="target-pill" hidden><span class="dot"></span><span id="target-name"></span></span>
    </div>
    <h1 class="screen-title" id="screen-title">Status</h1>
    <p class="screen-sub" id="screen-sub"></p>
  </header>

  <main id="main">
    <div class="view active" id="view-status">
      <div id="status-body">
        <div class="hero"><div class="sk sk-line" style="width:38%;height:10px"></div><div class="sk sk-line" style="width:66%;height:22px"></div><div class="sk sk-line" style="width:48%;height:10px"></div></div>
        <div class="tiles">
          <div class="tile"><div class="sk sk-line" style="width:50%;height:9px"></div><div class="sk sk-line" style="width:66%;height:18px"></div></div>
          <div class="tile"><div class="sk sk-line" style="width:50%;height:9px"></div><div class="sk sk-line" style="width:66%;height:18px"></div></div>
          <div class="tile"><div class="sk sk-line" style="width:50%;height:9px"></div><div class="sk sk-line" style="width:66%;height:18px"></div></div>
          <div class="tile"><div class="sk sk-line" style="width:50%;height:9px"></div><div class="sk sk-line" style="width:66%;height:18px"></div></div>
        </div>
      </div>
    </div>

    <div class="view" id="view-sessions">
      <div id="sessions-list">
        <div class="session"><div class="sk" style="width:8px;height:8px;border-radius:50%"></div><div class="sk sk-line" style="flex:1;max-width:55%"></div></div>
        <div class="session"><div class="sk" style="width:8px;height:8px;border-radius:50%"></div><div class="sk sk-line" style="flex:1;max-width:40%"></div></div>
        <div class="session"><div class="sk" style="width:8px;height:8px;border-radius:50%"></div><div class="sk sk-line" style="flex:1;max-width:48%"></div></div>
      </div>
    </div>

    <div class="view" id="view-transcript">
      <div class="thread" id="thread">
        <div class="msg theirs"><div class="bubble sk" style="width:180px;height:38px"></div></div>
        <div class="msg mine"><div class="bubble sk" style="width:130px;height:34px"></div></div>
        <div class="msg theirs"><div class="bubble sk" style="width:210px;height:52px"></div></div>
      </div>
    </div>

    <div class="view" id="view-command">
      <div class="card flush cmd-box">
        <span class="cmd-field" id="cmd-field">
          <span class="sigil">&gt;</span>
          <input id="cmd-input" type="text" placeholder="Type a command"
                 autocapitalize="off" autocorrect="off" autocomplete="off" spellcheck="false"
                 enterkeyhint="go" maxlength="1000">
        </span>
        <button class="btn" id="cmd-run" disabled>Run</button>
      </div>
      <p class="hint">Nothing runs until you confirm it on the next screen. Commands execute on your PC with your own account's privileges, and the result is posted to your Telegram chat too.</p>
      <div id="cmd-history"></div>
    </div>

    <div class="view" id="view-settings">
      <p class="section-label">General</p>
      <div class="card">
        <div class="row">
          <span class="label">Language</span>
          <span class="select-wrap">
            <select id="setting-language">
              <option value="en">English</option><option value="tr">Türkçe</option>
              <option value="de">Deutsch</option><option value="es">Español</option>
            </select>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
          </span>
        </div>
        <div class="row">
          <span class="label">Output mode<small class="sublabel">How chatty tether is in chat</small></span>
          <span class="select-wrap">
            <select id="setting-mode">
              <option value="live">live</option><option value="summary">summary</option>
              <option value="quiet">quiet</option><option value="verbose">verbose</option>
            </select>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
          </span>
        </div>
        <div class="row">
          <span class="label">Confirm before send<small class="sublabel">Stage messages for a manual OK</small></span>
          <div class="switch" id="setting-confirm_before_send" data-key="confirm_before_send" role="switch"></div>
        </div>
        <div class="row">
          <span class="label">Mini App<small class="sublabel">This app's menu button</small></span>
          <div class="switch" id="setting-mini_app_enabled" data-key="mini_app_enabled" role="switch"></div>
        </div>
      </div>
      <p class="hint">Turning the Mini App off removes its menu button - reopen it any time from /menu, or send /start if the button looks stale.</p>

      <p class="section-label">Watchers</p>
      <div class="card" id="watcher-toggles"></div>
      <p class="hint">Background watchers tether runs on your PC - turn off whichever ones don't apply to how you use it.</p>

      <p class="section-label">Thresholds</p>
      <div class="card" id="threshold-fields"></div>
      <p class="hint">Everything here saves the moment you change it - there's no save button.</p>
    </div>
  </main>

  <div id="composer">
    <div class="composer-inner">
      <div class="composer-bar" id="composer-bar">
        <textarea id="compose-input" rows="1" placeholder="Message Claude..." maxlength="4096" enterkeyhint="send"></textarea>
        <button class="send-btn" id="compose-send" aria-label="Send message" disabled>
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5"/><path d="M5 12l7-7 7 7"/></svg>
        </button>
      </div>
      <div class="composer-note" id="composer-note"></div>
    </div>
  </div>

  <nav class="tabbar">
    <button class="tab active" data-view="status">
      <span class="ico"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2.5-7 4 14 2.5-7H21"/></svg></span>Status
    </button>
    <button class="tab" data-view="sessions">
      <span class="ico"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/></svg></span>Sessions
    </button>
    <button class="tab" data-view="transcript">
      <span class="ico"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8 8 0 0 1-11.6 7.1L4 20l1.4-4.3A8 8 0 1 1 21 11.5z"/></svg></span>Chat
    </button>
    <button class="tab" data-view="command">
      <span class="ico"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M7.5 9.5l2.8 2.5-2.8 2.5"/><path d="M13 15h4"/></svg></span>Command
    </button>
    <button class="tab" data-view="settings">
      <span class="ico"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2.2"/><circle cx="10" cy="17" r="2.2"/></svg></span>Settings
    </button>
  </nav>
</div>

<div class="sheet" id="sheet">
  <div class="sheet-scrim" id="sheet-scrim"></div>
  <div class="sheet-panel" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
    <div class="sheet-grip"></div>
    <div class="sheet-title" id="sheet-title"></div>
    <div class="sheet-sub" id="sheet-sub"></div>
    <div class="sheet-body" id="sheet-body"></div>
  </div>
</div>

<div id="toast" role="status" aria-live="polite"></div>

<script>
(function () {
  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = tg && tg.initData;

  // "Add to Home Screen" launches this page outside any Telegram
  // context at all - there is no initData to read, ever. The bearer
  // token from /miniapp link travels as a URL *fragment*
  // (https://domain/#t=...), which browsers never send to any server -
  // it only ever exists client-side, read straight off location.hash.
  const hashToken = (location.hash.match(/^#t=(.+)$/) || [])[1];
  const authHeader = initData ? ("tma " + initData) : (hashToken ? ("Bearer " + hashToken) : null);

  // ---- security gate -------------------------------------------------
  // Neither credential present means this page was not opened from a
  // real Telegram session or a valid home-screen link. Bail out before
  // anything else runs: #gate stays visible, #app stays hidden, and not
  // a single /api/* request is ever made.
  if (!authHeader) {
    return;
  }

  document.getElementById("gate").style.display = "none";
  const app = document.getElementById("app");
  app.style.display = "flex";

  tg.ready();
  tg.expand();
  try { tg.disableVerticalSwipes && tg.disableVerticalSwipes(); } catch (e) {}
  applyTheme();
  tg.onEvent("themeChanged", applyTheme);
  applyViewportHeight();
  tg.onEvent("viewportChanged", applyViewportHeight);
  window.addEventListener("resize", applyViewportHeight);

  // Telegram's colorScheme is used only as a light/dark *signal* - the
  // palette itself is ours, so the app looks like itself regardless of
  // whatever accent the user picked for their Telegram client.
  function applyTheme() {
    const dark = tg.colorScheme === "dark";
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    const bg = dark ? "#1B1A18" : "#F0EEE6";
    try { tg.setHeaderColor(bg); } catch (e) {}
    try { tg.setBackgroundColor(bg); } catch (e) {}
    try { tg.setBottomBarColor && tg.setBottomBarColor(bg); } catch (e) {}
  }

  // Telegram's iOS WebView does not shrink CSS dvh when the on-screen
  // keyboard opens - #app kept its full pre-keyboard height, so the
  // composer and tab bar ended up sitting UNDER the keyboard instead of
  // pinned above it. viewportHeight (or viewportStableHeight once
  // Telegram's own resize settles) is the one signal that actually
  // reflects the current visible area, keyboard included - pushed into
  // a CSS variable #app's height is calc()'d from, on load and every
  // time the SDK reports a change.
  function applyViewportHeight() {
    const h = tg.viewportStableHeight || tg.viewportHeight || window.innerHeight;
    document.documentElement.style.setProperty("--tg-vh", h + "px");
  }

  function haptic(kind) {
    try { tg.HapticFeedback && tg.HapticFeedback.impactOccurred(kind || "light"); } catch (e) {}
  }
  function notifyHaptic(kind) {
    try { tg.HapticFeedback && tg.HapticFeedback.notificationOccurred(kind); } catch (e) {}
  }

  async function api(path, opts) {
    opts = opts || {};
    const headers = Object.assign({ "Authorization": authHeader }, opts.headers || {});
    if (opts.body) headers["Content-Type"] = "application/json";
    const res = await fetch(path, {
      method: opts.method || "GET", headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || ("http_" + res.status));
    }
    return res.json();
  }

  function friendlyError(e) {
    const m = (e && e.message) || "";
    if (m === "too_many_failed_attempts") return "Too many failed attempts - locked out for a few minutes.";
    if (m === "locked") return "tether is locked. Send /unlock <password> in the chat, then reopen this.";
    if (m === "text_too_long") return "That message is too long (4096 characters max).";
    if (m === "missing_text") return "Type something first.";
    if (m === "send_failed") return "tether couldn't hand that to the app. Try again.";
    if (m === "invalid_value" || m === "unknown_key") return "tether wouldn't accept that value.";
    if (m === "missing_name") return "That model name came through empty.";
    if (m === "missing_command") return "Type a command first.";
    if (m === "nothing_staged") return "That command already expired - tap Run again.";
    if (m === "exec_failed") return "tether couldn't run that on your PC.";
    if (m.indexOf("http_401") === 0 || m === "expired" || m === "bad_signature")
      return "This session expired. Close and reopen the Mini App.";
    if (m === "http_409") return "Your PC wouldn't accept that.";
    if (m.indexOf("http") === 0) return "Can't reach tether right now - try again in a moment.";
    return "Something went wrong - try again in a moment.";
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  let toastTimer = null;
  function toast(msg, bad) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.classList.toggle("bad", !!bad);
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
  }

  // ---- navigation ----------------------------------------------------
  const TITLES = {
    status: ["Status", "What your PC is doing right now"],
    sessions: ["Sessions", "Switch which conversation tether follows"],
    transcript: ["Chat", "Talk to Claude from anywhere"],
    command: ["Command", "Run something on your PC"],
    settings: ["Settings", "Tune how tether behaves"],
  };
  const views = {
    status: openStatus, sessions: renderSessions, transcript: openTranscript,
    command: renderCommand, settings: renderSettings,
  };
  let currentView = "status";
  let transcriptTimer = null;
  let statusTimer = null;

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.dataset.view;
      if (name === currentView) return;
      haptic("light");
      currentView = name;
      document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
      document.getElementById("screen-title").textContent = TITLES[name][0];
      document.getElementById("screen-sub").textContent = TITLES[name][1];
      app.classList.toggle("on-transcript", name === "transcript");
      clearInterval(transcriptTimer);
      transcriptTimer = null;
      clearInterval(statusTimer);
      statusTimer = null;
      document.getElementById("main").scrollTop = name === "transcript" ? 1e7 : 0;
      views[name]();
    });
  });
  document.getElementById("screen-sub").textContent = TITLES.status[1];

  // ---- target-aware chrome -------------------------------------------
  // /api/status carries which app tether is actually driving right now.
  // Rather than leaving that as one small pill nobody reads, the whole
  // accent family, the appbar mark, the compose placeholder and the Chat
  // subtitle follow it - so glancing at the app tells you what you're
  // about to talk to. A name we don't recognise is NOT an error: it
  // keeps its raw spelling everywhere and just gets the neutral "custom"
  // tint.
  const MARKS = {
    claude: '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2.6c.5 0 .9.4.9.9v6.1l4.3-4.3a.9.9 0 1 1 1.3 1.3l-4.3 4.3h6.1a.9.9 0 0 1 0 1.8h-6.1l4.3 4.3a.9.9 0 1 1-1.3 1.3l-4.3-4.3v6.1a.9.9 0 1 1-1.8 0v-6.1l-4.3 4.3a.9.9 0 0 1-1.3-1.3l4.3-4.3H3.5a.9.9 0 0 1 0-1.8h6.1L5.3 6.6a.9.9 0 0 1 1.3-1.3l4.3 4.3V3.5c0-.5.4-.9.9-.9z"/></svg>',
    antigravity: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19.5V4.5"/><path d="M6.6 9.9L12 4.2l5.4 5.7"/><path d="M4 21.4h16"/></svg>',
    cursor: '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M5.6 2.4l13 9.4-6 1.1 2.9 6.1-2.7 1.3-2.9-6.1-4.3 4.2z"/></svg>',
    custom: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><rect x="3.4" y="3.4" width="17.2" height="17.2" rx="5.2"/><circle cx="12" cy="12" r="2.7" fill="currentColor" stroke="none"/></svg>',
  };
  const TARGET_LABELS = { claude: "Claude", antigravity: "Antigravity", cursor: "Cursor" };

  let currentTarget = null;
  function applyTarget(raw) {
    const name = (typeof raw === "string" && raw.trim()) ? raw.trim() : "claude";
    if (name === currentTarget) return;
    currentTarget = name;
    const key = Object.prototype.hasOwnProperty.call(TARGET_LABELS, name.toLowerCase())
      ? name.toLowerCase() : "custom";
    const label = key === "custom" ? name : TARGET_LABELS[key];

    document.documentElement.setAttribute("data-target", key);
    document.getElementById("brand-mark").innerHTML = MARKS[key];
    document.getElementById("target-name").textContent = name;
    const pill = document.getElementById("target-pill");
    pill.hidden = false;
    pill.classList.add("live");

    input.placeholder = "Message " + label + "...";
    TITLES.transcript[1] = "Talk to " + label + " from anywhere";
    if (currentView === "transcript") {
      document.getElementById("screen-sub").textContent = TITLES.transcript[1];
    }
  }

  // ---- bottom sheet ---------------------------------------------------
  const sheetEl = document.getElementById("sheet");
  let sheetDismiss = null;
  let sheetHideTimer = null;

  function openSheet(opts) {
    document.getElementById("sheet-title").textContent = opts.title || "";
    const sub = document.getElementById("sheet-sub");
    sub.textContent = opts.sub || "";
    sub.hidden = !opts.sub;
    document.getElementById("sheet-body").innerHTML = opts.html || "";
    sheetDismiss = opts.onDismiss || null;
    clearTimeout(sheetHideTimer);
    sheetEl.classList.remove("working");
    sheetEl.classList.add("open");
    document.body.classList.add("sheet-on");
    // Flush the display:none -> block change with a forced reflow so the
    // browser has a real starting frame at translateY(101%) to animate
    // FROM, then flip to .in synchronously. A requestAnimationFrame pair
    // reads more idiomatically but silently never fires when the WebView
    // isn't compositing (backgrounded / throttled), which would leave the
    // panel parked off-screen with the scrim up and nothing to tap.
    void sheetEl.offsetHeight;
    sheetEl.classList.add("in");
    try { tg.BackButton && tg.BackButton.show(); } catch (e) {}
  }

  /* `silent` closes without running onDismiss - used when the sheet's own
     action already took over (a model was picked, a command confirmed),
     so the cancel path doesn't fire on top of it. */
  function closeSheet(silent) {
    if (!sheetEl.classList.contains("open")) return;
    const fn = sheetDismiss;
    sheetDismiss = null;
    sheetEl.classList.remove("in");
    clearTimeout(sheetHideTimer);
    sheetHideTimer = setTimeout(() => {
      if (!sheetEl.classList.contains("in")) {
        sheetEl.classList.remove("open", "working");
        document.body.classList.remove("sheet-on");
        // Emptied only after the slide-out finishes, so the panel still
        // has its content while it animates away - and so a retired
        // sheet leaves no stale buttons (with live listeners) behind.
        sheetBody().innerHTML = "";
      }
    }, 300);
    try { tg.BackButton && tg.BackButton.hide(); } catch (e) {}
    if (!silent && fn) fn();
  }
  function sheetOpen() { return sheetEl.classList.contains("open"); }
  function sheetBody() { return document.getElementById("sheet-body"); }

  document.getElementById("sheet-scrim").addEventListener("click", () => {
    if (sheetEl.classList.contains("working")) return;
    haptic("light");
    closeSheet();
  });
  try { tg.onEvent("backButtonClicked", () => { if (!sheetEl.classList.contains("working")) closeSheet(); }); } catch (e) {}

  const TICK = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>';

  // ---- model picker ---------------------------------------------------
  async function openModelPicker() {
    openSheet({
      title: "Switch model",
      sub: "tether drives the app's own picker - give it a couple of seconds.",
      html: '<div class="sheet-loading"><span class="spin"></span>Reading the model list...</div>',
    });

    let data;
    try {
      data = await api("/api/models");
    } catch (e) {
      if (sheetOpen()) sheetBody().innerHTML = '<div class="sheet-msg">' + esc(friendlyError(e)) + "</div>";
      return;
    }
    if (!sheetOpen()) return;   // dismissed while the list was loading

    const models = (data && data.models) || [];
    if (!models.length) {
      sheetBody().innerHTML = '<div class="sheet-msg">This app didn\'t report any switchable models.</div>';
      return;
    }
    // `current` is allowed to be null - nothing gets highlighted then,
    // which is honest rather than guessing at a selection.
    const cur = data.current;
    sheetBody().innerHTML = models.map((m) =>
      '<button class="opt' + (cur && m === cur ? " cur" : "") + '" data-model="' + esc(m) + '">' +
        '<span class="nm">' + esc(m) + "</span>" +
        '<span class="tick">' + TICK + "</span>" +
        '<span class="opt-spin"></span>' +
      "</button>"
    ).join("");
    sheetBody().querySelectorAll("[data-model]").forEach((btn) =>
      btn.addEventListener("click", () => pickModel(btn, btn.dataset.model))
    );
  }

  async function pickModel(btn, name) {
    if (sheetEl.classList.contains("working")) return;
    haptic("medium");
    sheetEl.classList.add("working");
    btn.classList.add("busy");
    try {
      const r = await api("/api/model", { method: "POST", body: { name: name } });
      closeSheet(true);
      toast("Model set to " + ((r && r.model) || name));
      notifyHaptic("success");
      renderStatus();
    } catch (e) {
      // 409 means the app's picker had no entry matching that name - a
      // real answer from the PC, not a transport failure, so say so
      // plainly and leave the sheet up to try something else.
      const m = (e && e.message) || "";
      toast(m === "http_409"
        ? "Couldn't switch to that - the app didn't offer " + name + "."
        : friendlyError(e), true);
      notifyHaptic("error");
      sheetEl.classList.remove("working");
      btn.classList.remove("busy");
    }
  }

  // ---- status --------------------------------------------------------
  function tile(k, v, cls) {
    return '<div class="tile ' + (cls || "") + '"><div class="k">' + esc(k) + '</div><div class="v">' + v + "</div></div>";
  }

  // Status is the one view that re-reads on a timer, so it repaints only
  // when something actually changed - otherwise an 8s tick would tear
  // down the model button under whatever finger is on it.
  let lastStatusSig = "";

  function openStatus() {
    renderStatus();
    statusTimer = setInterval(() => {
      if (document.visibilityState === "visible") renderStatus();
    }, 8000);
  }

  async function renderStatus() {
    const body = document.getElementById("status-body");
    try {
      const s = await api("/api/status");
      // every poll, not just the first - /target can change from the
      // Telegram side while this app sits open
      applyTarget(s.target);

      const sig = JSON.stringify([s.model, s.effort, s.output_mode, s.cpu_c, s.gpu_c, s.fan, s.target]);
      if (sig === lastStatusSig) return;
      lastStatusSig = sig;

      const cpuHot = s.cpu_c != null && s.cpu_c >= 85;
      const gpuHot = s.gpu_c != null && s.gpu_c >= 85;
      body.innerHTML =
        '<div class="hero">' +
          '<div class="eyebrow">' + esc(s.target || "claude") + "</div>" +
          '<button class="model-tap" id="model-tap">' +
            '<span class="model">' + esc(s.model || "Unknown model") + "</span>" +
            '<span class="chev"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg></span>' +
          "</button>" +
          '<div class="meta">' + esc(s.effort || "default") + " effort &middot; " + esc(s.output_mode || "live") + " output</div>" +
        "</div>" +
        '<div class="tiles">' +
          tile("CPU", s.cpu_c != null ? esc(s.cpu_c) + "<small>&deg;C</small>" : "n/a", s.cpu_c == null ? "muted" : (cpuHot ? "hot" : "")) +
          tile("GPU", s.gpu_c != null ? esc(s.gpu_c) + "<small>&deg;C</small>" : "n/a", s.gpu_c == null ? "muted" : (gpuHot ? "hot" : "")) +
          tile("Fan", s.fan != null ? esc(s.fan) + "<small>%</small>" : "n/a", s.fan == null ? "muted" : "") +
          tile("Output", esc(s.output_mode || "live"), "muted") +
        "</div>" +
        '<div class="card"><div class="row"><span class="label">Effort</span><span class="value">' + esc(s.effort || "unknown") + "</span></div>" +
        '<div class="row"><span class="label">Target app</span><span class="value">' + esc(s.target || "claude") + "</span></div>" +
        '<div class="row"><span class="label">Tunnel</span><span class="value"><button class="btn ghost tiny" id="stop-tunnel-btn">Stop</button></span></div></div>';
      wire("model-tap", openModelPicker);
      wire("stop-tunnel-btn", stopTunnel);
    } catch (e) {
      if (lastStatusSig === "__err") return;
      lastStatusSig = "__err";
      body.innerHTML = emptyState("Couldn't load status", friendlyError(e), "retry-status");
      wire("retry-status", renderStatus);
    }
  }

  function emptyState(title, sub, retryId) {
    return '<div class="empty"><div class="big">' + esc(title) + "</div><div>" + esc(sub) + "</div>" +
      (retryId ? '<button class="btn ghost tiny" id="' + retryId + '">Try again</button>' : "") + "</div>";
  }
  function wire(id, fn) {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", () => { haptic("light"); fn(); });
  }

  // Quick access from the very first screen this app shows - the same
  // mini_app_enabled toggle Settings already has, just one tap closer
  // for "I'm about to game, kill the tunnel now" instead of digging
  // through a settings list.
  async function stopTunnel() {
    if (!confirm("Stop the Mini App tunnel? This shuts down remote access from any browser/phone until you turn it back on from the bot's /settings.")) return;
    try {
      await api("/api/settings", { method: "POST", body: { key: "mini_app_enabled", value: false } });
      notifyHaptic("success");
      toast("Tunnel stopped.");
    } catch (e) {
      toast(friendlyError(e), true);
      notifyHaptic("error");
    }
  }

  // ---- sessions ------------------------------------------------------
  async function renderSessions() {
    const list = document.getElementById("sessions-list");
    try {
      const data = await api("/api/sessions");
      const sessions = data.sessions || [];
      if (!sessions.length) {
        list.innerHTML = emptyState("No sessions yet", "Open a conversation on your PC and it'll show up here.", "retry-sessions");
        wire("retry-sessions", renderSessions);
        return;
      }
      list.innerHTML = sessions.map((s) =>
        '<button class="session' + (s.running ? " running" : "") + '" data-switch="' + esc(s.name) + '">' +
          '<span class="dot"></span>' +
          '<span class="name">' + esc(s.name) + "</span>" +
          '<span class="state">' + (s.running ? "running" : "idle") + "</span>" +
          '<span class="chev"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg></span>' +
        "</button>"
      ).join("");
      list.querySelectorAll("[data-switch]").forEach((btn) => btn.addEventListener("click", async () => {
        if (btn.classList.contains("busy")) return;
        haptic("medium");
        btn.classList.add("busy");
        try {
          const r = await api("/api/sessions/switch", { method: "POST", body: { name: btn.dataset.switch } });
          if (r && r.ok === false) { toast("That session wouldn't switch.", true); notifyHaptic("error"); }
          else { toast("Switched to " + btn.dataset.switch); notifyHaptic("success"); }
        } catch (e) {
          toast(friendlyError(e), true);
          notifyHaptic("error");
        }
        btn.classList.remove("busy");
        renderSessions();
      }));
    } catch (e) {
      list.innerHTML = emptyState("Couldn't load sessions", friendlyError(e), "retry-sessions");
      wire("retry-sessions", renderSessions);
    }
  }

  // ---- transcript + compose ------------------------------------------
  // `outbox` holds messages typed here. Each one renders instantly as a
  // bubble (no waiting on the 3s poll), carries its own honest server
  // status, and is reconciled against the real transcript once Claude's
  // own log echoes it back.
  const outbox = [];
  let localSeq = 0;
  let lastEvents = [];
  let lastSig = "";
  let loadedOnce = false;

  const SEND_LABELS = {
    sending:                   { text: "Sending", tone: "", spin: true },
    sent_unverified:           { text: "Sent", tone: "", tick: true },
    sent_pending_verification: { text: "Delivering", tone: "", spin: true },
    confirmed:                 { text: "Sent", tone: "", tick: true },
    deferred:                  { text: "Held - you're active at the keyboard", tone: "warn" },
    staged:                    { text: "Staged - confirm from Telegram to send", tone: "warn" },
    stage_failed:              { text: "Couldn't paste into the app", tone: "bad", retry: true },
    focus_failed:              { text: "Pasted, but couldn't press Enter", tone: "bad", retry: true },
    failed:                    { text: "Not sent", tone: "bad", retry: true },
  };

  function openTranscript() {
    loadTranscript();
    transcriptTimer = setInterval(() => {
      if (document.visibilityState === "visible") loadTranscript();
    }, 3000);
  }

  async function loadTranscript(opts) {
    try {
      const data = await api("/api/transcript");
      lastEvents = data.events || [];
      loadedOnce = true;
      paintThread();
    } catch (e) {
      if (!loadedOnce) {
        document.getElementById("thread").innerHTML =
          emptyState("Couldn't load the transcript", friendlyError(e), "retry-transcript");
        wire("retry-transcript", loadTranscript);
      } else if (opts && opts.loud) {
        toast(friendlyError(e), true);
      }
    }
  }

  function stamp(ts) {
    if (!ts) return "";
    const d = new Date(typeof ts === "number" ? (ts < 1e12 ? ts * 1000 : ts) : ts);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  const ASIDE_ICONS = {
    tool_call: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a4 4 0 0 1 5 5L21 13l-3-3-6.5 8.5a2.1 2.1 0 0 1-3-3L17 9l-3-3z"/></svg>',
    tool_result: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>',
    thinking: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/></svg>',
    image: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M3 16l5-4 4 3 3-2 6 5"/></svg>',
    system: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/></svg>',
  };

  /* Pairs each outbox message with its real echo in the transcript, so a
     message never renders twice: the local bubble takes the echo's slot
     and keeps its own status line. Confirmed bubbles retire after a
     minute, at which point the server's own copy simply renders instead. */
  function buildItems() {
    const now = Date.now();
    for (let i = outbox.length - 1; i >= 0; i--) {
      const m = outbox[i];
      if (m.state === "confirmed" && now - m.confirmedAt > 60000) outbox.splice(i, 1);
    }
    if (outbox.length > 40) outbox.splice(0, outbox.length - 40);

    const free = outbox.filter((m) => m.state !== "failed");
    const placed = new Set();
    const items = [];
    for (const e of lastEvents) {
      if (e.type === "user_text") {
        const text = (e.text || "").trim();
        const hit = free.find((m) => !placed.has(m.id) && m.text === text);
        if (hit) {
          placed.add(hit.id);
          if (hit.state === "sending" || hit.state === "sent_pending_verification" ||
              hit.state === "sent_unverified" || hit.state === "deferred" || hit.state === "staged") {
            hit.state = "confirmed";
            hit.confirmedAt = now;
          }
          items.push({ kind: "mine", m: hit, ts: e.timestamp });
          continue;
        }
      }
      items.push({ kind: "event", e: e });
    }
    for (const m of outbox) if (!placed.has(m.id)) items.push({ kind: "mine", m: m });
    return items;
  }

  function renderMine(m, ts) {
    const info = SEND_LABELS[m.state] || SEND_LABELS.sending;
    const label = m.state === "failed" && m.error ? m.error : info.text;
    let right = "";
    if (info.spin) right = '<span class="spin dim"></span>';
    else if (info.tick) right = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>';
    return '<div class="msg mine' + (info.spin ? " sending" : "") + '">' +
      '<div class="bubble">' + esc(m.text) + "</div>" +
      '<div class="stamp ' + (info.tone || "") + '">' +
        (ts ? esc(stamp(ts)) + " &middot; " : "") + esc(label) + " " + right +
        (info.retry ? ' <button class="retry" data-retry="' + m.id + '">Retry</button>' : "") +
      "</div></div>";
  }

  function paintThread() {
    const items = buildItems();
    const sig = JSON.stringify(items.map((it) => it.kind === "mine"
      ? ["m", it.m.id, it.m.state]
      : ["e", it.e.type, it.e.timestamp, it.e.tool_name, it.e.is_error, (it.e.text || "").length, (it.e.text || "").slice(0, 40)]));
    if (sig === lastSig) return;
    lastSig = sig;

    const main = document.getElementById("main");
    const wasNearBottom = main.scrollHeight - main.scrollTop - main.clientHeight < 120;
    const thread = document.getElementById("thread");

    if (!items.length) {
      thread.innerHTML = '<div class="empty"><div class="big">Nothing here yet</div><div>Send Claude a message below and the conversation shows up here.</div></div>';
      return;
    }

    thread.innerHTML = items.map((it) => {
      if (it.kind === "mine") return renderMine(it.m, it.ts);
      const e = it.e;
      const text = e.text || "";
      if (e.type === "user_text") {
        return '<div class="msg mine"><div class="bubble">' + esc(text) + "</div>" +
          '<div class="stamp">' + esc(stamp(e.timestamp)) + "</div></div>";
      }
      if (e.type === "assistant_text") {
        return '<div class="msg theirs' + (e.is_error ? " err" : "") + '"><div class="bubble">' + esc(text) + "</div>" +
          '<div class="stamp">' + esc(stamp(e.timestamp)) + "</div></div>";
      }
      const head = e.tool_name ? "<b>" + esc(e.tool_name) + "</b> " : (e.type === "thinking" ? "<b>thinking</b> " : "");
      return '<div class="aside ' + esc(e.type) + (e.is_error ? " err" : "") + '">' +
        '<span class="ico">' + (ASIDE_ICONS[e.type] || ASIDE_ICONS.system) + "</span>" +
        '<span class="body">' + head + '<span class="t">' + esc(text) + "</span></span></div>";
    }).join("");

    thread.querySelectorAll("[data-retry]").forEach((b) => b.addEventListener("click", () => {
      const m = outbox.find((x) => String(x.id) === b.dataset.retry);
      if (m) resend(m);
    }));

    if (wasNearBottom) main.scrollTop = main.scrollHeight;
  }

  // ---- composer ------------------------------------------------------
  const input = document.getElementById("compose-input");
  const sendBtn = document.getElementById("compose-send");
  const note = document.getElementById("composer-note");
  const bar = document.getElementById("composer-bar");

  function autogrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 132) + "px";
    sendBtn.disabled = !input.value.trim();
  }
  input.addEventListener("input", autogrow);
  input.addEventListener("focus", () => {
    bar.classList.add("focus");
    setTimeout(() => { document.getElementById("main").scrollTop = 1e7; }, 250);
  });
  input.addEventListener("blur", () => bar.classList.remove("focus"));
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) { ev.preventDefault(); doSend(); }
  });
  sendBtn.addEventListener("click", doSend);

  function noteText(msg) {
    note.textContent = msg || "";
  }

  function doSend() {
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    autogrow();
    const msg = { id: ++localSeq, text: text, state: "sending", at: Date.now() };
    outbox.push(msg);
    lastSig = "";           // force an immediate repaint - no poll delay
    paintThread();
    document.getElementById("main").scrollTop = 1e7;
    haptic("medium");
    deliver(msg);
  }

  function resend(m) {
    haptic("medium");
    m.state = "sending";
    m.error = null;
    lastSig = "";
    paintThread();
    deliver(m);
  }

  async function deliver(m) {
    try {
      const r = await api("/api/send", { method: "POST", body: { text: m.text } });
      const status = (r && r.status) || "sent_unverified";
      m.state = SEND_LABELS[status] ? status : "sent_unverified";
      if (status === "deferred") {
        noteText("Held until you step away from the PC.");
        notifyHaptic("warning");
      } else if (status === "staged") {
        noteText("Waiting for your confirm in the Telegram chat.");
        notifyHaptic("warning");
      } else if (status === "stage_failed" || status === "focus_failed") {
        noteText("");
        notifyHaptic("error");
      } else {
        noteText("");
        notifyHaptic("success");
      }
      // Nudge the transcript a couple of times so Claude's own echo (and
      // then its reply) land well before the next 3s tick would fetch them.
      if (status === "sent_pending_verification" || status === "sent_unverified") {
        setTimeout(() => loadTranscript(), 700);
        setTimeout(() => loadTranscript(), 2000);
      }
    } catch (e) {
      m.state = "failed";
      m.error = friendlyError(e);
      notifyHaptic("error");
    }
    lastSig = "";
    paintThread();
    setTimeout(() => { if (note.textContent) noteText(""); }, 6000);
  }

  // ---- command --------------------------------------------------------
  /* Deliberately not a terminal emulator. This is the /cmd flow with a
     touch surface on it: stage the command, look at the exact text you
     staged, then confirm - the same friction /cmd has over Telegram,
     for the same reason (real shell execution with the owner's own
     privileges is the most dangerous thing this bot can do). The
     backend audit-logs it identically and posts the result into the
     Telegram chat either way, so nothing here is a side channel.
     History is client-side only for this session - no endpoint reads it
     back, it just survives tab switches. */
  const cmdInput = document.getElementById("cmd-input");
  const cmdRun = document.getElementById("cmd-run");
  const cmdField = document.getElementById("cmd-field");
  const cmdHistory = [];
  let cmdSeq = 0;
  let cmdBusy = false;

  // cmdBusy covers both "staged, awaiting your confirm" and "actually
  // running" - the server holds one staged slot, so a second Run must
  // not be possible in either state. The spinner in the history row is
  // what reports the run itself.
  function syncRunBtn() {
    cmdRun.disabled = cmdBusy || !cmdInput.value.trim();
  }
  cmdInput.addEventListener("input", syncRunBtn);
  cmdInput.addEventListener("focus", () => cmdField.classList.add("focus"));
  cmdInput.addEventListener("blur", () => cmdField.classList.remove("focus"));
  cmdInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); stageCmd(); }
  });
  cmdRun.addEventListener("click", stageCmd);

  function renderCommand() {
    paintCmd();
    syncRunBtn();
  }

  function paintCmd() {
    const el = document.getElementById("cmd-history");
    if (!cmdHistory.length) {
      el.innerHTML = emptyState("Nothing has run yet",
        "Type a command above. You get a confirm step before anything executes.");
      return;
    }
    el.innerHTML = cmdHistory.map((it) => {
      const failed = it.state === "fail" || it.state === "error";
      let body;
      if (it.state === "running") {
        body = '<div class="cmd-running"><span class="spin"></span>Running on your PC...</div>';
      } else if (it.output) {
        body = '<pre class="term">' + esc(it.output) + "</pre>";
      } else {
        body = '<pre class="term quiet">(finished with no output)</pre>';
      }
      const badge = it.state === "fail" ? '<div class="cmd-badge">exited with an error</div>'
        : it.state === "error" ? '<div class="cmd-badge">didn\'t run</div>' : "";
      return '<div class="cmd-item' + (failed ? " fail" : "") + '">' +
        '<div class="cmd-head"><span class="c">' + esc(it.command) + "</span>" +
        '<span class="ts">' + esc(stamp(it.at)) + "</span></div>" +
        badge + body + "</div>";
    }).join("");
  }

  async function stageCmd() {
    const command = cmdInput.value.trim();
    if (!command || cmdBusy) return;
    cmdBusy = true;
    syncRunBtn();
    try {
      await api("/api/cmd/stage", { method: "POST", body: { command: command } });
    } catch (e) {
      cmdBusy = false;
      syncRunBtn();
      toast(friendlyError(e), true);
      notifyHaptic("error");
      return;
    }
    haptic("medium");
    cmdInput.blur();
    openConfirmSheet(command);
  }

  function openConfirmSheet(command) {
    openSheet({
      title: "Run this?",
      sub: "It runs on your PC with your own account's privileges.",
      html: '<pre class="term">' + esc(command) + "</pre>" +
        '<div class="sheet-actions">' +
          '<button class="btn ghost" id="cmd-cancel">Cancel</button>' +
          '<button class="btn danger" id="cmd-confirm">Run it</button>' +
        "</div>",
      // covers the scrim tap and Telegram's own back button too - the
      // staged command must not be left sitting on the server
      onDismiss: () => cancelStaged(),
    });
    document.getElementById("cmd-cancel").addEventListener("click", () => {
      haptic("light");
      closeSheet();
    });
    document.getElementById("cmd-confirm").addEventListener("click", () => runStaged(command));
  }

  async function cancelStaged() {
    cmdBusy = false;
    syncRunBtn();
    try { await api("/api/cmd/cancel", { method: "POST" }); } catch (e) {}
  }

  async function runStaged(command) {
    haptic("medium");
    closeSheet(true);          // silent: don't fire the cancel path
    const item = { id: ++cmdSeq, command: command, at: Date.now(), state: "running", output: "" };
    cmdHistory.unshift(item);
    if (cmdHistory.length > 20) cmdHistory.length = 20;
    cmdInput.value = "";
    syncRunBtn();
    paintCmd();
    document.getElementById("main").scrollTop = 0;

    try {
      const r = await api("/api/cmd/confirm", { method: "POST" });
      // ok:false is the command itself failing - real output worth
      // reading, just styled as a failure. Only a thrown error is a
      // transport/server problem.
      item.state = r && r.ok ? "ok" : "fail";
      item.output = (r && r.output) || "";
      notifyHaptic(item.state === "ok" ? "success" : "error");
    } catch (e) {
      item.state = "error";
      item.output = friendlyError(e);
      notifyHaptic("error");
    }
    cmdBusy = false;
    syncRunBtn();
    paintCmd();
  }

  // ---- settings ------------------------------------------------------
  const WATCHER_TOGGLES = [
    ["dialog_watch_enabled", "Dialog alerts", "Tell me when a popup needs an answer"],
    ["stall_watch_enabled", "Stall detection", "Notice when a run goes quiet"],
    ["activity_watch_enabled", "Session activity", "Ping me when a session starts moving"],
    ["app_health_watch_enabled", "App health", "Watch for the app crashing or hanging"],
    ["usage_limit_continue_enabled", "Auto-continue", "Resume after a usage limit clears"],
    ["preserve_user_clipboard", "Preserve clipboard", "Restore what you had copied after a paste"],
  ];
  const THRESHOLD_FIELDS = [
    ["temp_emergency_c", "Emergency temp", "&deg;C", 1, 150],
    ["defer_when_user_active_sec", "Defer while active", "sec", 0, 600],
    ["auto_send_after_idle_sec", "Auto-send after idle", "sec", 0, 3600],
  ];

  let lastSettings = {};

  function ensureSettingsBuilt() {
    const watchers = document.getElementById("watcher-toggles");
    if (!watchers.dataset.built) {
      watchers.innerHTML = WATCHER_TOGGLES.map(([key, label, sub]) =>
        '<div class="row"><span class="label">' + label + '<small class="sublabel">' + sub + "</small></span>" +
        '<div class="switch" id="setting-' + key + '" data-key="' + key + '" role="switch"></div></div>'
      ).join("");
      watchers.querySelectorAll(".switch").forEach((el) =>
        el.addEventListener("click", () => toggleSwitch(el, el.dataset.key))
      );
      watchers.dataset.built = "1";
    }
    const thresholds = document.getElementById("threshold-fields");
    if (!thresholds.dataset.built) {
      thresholds.innerHTML = THRESHOLD_FIELDS.map(([key, label, unit, lo, hi]) =>
        '<div class="row"><span class="label">' + label + '<small class="sublabel">' + unit + " &middot; " + lo + "-" + hi + "</small></span>" +
        '<input class="num" type="number" inputmode="numeric" min="' + lo + '" max="' + hi + '" step="1" id="setting-' + key + '" data-key="' + key + '"></div>'
      ).join("");
      thresholds.querySelectorAll("input").forEach((el) =>
        el.addEventListener("change", async () => {
          const n = parseInt(el.value, 10);
          if (Number.isNaN(n)) { el.value = lastSettings[el.dataset.key]; return; }
          const ok = await saveSetting(el.dataset.key, n);
          if (ok) { lastSettings[el.dataset.key] = n; haptic("light"); }
          else {
            el.classList.add("bad");
            setTimeout(() => el.classList.remove("bad"), 1200);
            el.value = lastSettings[el.dataset.key];
          }
        })
      );
      thresholds.dataset.built = "1";
    }
  }

  async function renderSettings() {
    ensureSettingsBuilt();
    try {
      const s = await api("/api/settings");
      lastSettings = s;
      document.getElementById("setting-language").value = s.language;
      document.getElementById("setting-mode").value = s.output_mode;
      document.getElementById("setting-confirm_before_send").classList.toggle("on", !!s.confirm_before_send);
      document.getElementById("setting-mini_app_enabled").classList.toggle("on", !!s.mini_app_enabled);
      for (const [key] of WATCHER_TOGGLES) {
        document.getElementById("setting-" + key).classList.toggle("on", !!s[key]);
      }
      for (const [key] of THRESHOLD_FIELDS) {
        document.getElementById("setting-" + key).value = s[key];
      }
    } catch (e) {
      toast(friendlyError(e), true);
    }
  }

  document.getElementById("setting-language").addEventListener("change", async (e) => {
    const prev = lastSettings.language;
    if (await saveSetting("language", e.target.value)) { lastSettings.language = e.target.value; haptic("light"); }
    else e.target.value = prev;
  });
  document.getElementById("setting-mode").addEventListener("change", async (e) => {
    const prev = lastSettings.output_mode;
    if (await saveSetting("output_mode", e.target.value)) { lastSettings.output_mode = e.target.value; haptic("light"); }
    else e.target.value = prev;
  });
  document.getElementById("setting-confirm_before_send").addEventListener("click", (e) => toggleSwitch(e.currentTarget, "confirm_before_send"));
  document.getElementById("setting-mini_app_enabled").addEventListener("click", (e) => toggleSwitch(e.currentTarget, "mini_app_enabled"));

  async function toggleSwitch(el, key) {
    const next = !el.classList.contains("on");
    if (key === "mini_app_enabled" && !next) {
      if (!confirm("Turn off the Mini App? This removes its menu button - you can turn it back on from /settings in the chat.")) return;
    }
    haptic("medium");
    el.classList.toggle("on", next);
    const ok = await saveSetting(key, next);
    if (ok) lastSettings[key] = next;
    else el.classList.toggle("on", !next);
  }

  async function saveSetting(key, value) {
    try {
      await api("/api/settings", { method: "POST", body: { key: key, value: value } });
      return true;
    } catch (e) {
      toast(friendlyError(e), true);
      notifyHaptic("error");
      return false;
    }
  }

  autogrow();
  syncRunBtn();
  openStatus();
})();
</script>
</body>
</html>
"""
