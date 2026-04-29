# Crypto DCA Monitor

[![tests](https://github.com/liujs123456/crypto-dca-monitor/actions/workflows/test.yml/badge.svg)](https://github.com/liujs123456/crypto-dca-monitor/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

A cloud-native, $0/month cryptocurrency portfolio monitor that runs 24/7 on GitHub Actions. Push notifications for dip-buying ladder triggers, LLM-summarized morning news, end-of-day account snapshots, and a weekly recap — all delivered to your phone via [ntfy.sh](https://ntfy.sh), plus a static dashboard rebuilt on every run.

Built for disciplined dollar-cost-averaging investors who want signal, not noise — and who would rather have their phone interrupt them at the right moment than refresh CoinMarketCap fifty times a day.

> Strategy isn't included; you bring your own. This is execution infrastructure.

## Why this exists

Every retail crypto investor eventually faces the same problem: *checking too often is bad for your strategy and your sleep, but never checking means missing the moments that matter*. Existing solutions are either:
- Mobile exchange apps that incentivize frequent checking and cross-selling
- Paid signal services with opaque algorithms and recurring fees
- Self-hosted scripts that require always-on hardware

This is the third path: a stateless-by-default, idempotent, cron-driven monitor that **only interrupts you when something matters**, runs entirely on free-tier GitHub Actions, and costs nothing beyond the API keys you already have.

## Features

| Workflow | Frequency | What it does |
|----------|-----------|--------------|
| `btc-monitor` | Every 2h on `:07` | Multi-tier dip-buying ladder. Silent unless price crosses a threshold; persists tier state in `state/btc_state.json` (committed back to repo) so the *re-arm-after-rebound* rule actually works. |
| `morning-briefing` | Daily 7:17 AM PT | Aggregates 30+ headlines from CNBC, CoinDesk, Yahoo Finance, Cointelegraph; **deduplicates near-identical stories** across sources; LLM-summarizes the top 4-5 most market-impactful items. |
| `evening-summary` | Daily 8:17 PM PT | Total assets, holdings, today's DCA fills, unrealized P&L, Earn interest, plus a **ladder status block** (which tier is closest, distance to each trigger, armed/fired state). |
| `weekly-summary` | Sundays 9:30 PM PT | Week-over-week delta of assets / BTC held / price; appends a snapshot to `state/weekly_snapshots.json`; rebuilds the dashboard. |
| `update-ref-price` | Daily 1:05 AM PT | Auto-refreshes `BTC_REF_PRICE` GH variable to the rolling 30-day high (rounded up to nearest $500). No more manual recalibration. |

All push to a single ntfy topic — your phone hears one channel, you set DND rules per priority level. **Every workflow has an `if: failure()` step** that pushes a max-priority alert with a clickable link to the failed run, so you find out within seconds when a monitor breaks instead of weeks later.

## Why not other tools?

| Tool | Limitation | This project's answer |
|------|-----------|----------------------|
| **3Commas / Cryptohopper** | Locked into proprietary platform; subscription fees ($30+/mo); your strategy lives on their servers | Self-hosted code, free tier only, your strategy stays in your repo |
| **SymBot / freqtrade** | Requires Docker + always-on VPS / Raspberry Pi; ops burden; restart loops | Stateless workflow runs in CI; nothing to maintain; no server to forget about |
| **binance-dca-bot** (and forks) | Single exchange; basic DCA only; no monitoring or news layer | OKX (extensible to others); dip-ladder + DCA + news + weekly recap + dashboard in one repo |
| **Exchange mobile apps** | Designed to maximize engagement; cross-sell leveraged products; tempt you to check every hour | Push-only UX; silent unless something matters; you check exactly when alerted |
| **Telegram price-alert bots** | Telegram itself is noisy; alerts mix with chat; no priority levels; account binding | ntfy supports per-priority DND; runs alongside iOS Focus; no extra account |
| **Custom Python script + cron on laptop** | Stops when laptop sleeps or travels; you forget to start it back up | GitHub Actions runs in their datacenter 24/7 regardless of your hardware |
| **OKX official tools** (e.g. okx/agent-skills) | Trade execution focused; assumes you want an agent making moves | Read-only by design; observation layer for humans-in-the-loop |

## Architecture

```
                          ┌──────────────────────┐
                          │  GitHub Actions Cron │
                          └──────────┬───────────┘
                                     │
   ┌──────────────┬──────────────────┼──────────────────┬──────────────┐
   │              │                  │                  │              │
   ▼              ▼                  ▼                  ▼              ▼
┌───────┐   ┌───────────┐    ┌──────────────┐   ┌─────────────┐  ┌─────────────┐
│ btc-  │   │ morning-  │    │  evening-    │   │  weekly-    │  │  update-    │
│monitor│   │ briefing  │    │  summary     │   │  summary    │  │  ref-price  │
└───┬───┘   └─────┬─────┘    └──────┬───────┘   └──────┬──────┘  └──────┬──────┘
    │             │                 │                  │                │
    ▼             ▼                 ▼                  ▼                ▼
┌────────┐  ┌──────────┐     ┌──────────────┐    ┌──────────┐   ┌────────────┐
│Coinbase│  │ RSS +    │     │  OKX API     │    │ OKX API  │   │ CoinGecko  │
│CoinGeck│  │ Groq LLM │     │  (HMAC v5)   │    │ + state/ │   │ market_chrt│
└───┬────┘  └────┬─────┘     └──────┬───────┘    └────┬─────┘   └─────┬──────┘
    │            │                  │                 │               │
    └────────────┴──────┬───────────┴─────────────────┴───────────────┘
                        ▼                                ▼
                   ┌─────────┐                    ┌──────────────┐
                   │ ntfy.sh │                    │ docs/        │
                   └────┬────┘                    │ index.html   │
                        ▼                         │ (dashboard)  │
                     📱 Phone                     └──────────────┘
```

State (current tier, armed flags, weekly snapshots) lives in `state/*.json`, committed back to `main` by a bot identity (`monitor-bot`) using `[skip ci]` to avoid recursion. The static dashboard at `docs/index.html` is rebuilt on every BTC monitor + weekly run; serve it via GitHub Pages or just open it locally.

## State persistence

Earlier versions stored tier state by polling past ntfy notifications — clever, but fragile (ntfy's 12h history isn't a contract, and it broke when a notification title was changed). State now lives at `state/btc_state.json`:

```json
{
  "tier": "WATCH",
  "armed": {"T1": true, "T2": false, "T3": true, "T4": true},
  "last_price": 72500.0,
  "last_ref": 79500.0,
  "last_check_utc": "2026-04-28T10:07:11+00:00"
}
```

This makes the **rebound-to-rearm rule** real: if T2 fires at $67,575, it stays disarmed until BTC rebounds above $67,575 × 1.05 = $70,953, even across multiple monitor runs. No double-firing on noisy candles, no false re-fires.

## DST handling — automatic

GitHub Actions cron only supports UTC, which means a cron set for "7:17 AM PT" runs an hour off twice a year. Instead of asking you to edit the YAMLs every March and November, this repo schedules each daily/weekly workflow at **both** PDT and PST UTC times, then a tiny `lib/dst_gate.py` step at the start of each run checks the current PT clock and `exit 0`s if it's the wrong window. The right one fires; the other returns immediately. **You never have to touch cron again.**

## Failure alerts

Silent failures are the worst kind. Every workflow has:

```yaml
- name: Notify on failure
  if: failure()
  run: |
    curl -X POST \
      -H "Title: 🚨 monitor failed" \
      -H "Priority: high" \
      -H "Click: ${RUN_URL}" \
      -d "..." "https://ntfy.sh/${NTFY_TOPIC}"
```

So if Groq rate-limits, OKX rotates an API, GitHub has an outage, or a new dependency breaks something — you get a phone notification within seconds, with a tap-to-open link straight to the failed run's logs.

## AI Co-pilot Layer (optional)

The cron jobs interrupt you when something matters. Once they do, you often want to **ask back** — *why did T1 fire? what's my actual cost basis? how far to T2?* — and a fixed-format push notification can't answer that.

The [`claude/`](./claude) directory ships an optional conversational layer built on [Claude Code](https://claude.com/claude-code) Skills + MCP:

| Layer | Frequency | Interface |
|-------|-----------|-----------|
| Cron workflows (`scripts/`) | Every 2h / daily / weekly | Push notification |
| Static dashboard (`docs/`) | Rebuilt on each run | Web page |
| Claude skills (`claude/`) | On-demand | Natural language |

First skill shipped: [`analyze-position`](./claude/skills/analyze-position/SKILL.md) — ask *"how am I doing?"* / *"看下仓位"* and Claude pulls live OKX state + current ladder tier and gives you a one-screen analysis.

The layer is **independent** of the cron jobs. You can run the monitor without it; the GitHub Actions don't depend on the skills directory. Everything stays read-only — no skill calls a trade endpoint, ever.

## Quick start

```bash
# 1) Fork this repo, then clone your fork
git clone git@github.com:<your-username>/crypto-dca-monitor.git
cd crypto-dca-monitor

# 2) Pick an ntfy topic name (anything URL-safe — pick something hard to guess)
TOPIC="my-dca-$(openssl rand -hex 6)"

# 3) Subscribe your phone: install ntfy iOS/Android app → add subscription "$TOPIC"

# 4) Set GitHub Secrets (see .env.example for all required keys)
gh secret set NTFY_TOPIC --body "$TOPIC"
gh secret set GROQ_API_KEY --body "gsk_xxxxx"        # https://console.groq.com (free tier)
gh secret set OKX_API_KEY --body "..."               # OKX → API → create READ-ONLY key
gh secret set OKX_SECRET --body "..."
gh secret set OKX_PASSPHRASE --body "..."

# 5) (Optional but recommended) Set the dip-ladder reference price
gh variable set BTC_REF_PRICE --body "80000"        # rolling 30-day high

# 6) (Optional) For auto-updating BTC_REF_PRICE: set a fine-grained PAT with `variables: write` scope
gh secret set GH_PAT_VARS --body "ghp_xxxxx"

# 7) Trigger workflows manually to verify
gh workflow run btc-monitor.yml
gh workflow run morning-briefing.yml
gh workflow run evening-summary.yml
```

## Strategy: how the dip-ladder works

Inspired by classic value-averaging plus capitulation-buying:

```
Reference price (rolling 30-day high — auto-maintained by update-ref-price.yml)
    ↓
WATCH: -8% from ref  →  advance warning, no buy signal
T1:    -10% from ref →  first dip
T2:    -15% from ref →  noticeable correction
T3:    -22% from ref →  deep correction
T4:    -32% from ref →  capitulation
```

Each tier publishes a notification with escalating priority. Once a tier fires it's **disarmed** and won't fire again until BTC rebounds above the trigger price by 5%. State lives in `state/btc_state.json`, committed back by the workflow itself.

You decide tier sizes off-platform. This system tells you *when*, never *how much*.

## Dashboard

`docs/index.html` is a single-page static dashboard: current price, ladder state with armed/fired flags, distance to each trigger, and 26-week rolling charts (total assets, BTC price vs holdings). Rebuilt automatically on every BTC monitor run and on every weekly summary.

**Three ways to view it:**
- **GitHub Pages**: Settings → Pages → Source = `main` branch, `/docs` folder. Public repos get this for free.
- **Local**: `open docs/index.html`
- **Anywhere static**: serve the `docs/` directory from Netlify, Cloudflare Pages, etc.

## Why these specific choices

| Decision | Why |
|----------|-----|
| **GitHub Actions cron** | Free; 2,000 min/mo for free accounts; no server to maintain |
| **ntfy.sh (vs SMS/Discord/Slack)** | Free, self-hostable, no account needed, native iOS/Android apps with priority-based DND |
| **Groq llama-3.1-8b-instant** | Free tier, sub-second inference, plenty fast for daily news distillation |
| **State in `state/*.json`, committed back** | No external DB, no Gist token rotation; survives ntfy outages; recovers across long downtime windows |
| **Python stdlib only** | Zero external deps, runs on any Linux runner, easy to audit (no `pip install`) |
| **Coinbase + CoinGecko fallback** | Both have generous public APIs; redundancy avoids missed alerts |

## Costs

Truly $0/month if you stay within free tiers:
- GitHub Actions: 2,000 min/mo for free accounts (this uses ~45 min/mo with all 5 workflows)
- Groq: 30 req/min, 14,400 req/day on free tier (this uses 1 req/day)
- ntfy.sh: free (publish + subscribe to public topics)
- OKX API: free for read-only queries
- Coinbase / CoinGecko: free for unauthenticated quotes

## Schedule reference

All workflows use cron minutes that **avoid** the `:00`/`:03`/`:05` marks where GitHub Actions silently skips runs during global load spikes — see [actions/runner#1306](https://github.com/actions/runner/issues/1306). Instead they use `:07`/`:17`/`:30`.

| Workflow | UTC cron(s) | Resolves to PT |
|----------|-------------|----------------|
| `btc-monitor` | `7 */2 * * *` | every 2h `:07` |
| `morning-briefing` | `17 14 * * *` + `17 15 * * *` | 7:17 AM (DST gate filters one) |
| `evening-summary` | `17 3 * * *` + `17 4 * * *` | 8:17 PM (DST gate filters one) |
| `weekly-summary` | `30 4 * * 1` + `30 5 * * 1` | Sun 9:30 PM (DST gate filters one) |
| `update-ref-price` | `5 8 * * *` + `5 9 * * *` | 1:05 AM (DST gate filters one) |

## What's deliberately not included

- **No trade execution.** By design. This system observes; you decide.
- **No leverage / futures / options.** Spot only.
- **No web UI for configuration.** Everything via GitHub Secrets / Variables.
- **No email channel.** Inboxes are graveyards. Phone push is the only output.

## Testing

```bash
# Ladder math + state machine
python3 -c "from lib import ladder; print(ladder.tier_prices(80000))"

# DST gate (returns exit 0 = skip, exit 1 = proceed)
python3 -m lib.dst_gate skip-if-not 7 17

# Dashboard rebuild from current state
python3 scripts/build_dashboard.py && open docs/index.html

# Claude skill tests (CI-enforced)
python3 -m unittest discover -s claude/skills/analyze-position -p "test_*.py" -v
```

CI runs the skill tests on every push to `claude/**` — see [`.github/workflows/test.yml`](.github/workflows/test.yml) and the badge at the top of this README.

## License

MIT — see [LICENSE](LICENSE).

## Contributions welcome

Issues and PRs welcome. Particularly interested in:
- Additional exchange integrations (Coinbase, Kraken, Binance)
- Configurable tier counts and thresholds via repo variables
- More language support for the morning briefing
- Tests for the cron scripts (`scripts/btc_monitor.py`, `scripts/morning_briefing.py`, `scripts/evening_summary.py`)
- More skills under `claude/skills/` (e.g. `explain-trigger`, `dca-advisor`)
