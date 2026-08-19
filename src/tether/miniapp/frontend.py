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
    font-size: 13.5px; line-height: 1.4; text-align: center; z-index: 50;
    transition: opacity 220ms var(--ease-soft), transform 260ms var(--ease);
  }
  #toast.show { opacity: 1; transform: translate(-50%, 0); }
  #toast.bad { box-shadow: var(--shadow), inset 0 0 0 1px var(--danger); color: var(--danger); }

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
      <span class="mark"><svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2.6c.5 0 .9.4.9.9v6.1l4.3-4.3a.9.9 0 1 1 1.3 1.3l-4.3 4.3h6.1a.9.9 0 0 1 0 1.8h-6.1l4.3 4.3a.9.9 0 1 1-1.3 1.3l-4.3-4.3v6.1a.9.9 0 1 1-1.8 0v-6.1l-4.3 4.3a.9.9 0 0 1-1.3-1.3l4.3-4.3H3.5a.9.9 0 0 1 0-1.8h6.1L5.3 6.6a.9.9 0 0 1 1.3-1.3l4.3 4.3V3.5c0-.5.4-.9.9-.9z"/></svg></span>
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
    <button class="tab" data-view="settings">
      <span class="ico"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2.2"/><circle cx="10" cy="17" r="2.2"/></svg></span>Settings
    </button>
  </nav>
</div>

<div id="toast" role="status" aria-live="polite"></div>

<script>
(function () {
  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = tg && tg.initData;

  // ---- security gate -------------------------------------------------
  // No initData means this page was not opened from a real Telegram
  // session. Bail out before anything else runs: #gate stays visible,
  // #app stays hidden, and not a single /api/* request is ever made.
  if (!initData) {
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
    const headers = Object.assign({ "Authorization": "tma " + initData }, opts.headers || {});
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
    if (m.indexOf("http_401") === 0 || m === "expired" || m === "bad_signature")
      return "This session expired. Close and reopen the Mini App.";
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
    settings: ["Settings", "Tune how tether behaves"],
  };
  const views = { status: renderStatus, sessions: renderSessions, transcript: openTranscript, settings: renderSettings };
  let currentView = "status";
  let transcriptTimer = null;

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
      document.getElementById("main").scrollTop = name === "transcript" ? 1e7 : 0;
      views[name]();
    });
  });
  document.getElementById("screen-sub").textContent = TITLES.status[1];

  // ---- status --------------------------------------------------------
  function tile(k, v, cls) {
    return '<div class="tile ' + (cls || "") + '"><div class="k">' + esc(k) + '</div><div class="v">' + v + "</div></div>";
  }

  async function renderStatus() {
    const body = document.getElementById("status-body");
    try {
      const s = await api("/api/status");
      const pill = document.getElementById("target-pill");
      document.getElementById("target-name").textContent = s.target || "claude";
      pill.hidden = false;
      pill.classList.add("live");

      const cpuHot = s.cpu_c != null && s.cpu_c >= 85;
      const gpuHot = s.gpu_c != null && s.gpu_c >= 85;
      body.innerHTML =
        '<div class="hero">' +
          '<div class="eyebrow">' + esc(s.target || "claude") + "</div>" +
          '<div class="model">' + esc(s.model || "Unknown model") + "</div>" +
          '<div class="meta">' + esc(s.effort || "default") + " effort &middot; " + esc(s.output_mode || "live") + " output</div>" +
        "</div>" +
        '<div class="tiles">' +
          tile("CPU", s.cpu_c != null ? esc(s.cpu_c) + "<small>&deg;C</small>" : "n/a", s.cpu_c == null ? "muted" : (cpuHot ? "hot" : "")) +
          tile("GPU", s.gpu_c != null ? esc(s.gpu_c) + "<small>&deg;C</small>" : "n/a", s.gpu_c == null ? "muted" : (gpuHot ? "hot" : "")) +
          tile("Fan", s.fan != null ? esc(s.fan) + "<small>%</small>" : "n/a", s.fan == null ? "muted" : "") +
          tile("Output", esc(s.output_mode || "live"), "muted") +
        "</div>" +
        '<div class="card"><div class="row"><span class="label">Effort</span><span class="value">' + esc(s.effort || "unknown") + "</span></div>" +
        '<div class="row"><span class="label">Target app</span><span class="value">' + esc(s.target || "claude") + "</span></div></div>";
    } catch (e) {
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
  renderStatus();
})();
</script>
</body>
</html>
"""
