from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .report import build_run_state


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Polymarket Paper Desk</title>
  <style>
    :root {
      color-scheme: dark;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f1012;
      color: #e7ebef;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: #0f1012; color: #e7ebef; }
    header {
      position: sticky; top: 0; z-index: 2;
      padding: 14px 20px;
      background: #121315;
      border-bottom: 1px solid #2d3136;
      display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap;
    }
    h1 { font-size: 18px; margin: 0; letter-spacing: 0; font-weight: 720; }
    main { padding: 16px 20px 28px; display: grid; gap: 14px; }
    .deck { display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 10px; }
    .workspace { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(320px, .8fr); gap: 14px; align-items: start; }
    .stack { display: grid; gap: 14px; }
    .panel, .metric-card {
      background: #17191d;
      border: 1px solid #30343a;
      border-radius: 8px;
      box-shadow: 0 10px 28px rgba(0,0,0,.22);
    }
    .panel { padding: 14px; }
    .metric-card { padding: 12px; min-height: 82px; }
    .metric { font-size: 28px; font-weight: 760; margin-top: 7px; font-variant-numeric: tabular-nums; }
    .label { font-size: 11px; color: #98a2ad; text-transform: uppercase; font-weight: 720; }
    .subtle { color: #98a2ad; font-size: 12px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
    .badge {
      border: 1px solid transparent;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 11px;
      font-weight: 760;
      display: inline-flex; align-items: center; gap: 6px;
      white-space: nowrap;
    }
    .completed { background: rgba(50, 208, 127, .13); border-color: rgba(50, 208, 127, .35); color: #66e0a2; }
    .active { background: rgba(77, 164, 255, .13); border-color: rgba(77, 164, 255, .35); color: #80bdff; }
    .stale { background: rgba(233, 181, 72, .15); border-color: rgba(233, 181, 72, .38); color: #f2cb73; }
    .missing { background: rgba(255, 92, 92, .13); border-color: rgba(255, 92, 92, .35); color: #ff9a9a; }
    .polling { background: rgba(190, 145, 255, .13); border-color: rgba(190, 145, 255, .35); color: #d0b4ff; }
    .panel-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 12px; }
    .market-board { display: grid; gap: 12px; }
    .market-card {
      background: #1d2025;
      border: 1px solid #343941;
      border-radius: 8px;
      overflow: hidden;
    }
    .market-top {
      padding: 12px 12px 10px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      border-bottom: 1px solid #333941;
      background: linear-gradient(180deg, #20242a 0%, #1b1e23 100%);
    }
    .market-name { font-weight: 740; line-height: 1.28; }
    .market-meta { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; align-content: start; }
    .outcome-row {
      display: grid;
      grid-template-columns: minmax(160px, .95fr) repeat(4, minmax(66px, .28fr)) minmax(260px, 1fr);
      gap: 10px;
      padding: 12px;
      align-items: center;
      border-top: 1px solid #2b3037;
    }
    .outcome-row:first-of-type { border-top: 0; }
    .outcome-name { color: #f0c96a; font-weight: 780; font-size: 14px; }
    .stat { background: #14161a; border: 1px solid #2b3037; border-radius: 6px; padding: 8px 9px; min-height: 54px; }
    .stat strong { display: block; margin-top: 4px; font-size: 17px; font-variant-numeric: tabular-nums; }
    .chart-wrap { min-width: 0; }
    .chart-title { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 5px; }
    .spark { width: 100%; height: 86px; display: block; background: #101215; border: 1px solid #343941; border-radius: 7px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th, td { text-align: left; padding: 8px 7px; border-bottom: 1px solid #2a2f36; vertical-align: top; }
    th { color: #9aa5b1; font-size: 10px; text-transform: uppercase; }
    tr:last-child td { border-bottom: 0; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; color: #bac4cf; }
    .empty { padding: 18px; color: #98a2ad; border: 1px dashed #3a4048; border-radius: 8px; text-align: center; }
    @media (max-width: 1150px) {
      .deck { grid-template-columns: repeat(3, minmax(120px, 1fr)); }
      .workspace { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      header { padding: 12px 14px; }
      main { padding: 12px 14px 22px; }
      .deck { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
      .market-top { grid-template-columns: 1fr; }
      .market-meta { justify-content: flex-start; }
      .outcome-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .chart-wrap { grid-column: 1 / -1; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Polymarket Paper Desk</h1>
      <div class="subtle" id="subtitle"></div>
    </div>
    <div id="badges"></div>
  </header>
  <main>
    <section class="deck" id="metrics"></section>
    <section class="workspace">
      <div class="panel">
        <div class="panel-head">
          <div>
            <div class="label">Watchlist</div>
            <div class="subtle">PUBLIC CLOB POLLING</div>
          </div>
          <span class="badge polling">JSONL replay</span>
        </div>
        <div class="market-board" id="market-board"></div>
      </div>
      <div class="stack">
        <div class="panel">
          <div class="panel-head"><div class="label">PnL Components</div></div>
          <table><tbody id="pnl"></tbody></table>
        </div>
        <div class="panel">
          <div class="panel-head"><div class="label">Risk Events</div></div>
          <table><tbody id="risks"></tbody></table>
        </div>
        <div class="panel">
          <div class="panel-head"><div class="label">Skipped Markets</div></div>
          <table><tbody id="skips"></tbody></table>
        </div>
      </div>
    </section>
    <section class="workspace">
      <div class="panel">
        <div class="panel-head"><div class="label">Latest Books</div></div>
        <table><thead><tr><th>Market / Outcome</th><th>Bid</th><th>Ask</th><th>Mid</th><th>State</th></tr></thead><tbody id="books"></tbody></table>
      </div>
      <div class="panel">
        <div class="panel-head"><div class="label">Recent Fills</div></div>
        <table><thead><tr><th>Side</th><th>Price</th><th>Size</th><th>Evidence</th></tr></thead><tbody id="fills"></tbody></table>
      </div>
    </section>
  </main>
  <script>
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const td = (value) => `<td>${value ?? ""}</td>`;
    function displayValue(value) {
      if (value === null || value === undefined) return '—';
      if (Array.isArray(value)) return value.length ? value.map(esc).join(', ') : 'none';
      if (typeof value === 'object') return Object.keys(value).length ? `<code>${esc(JSON.stringify(value))}</code>` : 'none';
      return esc(value);
    }
    const rows = (obj) => Object.entries(obj || {}).sort().map(([k,v]) => `<tr><td><code>${esc(k)}</code></td><td>${displayValue(v)}</td></tr>`).join("") || '<tr><td colspan="2" class="subtle">None</td></tr>';
    function badge(text, cls) { return `<span class="badge ${cls}">${esc(text)}</span>`; }
    function fmt(value) {
      if (value === null || value === undefined || value === '') return '—';
      const n = Number(value);
      if (!Number.isFinite(n)) return esc(value);
      return n.toFixed(3).replace(/0+$/,'').replace(/\.$/,'');
    }
    function compact(value) {
      const n = Number(value || 0);
      if (Math.abs(n) >= 1000000) return (n / 1000000).toFixed(1) + 'M';
      if (Math.abs(n) >= 1000) return (n / 1000).toFixed(1) + 'K';
      return fmt(n);
    }
    function shortToken(token) { return token ? `${String(token).slice(0, 7)}...${String(token).slice(-4)}` : ''; }
    function spark(points) {
      const values = (points || []).map(p => p.midpoint).filter(v => v !== null && v !== undefined).map(Number);
      if (values.length < 2) {
        return '<svg class="spark" viewBox="0 0 360 86"><text x="180" y="46" text-anchor="middle" font-size="12" fill="#98a2ad">waiting for history</text></svg>';
      }
      const min = Math.min(...values), max = Math.max(...values), rawSpan = max - min, span = Math.max(rawSpan, 0.001);
      const coords = values.map((v, i) => {
        const x = 10 + (i / (values.length - 1)) * 340;
        const y = rawSpan < 0.0005 ? 43 : 72 - ((v - min) / span) * 58;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(' ');
      const first = values[0], last = values[values.length - 1], change = last - first;
      const stroke = change > 0.0005 ? '#32d07f' : change < -0.0005 ? '#ff6b6b' : '#f0c96a';
      const status = rawSpan < 0.0005 ? 'flat' : `${change >= 0 ? '+' : ''}${fmt(change)}`;
      const lastY = rawSpan < 0.0005 ? 43 : 72 - ((last - min) / span) * 58;
      return `<svg class="spark" viewBox="0 0 360 86" preserveAspectRatio="none">
        <line x1="10" y1="14" x2="350" y2="14" stroke="#252b32" stroke-width="1"/>
        <line x1="10" y1="43" x2="350" y2="43" stroke="#252b32" stroke-width="1"/>
        <line x1="10" y1="72" x2="350" y2="72" stroke="#252b32" stroke-width="1"/>
        <polyline points="${coords}" fill="none" stroke="${stroke}" stroke-width="2.4"/>
        <circle cx="350" cy="${lastY.toFixed(1)}" r="3.4" fill="${stroke}"/>
        <text x="14" y="13" font-size="10" fill="#98a2ad">${fmt(max)}</text>
        <text x="14" y="80" font-size="10" fill="#98a2ad">${fmt(min)}</text>
        <text x="348" y="13" text-anchor="end" font-size="10" fill="${stroke}">${status}</text>
      </svg>`;
    }
    function metric(label, value, cls='') {
      return `<div class="metric-card"><div class="label">${esc(label)}</div><div class="metric ${cls}">${esc(value ?? 0)}</div></div>`;
    }
    function marketCard(m) {
      const outcomes = (m.outcomes || []).map(o => `
        <div class="outcome-row">
          <div>
            <div class="outcome-name">${esc(o.outcome)}</div>
            <div class="subtle">Token <span class="mono">${esc(shortToken(o.token_id))}</span></div>
          </div>
          <div class="stat"><div class="label">Bid</div><strong>${fmt(o.best_bid)}</strong></div>
          <div class="stat"><div class="label">Ask</div><strong>${fmt(o.best_ask)}</strong></div>
          <div class="stat"><div class="label">Mid</div><strong>${fmt(o.midpoint)}</strong></div>
          <div class="stat"><div class="label">Spread</div><strong>${fmt(o.spread)}</strong></div>
          <div class="chart-wrap">
            <div class="chart-title"><span class="label">Mid Price History</span>${badge(o.state || 'missing', o.state === 'live/polled' ? 'completed' : 'missing')}</div>
            ${spark(o.history)}
          </div>
        </div>`).join('');
      return `<article class="market-card">
        <div class="market-top">
          <div>
            <div class="market-name">${esc(m.question || m.slug || 'Unknown market')}</div>
            <div class="subtle">${esc(m.slug || '')}</div>
          </div>
          <div class="market-meta">
            ${badge(`quotes ${m.quote_count ?? 0}`, 'active')}
            ${badge(`fills ${m.fill_count ?? 0}`, m.fill_count ? 'completed' : 'stale')}
            ${badge(`risk ${m.risk_event_count ?? 0}`, m.risk_event_count ? 'stale' : 'completed')}
            ${badge(`vol ${compact(m.volume_24h)}`, 'polling')}
          </div>
        </div>
        ${outcomes}
      </article>`;
    }
    async function load() {
      const state = await fetch('/state.json', {cache: 'no-store'}).then(r => r.json());
      const counts = state.counts || {};
      document.getElementById('subtitle').textContent = `${state.data_dir || ''} · ${state.generated_at || ''}`;
      document.getElementById('badges').innerHTML = [
        badge(state.status, state.status === 'completed' ? 'completed' : 'active'),
        state.fallback_mode ? badge(state.fallback_mode, 'polling') : badge('missing mode', 'missing'),
        state.observation_mode ? badge('observation', 'stale') : ''
      ].join(' ');
      document.getElementById('metrics').innerHTML = [
        metric('Watched', counts.markets_watched),
        metric('Quotes', counts.quotes),
        metric('Fills', counts.fills),
        metric('Books', counts.books),
        metric('Risk Events', counts.risk_events),
        metric('Mark PnL', fmt(state.pnl?.mark_to_mid_pnl))
      ].join('');
      document.getElementById('market-board').innerHTML = (state.market_summaries || []).map(marketCard).join('') || '<div class="empty">No selected markets.</div>';
      document.getElementById('pnl').innerHTML = rows(state.pnl);
      document.getElementById('risks').innerHTML = rows(state.risk_counts);
      document.getElementById('skips').innerHTML = rows(state.skipped_counts);
      document.getElementById('books').innerHTML = Object.values(state.latest_books || {}).slice(-40).map(b => {
        const name = b.display_name || `${b.market_id || 'Unknown'} - ${b.outcome || shortToken(b.token_id)}`;
        return `<tr>${td(`<div>${esc(name)}</div><div class="subtle">Token <span class="mono">${esc(shortToken(b.token_id))}</span></div>`)}${td(fmt(b.best_bid))}${td(fmt(b.best_ask))}${td(fmt(b.midpoint))}${td((b.best_bid == null || b.best_ask == null) ? badge('missing','missing') : badge('live/polled','completed'))}</tr>`;
      }).join('') || '<tr><td colspan="5" class="subtle">No books.</td></tr>';
      document.getElementById('fills').innerHTML = (state.recent_fills || []).map(f => `<tr>${td(esc(f.side))}${td(fmt(f.price))}${td(fmt(f.size))}${td(`<code>${esc(f.evidence_event_id || '')}</code>`)}</tr>`).join('') || '<tr><td colspan="4" class="subtle">No conservative fills.</td></tr>';
    }
    load();
    setInterval(load, 5000);
  </script>
</body>
</html>
"""


def serve_dashboard(data_dir: Path, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(INDEX_HTML.encode("utf-8"))
                return
            if path == "/state.json":
                state = build_run_state(data_dir)
                body = json.dumps(state, indent=2, sort_keys=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Serving read-only paper dashboard at http://{host}:{port}", flush=True)
    server.serve_forever()
