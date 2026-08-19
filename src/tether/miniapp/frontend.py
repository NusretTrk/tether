"""
The Mini App's entire client is one self-contained HTML string - no
build step, no framework, matching the "don't add resource weight"
constraint this feature was built under. The only external resource is
Telegram's own official WebApp SDK script, which is required for a Mini
App to function at all (it's what supplies initData, theme colors, and
haptics) and isn't a third-party dependency in the supply-chain sense.

Security note: a visitor who finds the ngrok URL and loads it in a plain
browser (not through Telegram) gets exactly this shell and nothing else -
`Telegram.WebApp.initData` is only ever populated by a genuine Telegram
WebApp launch, so the guard at the top of `boot()` stops everything
before a single API call is made. The real auth boundary is server-side
(see miniapp/auth.py) - this client-side guard is a courtesy, not the
security control.
"""

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>tether</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root {
    --bg: #ffffff; --text: #1c1c1e; --hint: #8e8e93; --link: #007aff;
    --button: #007aff; --button-text: #ffffff; --secondary-bg: #f2f2f7;
    --section-separator: rgba(60,60,67,0.29);
    --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body { margin: 0; padding: 0; height: 100%; overscroll-behavior-y: none; }
  body {
    background: var(--bg); color: var(--text);
    font: 15px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    display: flex; flex-direction: column;
  }
  #gate { display: flex; align-items: center; justify-content: center; height: 100vh; padding: 24px; text-align: center; color: var(--hint); }
  #app { display: none; flex-direction: column; height: 100vh; }
  header { padding: 14px 16px 10px; font-size: 20px; font-weight: 700; }
  main { flex: 1; overflow-y: auto; padding: 0 16px 12px; }
  .card {
    background: var(--secondary-bg); border-radius: 14px; padding: 14px 16px;
    margin-bottom: 10px; transition: transform 120ms var(--ease-out), opacity 200ms ease;
  }
  .row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; }
  .row + .row { border-top: 0.5px solid var(--section-separator); }
  .label { color: var(--text); }
  .value { color: var(--hint); font-variant-numeric: tabular-nums; }
  .hint { color: var(--hint); font-size: 13px; margin: 4px 2px 12px; }
  button, select {
    font: inherit; border: none; border-radius: 12px; padding: 10px 14px;
    background: var(--button); color: var(--button-text); cursor: pointer;
    transition: transform 140ms var(--ease-out), opacity 140ms ease;
  }
  button:active { transform: scale(0.97); }
  button.secondary { background: var(--secondary-bg); color: var(--text); }
  button.danger { background: #ff3b30; color: #fff; }
  button:disabled { opacity: 0.5; cursor: default; transform: none; }
  .switch { position: relative; width: 46px; height: 28px; border-radius: 14px; background: var(--section-separator); transition: background 160ms ease; flex-shrink: 0; }
  .switch::after { content: ""; position: absolute; top: 2px; left: 2px; width: 24px; height: 24px; border-radius: 50%; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,0.2); transition: transform 160ms var(--ease-out); }
  .switch.on { background: #34c759; }
  .switch.on::after { transform: translateX(18px); }
  .tabbar { display: flex; border-top: 0.5px solid var(--section-separator); padding-bottom: env(safe-area-inset-bottom); }
  .tab { flex: 1; text-align: center; padding: 8px 0 6px; background: none; border-radius: 0; color: var(--hint); font-size: 11px; }
  .tab.active { color: var(--link); }
  .tab .icon { font-size: 20px; display: block; }
  .event { padding: 8px 0; border-top: 0.5px solid var(--section-separator); }
  .event:first-child { border-top: none; }
  .event .meta { font-size: 11px; color: var(--hint); margin-bottom: 2px; }
  .event .text { white-space: pre-wrap; word-break: break-word; }
  .event.error .text { color: #ff3b30; }
  .empty { color: var(--hint); text-align: center; padding: 40px 16px; }
  .spinner { width: 20px; height: 20px; border-radius: 50%; border: 2px solid var(--section-separator); border-top-color: var(--link); animation: spin 700ms linear infinite; margin: 24px auto; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .view { display: none; }
  .view.active { display: block; }
</style>
</head>
<body>

<div id="gate">Open this from the tether bot in Telegram.</div>

<div id="app">
  <header id="header">tether</header>
  <main>
    <div class="view active" id="view-status">
      <div class="card" id="status-card"><div class="spinner"></div></div>
      <p class="hint" id="status-hint"></p>
    </div>
    <div class="view" id="view-sessions">
      <div id="sessions-list"><div class="spinner"></div></div>
    </div>
    <div class="view" id="view-transcript">
      <div id="transcript-list"><div class="spinner"></div></div>
    </div>
    <div class="view" id="view-settings">
      <div class="card">
        <div class="row"><span class="label">Language</span>
          <select id="setting-language">
            <option value="en">English</option><option value="tr">Türkçe</option>
            <option value="de">Deutsch</option><option value="es">Español</option>
          </select>
        </div>
        <div class="row"><span class="label">Output mode</span>
          <select id="setting-mode">
            <option value="live">live</option><option value="summary">summary</option>
            <option value="quiet">quiet</option><option value="verbose">verbose</option>
          </select>
        </div>
        <div class="row"><span class="label">Confirm before send</span>
          <div class="switch" id="setting-confirm" data-key="confirm_before_send"></div>
        </div>
        <div class="row"><span class="label">Mini App</span>
          <div class="switch" id="setting-miniapp" data-key="mini_app_enabled"></div>
        </div>
      </div>
      <p class="hint">Turning the Mini App off removes this menu button - reopen it any time from /menu, or /start refreshes the button if it looks stale.</p>
    </div>
  </main>
  <nav class="tabbar">
    <button class="tab active" data-view="status"><span class="icon">📊</span>Status</button>
    <button class="tab" data-view="sessions"><span class="icon">📋</span>Sessions</button>
    <button class="tab" data-view="transcript"><span class="icon">💬</span>Transcript</button>
    <button class="tab" data-view="settings"><span class="icon">⚙️</span>Settings</button>
  </nav>
</div>

<script>
(function () {
  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = tg && tg.initData;

  if (!initData) {
    return; // #gate stays visible, #app stays hidden - nothing else runs
  }

  document.getElementById("gate").style.display = "none";
  document.getElementById("app").style.display = "flex";

  tg.ready();
  tg.expand();
  applyTheme();
  tg.onEvent("themeChanged", applyTheme);

  function applyTheme() {
    const p = tg.themeParams || {};
    const root = document.documentElement.style;
    const map = {
      bg_color: "--bg", text_color: "--text", hint_color: "--hint",
      link_color: "--link", button_color: "--button", button_text_color: "--button-text",
      secondary_bg_color: "--secondary-bg",
    };
    for (const [k, v] of Object.entries(map)) if (p[k]) root.setProperty(v, p[k]);
  }

  function haptic(kind) {
    if (tg.HapticFeedback) tg.HapticFeedback.impactOccurred(kind || "light");
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
    if (e.message === "too_many_failed_attempts") return "Temporarily locked out after repeated failed attempts. Try again in a few minutes.";
    if (e.message && e.message.startsWith("http")) return "tether isn't reachable right now - try again in a moment, or send /start in the chat.";
    return "Couldn't load this - try again in a moment, or send /start in the chat.";
  }

  // ---- tabs ----
  const views = { status: renderStatus, sessions: renderSessions, transcript: renderTranscript, settings: renderSettings };
  let transcriptTimer = null;

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      haptic("light");
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("view-" + btn.dataset.view).classList.add("active");
      clearInterval(transcriptTimer);
      views[btn.dataset.view]();
    });
  });

  // ---- status ----
  async function renderStatus() {
    const card = document.getElementById("status-card");
    try {
      const s = await api("/api/status");
      card.innerHTML =
        row("Model", s.model || "unknown") +
        row("Effort", s.effort || "unknown") +
        row("Target", s.target) +
        row("Output mode", s.output_mode) +
        row("CPU", s.cpu_c != null ? s.cpu_c + "°C" : "n/a") +
        row("GPU", s.gpu_c != null ? s.gpu_c + "°C" : "n/a");
    } catch (e) {
      card.innerHTML = '<p class="empty">' + friendlyError(e) + "</p>";
    }
  }

  function row(label, value) {
    return '<div class="row"><span class="label">' + label + '</span><span class="value">' + esc(String(value)) + "</span></div>";
  }

  // ---- sessions ----
  async function renderSessions() {
    const list = document.getElementById("sessions-list");
    try {
      const { sessions } = await api("/api/sessions");
      if (!sessions.length) { list.innerHTML = '<p class="empty">No sessions found.</p>'; return; }
      list.innerHTML = sessions.map((s) =>
        '<div class="card row"><span class="label">' + (s.running ? "🟢 " : "⚪ ") + esc(s.name) +
        '</span><button class="secondary" data-switch="' + esc(s.name) + '">Switch</button></div>'
      ).join("");
      list.querySelectorAll("[data-switch]").forEach((btn) => btn.addEventListener("click", async () => {
        haptic("medium");
        btn.disabled = true;
        try { await api("/api/sessions/switch", { method: "POST", body: { name: btn.dataset.switch } }); }
        catch (e) { alert(friendlyError(e)); }
        btn.disabled = false;
      }));
    } catch (e) {
      list.innerHTML = '<p class="empty">' + friendlyError(e) + "</p>";
    }
  }

  // ---- transcript (polls while this tab is visible) ----
  async function renderTranscript() {
    const list = document.getElementById("transcript-list");
    async function load() {
      try {
        const { events } = await api("/api/transcript");
        if (!events.length) { list.innerHTML = '<p class="empty">Nothing yet.</p>'; return; }
        list.innerHTML = events.map((e) =>
          '<div class="event' + (e.is_error ? " error" : "") + '"><div class="meta">' +
          esc(e.type) + (e.tool_name ? " · " + esc(e.tool_name) : "") +
          '</div><div class="text">' + esc(e.text || "") + "</div></div>"
        ).join("");
      } catch (e) {
        list.innerHTML = '<p class="empty">' + friendlyError(e) + "</p>";
      }
    }
    await load();
    transcriptTimer = setInterval(() => { if (document.visibilityState === "visible") load(); }, 3000);
  }

  // ---- settings ----
  async function renderSettings() {
    try {
      const s = await api("/api/settings");
      document.getElementById("setting-language").value = s.language;
      document.getElementById("setting-mode").value = s.output_mode;
      document.getElementById("setting-confirm").classList.toggle("on", !!s.confirm_before_send);
      document.getElementById("setting-miniapp").classList.toggle("on", !!s.mini_app_enabled);
    } catch (e) {
      alert(friendlyError(e));
    }
  }

  document.getElementById("setting-language").addEventListener("change", (e) => saveSetting("language", e.target.value));
  document.getElementById("setting-mode").addEventListener("change", (e) => saveSetting("output_mode", e.target.value));
  document.getElementById("setting-confirm").addEventListener("click", (e) => toggleSwitch(e.currentTarget, "confirm_before_send"));
  document.getElementById("setting-miniapp").addEventListener("click", (e) => toggleSwitch(e.currentTarget, "mini_app_enabled"));

  function toggleSwitch(el, key) {
    haptic("medium");
    const next = !el.classList.contains("on");
    if (key === "mini_app_enabled" && !next) {
      if (!confirm("Turn off the Mini App? This removes its menu button - you can turn it back on from /settings in the chat.")) return;
    }
    el.classList.toggle("on", next);
    saveSetting(key, next);
  }

  async function saveSetting(key, value) {
    try { await api("/api/settings", { method: "POST", body: { key, value } }); }
    catch (e) { alert(friendlyError(e)); }
  }

  function esc(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  renderStatus();
})();
</script>
</body>
</html>
"""
