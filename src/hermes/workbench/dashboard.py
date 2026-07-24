"""Single-page HTML dashboard for the Hermes workbench.

Renders tasks, memory, traces and skills in one self-contained HTML page
served by :mod:`hermes.workbench.server`. The page fetches JSON from the
``/dashboard`` and ``/traces/{trace_id}`` endpoints and re-renders
client-side, so no template engine or frontend build step is needed.

Public surface:
    * :data:`DASHBOARD_HTML` — the full HTML document as a string
"""

from __future__ import annotations

__all__ = ["DASHBOARD_HTML"]


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hermes Workbench Dashboard</title>
  <style>
    :root {
      --bg: #0f1115;
      --panel: #161a22;
      --panel-2: #1d2230;
      --border: #2a3142;
      --fg: #e6e8ec;
      --muted: #8a93a6;
      --accent: #5b9dff;
      --green: #4ade80;
      --red: #f87171;
      --yellow: #fbbf24;
      --purple: #c084fc;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
    }
    header {
      padding: 16px 24px;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: 16px;
    }
    header h1 { margin: 0; font-size: 18px; font-weight: 600; }
    header .meta { color: var(--muted); font-size: 12px; }
    header .actions { margin-left: auto; display: flex; gap: 8px; }
    button {
      background: var(--panel-2);
      color: var(--fg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 12px;
      cursor: pointer;
    }
    button:hover { border-color: var(--accent); }
    button.primary { background: var(--accent); color: #0b0d12; border-color: var(--accent); }
    main {
      padding: 20px 24px;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
    }
    .panel.full { grid-column: 1 / -1; }
    .panel-header {
      padding: 10px 14px;
      background: var(--panel-2);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .panel-header h2 { margin: 0; font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--muted); }
    .panel-header .count { color: var(--accent); font-size: 12px; }
    .panel-body { padding: 12px 14px; max-height: 480px; overflow: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
    th { color: var(--muted); font-weight: 500; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }
    td.mono, .mono { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 10px;
      font-size: 11px;
      font-weight: 500;
    }
    .badge.ok { background: rgba(74,222,128,0.15); color: var(--green); }
    .badge.fail { background: rgba(248,113,113,0.15); color: var(--red); }
    .badge.pending { background: rgba(251,191,36,0.15); color: var(--yellow); }
    .badge.cancelled { background: rgba(138,147,166,0.15); color: var(--muted); }
    .badge.timeout { background: rgba(251,191,36,0.15); color: var(--yellow); }
    .badge.kind-loop { background: rgba(91,157,255,0.15); color: var(--accent); }
    .badge.kind-planner { background: rgba(192,132,252,0.15); color: var(--purple); }
    .badge.kind-generator { background: rgba(74,222,128,0.15); color: var(--green); }
    .badge.kind-evaluator { background: rgba(251,191,36,0.15); color: var(--yellow); }
    .badge.kind-note { background: rgba(138,147,166,0.15); color: var(--muted); }
    .trace-link {
      color: var(--accent);
      cursor: pointer;
      text-decoration: underline;
      font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
      font-size: 11px;
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 8px;
      margin-bottom: 12px;
    }
    .stat {
      background: var(--panel-2);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px 12px;
    }
    .stat .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
    .stat .value { font-size: 20px; font-weight: 600; margin-top: 4px; }
    .ep-summary { color: var(--fg); }
    .ep-details { color: var(--muted); font-size: 11px; margin-top: 2px; font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
    .ep-time { color: var(--muted); font-size: 11px; white-space: nowrap; }
    .empty { color: var(--muted); text-align: center; padding: 20px; font-style: italic; }
    .trace-list-item {
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      margin-bottom: 6px;
      cursor: pointer;
    }
    .trace-list-item:hover { border-color: var(--accent); }
    .modal-bg {
      position: fixed; top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0,0,0,0.6);
      display: none;
      z-index: 100;
    }
    .modal-bg.active { display: block; }
    .modal {
      position: fixed; top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      width: min(800px, 90vw);
      max-height: 80vh;
      overflow: auto;
      display: none;
      z-index: 101;
    }
    .modal.active { display: block; }
    .modal-header {
      padding: 12px 16px;
      background: var(--panel-2);
      border-bottom: 1px solid var(--border);
      display: flex; align-items: center; gap: 12px;
    }
    .modal-header h3 { margin: 0; font-size: 14px; }
    .modal-header .close { margin-left: auto; }
    .modal-body { padding: 12px 16px; }
    .refresh-spinner {
      display: inline-block;
      width: 12px; height: 12px;
      border: 2px solid var(--muted);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin-right: 6px;
      vertical-align: middle;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .autorenew { color: var(--green); font-size: 11px; }
  </style>
</head>
<body>
  <header>
    <h1>Hermes Workbench</h1>
    <span class="meta" id="last-updated">never</span>
    <span class="autorenew" id="autorenew-status" style="display:none;">auto-refresh on</span>
    <div class="actions">
      <button id="btn-refresh">Refresh</button>
      <button id="btn-autorenew" class="primary">Auto-refresh</button>
    </div>
  </header>
  <main>
    <div class="panel full">
      <div class="panel-body">
        <div class="stats-grid" id="stats-grid"></div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header"><h2>Tasks</h2><span class="count" id="task-count">0</span></div>
      <div class="panel-body" id="tasks-body"></div>
    </div>

    <div class="panel">
      <div class="panel-header"><h2>Recent Episodes</h2><span class="count" id="episode-count">0</span></div>
      <div class="panel-body" id="episodes-body"></div>
    </div>

    <div class="panel">
      <div class="panel-header"><h2>Facts (L1)</h2><span class="count" id="fact-count">0</span></div>
      <div class="panel-body" id="facts-body"></div>
    </div>

    <div class="panel">
      <div class="panel-header"><h2>Traces</h2><span class="count" id="trace-count">0</span></div>
      <div class="panel-body" id="traces-body"></div>
    </div>

    <div class="panel full">
      <div class="panel-header"><h2>Skills</h2><span class="count" id="skill-count">0</span></div>
      <div class="panel-body" id="skills-body"></div>
    </div>
  </main>

  <div class="modal-bg" id="modal-bg"></div>
  <div class="modal" id="modal">
    <div class="modal-header">
      <h3>Trace <span class="mono" id="modal-trace-id"></span></h3>
      <button class="close" id="modal-close">Close</button>
    </div>
    <div class="modal-body" id="modal-body"></div>
  </div>

<script>
  let autoTimer = null;
  const API = window.location.origin;

  function fmtTime(ts) {
    if (!ts) return "-";
    const d = new Date(ts * 1000);
    return d.toLocaleString();
  }
  function fmtRelative(ts) {
    if (!ts) return "-";
    const diff = (Date.now() / 1000) - ts;
    if (diff < 60) return Math.floor(diff) + "s ago";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
  }
  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, c => (
      {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]
    ));
  }
  function statusBadge(status) {
    const s = (status || "PENDING").toUpperCase();
    const cls = s === "COMPLETED" ? "ok" :
                s === "FAILED" ? "fail" :
                s === "PENDING" ? "pending" :
                s === "CANCELLED" ? "cancelled" :
                s === "TIMEOUT" ? "timeout" : "pending";
    return `<span class="badge ${cls}">${escapeHtml(s)}</span>`;
  }
  function kindBadge(kind) {
    return `<span class="badge kind-${escapeHtml(kind)}">${escapeHtml(kind)}</span>`;
  }

  async function fetchJson(url) {
    const token = localStorage.getItem("hermes_token") || "";
    const headers = {};
    if (token) headers["Authorization"] = "Bearer " + token;
    const resp = await fetch(API + url, { headers });
    if (!resp.ok) {
      throw new Error(`${resp.status} ${resp.statusText}`);
    }
    return resp.json();
  }

  async function loadDashboard() {
    const refreshBtn = document.getElementById("btn-refresh");
    refreshBtn.innerHTML = `<span class="refresh-spinner"></span>Refreshing`;
    try {
      const data = await fetchJson("/dashboard?task_limit=20&episode_limit=50&fact_limit=100");
      renderDashboard(data);
      document.getElementById("last-updated").textContent = "updated " + new Date().toLocaleTimeString();
    } catch (e) {
      document.getElementById("tasks-body").innerHTML = `<div class="empty">Error: ${escapeHtml(e.message)}</div>`;
    } finally {
      refreshBtn.textContent = "Refresh";
    }
  }

  function renderDashboard(data) {
    // Stats
    const totals = data.totals || {};
    const statsHtml = `
      <div class="stat"><div class="label">Tasks</div><div class="value">${totals.tasks || 0}</div></div>
      <div class="stat"><div class="label">Episodes</div><div class="value">${totals.episodes || 0}</div></div>
      <div class="stat"><div class="label">Facts</div><div class="value">${totals.facts || 0}</div></div>
      <div class="stat"><div class="label">Skills</div><div class="value">${totals.skills || 0}</div></div>
      <div class="stat"><div class="label">Traces</div><div class="value">${totals.traces || 0}</div></div>
    `;
    document.getElementById("stats-grid").innerHTML = statsHtml;

    // Tasks
    const tasks = data.tasks || [];
    document.getElementById("task-count").textContent = tasks.length;
    if (tasks.length === 0) {
      document.getElementById("tasks-body").innerHTML = `<div class="empty">No tasks yet</div>`;
    } else {
      const rows = tasks.map(t => `
        <tr>
          <td class="mono">${escapeHtml(t.task_id)}</td>
          <td>${statusBadge(t.status)}</td>
          <td>${escapeHtml(t.mode || "oneshot")}</td>
          <td>${(t.rounds || []).length}</td>
          <td>${fmtRelative(t.updated_at || t.created_at)}</td>
        </tr>
      `).join("");
      document.getElementById("tasks-body").innerHTML = `
        <table>
          <thead><tr><th>ID</th><th>Status</th><th>Mode</th><th>Rounds</th><th>Updated</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }

    // Episodes
    const episodes = data.episodes || [];
    document.getElementById("episode-count").textContent = episodes.length;
    if (episodes.length === 0) {
      document.getElementById("episodes-body").innerHTML = `<div class="empty">No episodes recorded</div>`;
    } else {
      const items = episodes.map(ep => {
        const tid = (ep.details || {}).trace_id;
        const tidHtml = tid
          ? `<span class="trace-link" data-trace="${escapeHtml(tid)}">${escapeHtml(tid)}</span>`
          : "";
        return `
          <div style="margin-bottom:8px;">
            <div>${kindBadge(ep.kind)} <span class="ep-summary">${escapeHtml(ep.summary)}</span> ${tidHtml}</div>
            <div class="ep-time">${fmtRelative(ep.created_at)} (${fmtTime(ep.created_at)})</div>
          </div>
        `;
      }).join("");
      document.getElementById("episodes-body").innerHTML = items;
    }

    // Facts
    const facts = data.facts || [];
    document.getElementById("fact-count").textContent = facts.length;
    if (facts.length === 0) {
      document.getElementById("facts-body").innerHTML = `<div class="empty">No facts stored</div>`;
    } else {
      const rows = facts.map(f => `
        <tr>
          <td class="mono">${escapeHtml(f.key)}</td>
          <td class="mono">${escapeHtml(JSON.stringify(f.value))}</td>
        </tr>
      `).join("");
      document.getElementById("facts-body").innerHTML = `
        <table>
          <thead><tr><th>Key</th><th>Value</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }

    // Traces
    const traces = data.traces || [];
    document.getElementById("trace-count").textContent = traces.length;
    if (traces.length === 0) {
      document.getElementById("traces-body").innerHTML = `<div class="empty">No traces yet (run a loop task to generate)</div>`;
    } else {
      const items = traces.map(t => `
        <div class="trace-list-item" data-trace="${escapeHtml(t.trace_id)}">
          <div>
            <span class="mono">${escapeHtml(t.trace_id)}</span>
            <span class="badge" style="background:rgba(91,157,255,0.15);color:var(--accent);">${t.count} eps</span>
            ${t.kinds.map(k => kindBadge(k)).join(" ")}
          </div>
          <div class="ep-time">last: ${fmtRelative(t.last_at)}</div>
        </div>
      `).join("");
      document.getElementById("traces-body").innerHTML = items;
    }

    // Skills
    const skills = data.skills || [];
    document.getElementById("skill-count").textContent = skills.length;
    if (skills.length === 0) {
      document.getElementById("skills-body").innerHTML = `<div class="empty">No skills discovered</div>`;
    } else {
      const rows = skills.map(s => `
        <tr>
          <td class="mono">${escapeHtml(s.name)}</td>
          <td>${escapeHtml(s.runtime)}</td>
          <td>${escapeHtml(s.description || "")}</td>
        </tr>
      `).join("");
      document.getElementById("skills-body").innerHTML = `
        <table>
          <thead><tr><th>Name</th><th>Runtime</th><th>Description</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      `;
    }

    // Bind trace-link clicks
    document.querySelectorAll("[data-trace]").forEach(el => {
      el.addEventListener("click", () => openTrace(el.dataset.trace));
    });
  }

  async function openTrace(traceId) {
    document.getElementById("modal-trace-id").textContent = traceId;
    document.getElementById("modal-body").innerHTML = `<div class="empty">Loading...</div>`;
    document.getElementById("modal-bg").classList.add("active");
    document.getElementById("modal").classList.add("active");
    try {
      const data = await fetchJson("/traces/" + encodeURIComponent(traceId));
      const eps = data.episodes || [];
      if (eps.length === 0) {
        document.getElementById("modal-body").innerHTML = `<div class="empty">No episodes found for trace ${escapeHtml(traceId)}</div>`;
        return;
      }
      const items = eps.map(ep => {
        const details = JSON.stringify(ep.details || {}, null, 2);
        return `
          <div style="margin-bottom:12px;padding:8px;background:var(--panel-2);border-radius:6px;">
            <div>${kindBadge(ep.kind)} <strong>${escapeHtml(ep.summary)}</strong></div>
            <div class="ep-time">${fmtTime(ep.created_at)}</div>
            <pre class="ep-details" style="margin-top:6px;white-space:pre-wrap;">${escapeHtml(details)}</pre>
          </div>
        `;
      }).join("");
      document.getElementById("modal-body").innerHTML = `
        <div style="margin-bottom:8px;color:var(--muted);">${eps.length} episode(s) in this trace</div>
        ${items}
      `;
    } catch (e) {
      document.getElementById("modal-body").innerHTML = `<div class="empty">Error: ${escapeHtml(e.message)}</div>`;
    }
  }

  function closeModal() {
    document.getElementById("modal-bg").classList.remove("active");
    document.getElementById("modal").classList.remove("active");
  }

  document.getElementById("btn-refresh").addEventListener("click", loadDashboard);
  document.getElementById("btn-autorenew").addEventListener("click", () => {
    const btn = document.getElementById("btn-autorenew");
    const status = document.getElementById("autorenew-status");
    if (autoTimer) {
      clearInterval(autoTimer);
      autoTimer = null;
      btn.textContent = "Auto-refresh";
      btn.classList.add("primary");
      status.style.display = "none";
    } else {
      autoTimer = setInterval(loadDashboard, 5000);
      btn.textContent = "Stop auto";
      btn.classList.remove("primary");
      status.style.display = "inline";
    }
  });
  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("modal-bg").addEventListener("click", closeModal);

  loadDashboard();
</script>
</body>
</html>
"""
