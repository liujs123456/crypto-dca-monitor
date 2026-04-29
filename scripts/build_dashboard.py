#!/usr/bin/env python3
"""Build a single-page static dashboard at docs/index.html.

Reads state/btc_state.json + state/weekly_snapshots.json. Renders:
  - current price, ladder state, distance to each tier
  - 26-week rolling chart of total assets, BTC held, BTC price (Chart.js CDN)
  - last check timestamp

Run after weekly snapshot commit, or anytime via workflow_dispatch.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import ladder

STATE_PATH = ROOT / "state" / "btc_state.json"
SNAP_PATH = ROOT / "state" / "weekly_snapshots.json"
OUT_PATH = ROOT / "docs" / "index.html"


def load_json(p: Path, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def main() -> int:
    state = load_json(STATE_PATH, {})
    snaps = load_json(SNAP_PATH, [])

    cur_price = state.get("last_price") or 0
    ref = state.get("last_ref") or 79500
    cur_tier = state.get("tier", "GREEN")
    armed = state.get("armed", {})
    last_check = state.get("last_check_utc", "—")

    prices = ladder.tier_prices(ref) if ref else {}
    tier_rows = []
    for name, factor, amt in ladder.TIER_CONFIG:
        p = prices.get(name, 0)
        dist_pct = (cur_price / p - 1) * 100 if p and cur_price else 0
        is_armed = armed.get(name, True)
        badge = "🟢 armed" if is_armed else "🔒 fired"
        tier_rows.append(
            f"<tr><td>{name}</td><td>${p:,.0f}</td><td>{dist_pct:+.1f}%</td>"
            f"<td>${amt}</td><td>{badge}</td></tr>"
        )

    chart_labels = [s.get("ts_utc", "")[:10] for s in snaps]
    chart_assets = [s.get("total_assets", 0) for s in snaps]
    chart_btc_px = [s.get("btc_price", 0) for s in snaps]
    chart_btc_held = [s.get("btc_held", 0) for s in snaps]

    state_color = {
        "GREEN": "#10b981", "WATCH": "#eab308",
        "T1": "#f97316", "T2": "#f97316",
        "T3": "#ef4444", "T4": "#dc2626",
    }.get(cur_tier, "#10b981")

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>BTC DCA Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0f172a; color: #e2e8f0;
    margin: 0; padding: 20px; max-width: 1100px; margin-inline: auto;
  }}
  h1 {{ margin: 0 0 4px; font-size: 24px; }}
  .subtitle {{ color: #94a3b8; font-size: 13px; margin-bottom: 24px; }}
  .card {{
    background: #1e293b; border-radius: 12px; padding: 20px;
    margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,.3);
  }}
  .price-row {{ display: flex; gap: 24px; flex-wrap: wrap; align-items: baseline; }}
  .price {{ font-size: 36px; font-weight: 700; }}
  .ref {{ color: #94a3b8; font-size: 14px; }}
  .state-badge {{
    display: inline-block; padding: 4px 12px; border-radius: 6px;
    background: {state_color}; color: white; font-weight: 600; font-size: 14px;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #334155; }}
  th {{ color: #94a3b8; font-weight: 500; }}
  canvas {{ max-height: 280px; }}
  .footer {{ color: #64748b; font-size: 11px; text-align: center; margin-top: 24px; }}
</style>
</head>
<body>
  <h1>BTC DCA Dashboard</h1>
  <div class="subtitle">Last update (UTC): {last_check}</div>

  <div class="card">
    <div class="price-row">
      <div class="price">${cur_price:,.0f}</div>
      <div class="ref">REF (30d high): ${ref:,.0f}</div>
      <div><span class="state-badge">{cur_tier}</span></div>
    </div>
  </div>

  <div class="card">
    <h3 style="margin-top:0">Ladder Tiers</h3>
    <table>
      <thead><tr><th>Tier</th><th>Trigger</th><th>距当前</th><th>加仓</th><th>状态</th></tr></thead>
      <tbody>
        {"".join(tier_rows)}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h3 style="margin-top:0">Total Assets (26 weeks)</h3>
    <canvas id="assetsChart"></canvas>
  </div>

  <div class="card">
    <h3 style="margin-top:0">BTC Price vs BTC Held</h3>
    <canvas id="btcChart"></canvas>
  </div>

  <div class="footer">crypto-dca-monitor &middot; static dashboard rebuilt on each weekly snapshot</div>

<script>
const labels = {json.dumps(chart_labels)};
const assets = {json.dumps(chart_assets)};
const btcPx = {json.dumps(chart_btc_px)};
const btcHeld = {json.dumps(chart_btc_held)};

const baseOpts = {{
  responsive: true,
  plugins: {{ legend: {{ labels: {{ color: '#cbd5e1' }} }} }},
  scales: {{
    x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
    y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }},
  }},
}};

new Chart(document.getElementById('assetsChart'), {{
  type: 'line', data: {{ labels, datasets: [{{
    label: 'Total Assets ($)', data: assets,
    borderColor: '#22d3ee', backgroundColor: 'rgba(34,211,238,.15)', tension: 0.3, fill: true,
  }}]}},
  options: baseOpts,
}});

new Chart(document.getElementById('btcChart'), {{
  type: 'line', data: {{ labels, datasets: [
    {{ label: 'BTC Price ($)', data: btcPx, borderColor: '#fbbf24', tension: 0.3, yAxisID: 'y' }},
    {{ label: 'BTC Held', data: btcHeld, borderColor: '#a78bfa', tension: 0.3, yAxisID: 'y1' }},
  ]}},
  options: {{
    ...baseOpts,
    scales: {{
      x: baseOpts.scales.x,
      y: {{ position: 'left', ticks: {{ color: '#fbbf24' }}, grid: {{ color: '#334155' }} }},
      y1: {{ position: 'right', ticks: {{ color: '#a78bfa' }}, grid: {{ display: false }} }},
    }},
  }},
}});
</script>
</body>
</html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html)
    print(f"Wrote {OUT_PATH} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
