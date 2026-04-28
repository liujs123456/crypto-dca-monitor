# Crypto DCA Monitor

[![tests](https://github.com/liujs123456/crypto-dca-monitor/actions/workflows/test.yml/badge.svg)](https://github.com/liujs123456/crypto-dca-monitor/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

A cloud-native, $0/month cryptocurrency portfolio monitor that runs 24/7 on GitHub Actions. Push notifications for dip-buying ladder triggers, LLM-summarized morning news, and end-of-day account snapshots — all delivered to your phone via [ntfy.sh](https://ntfy.sh).

Built for disciplined dollar-cost-averaging investors who want signal, not noise — and who would rather have their phone interrupt them at the right moment than refresh CoinMarketCap fifty times a day.

> Strategy isn't included; you bring your own. This is execution infrastructure.

## Why this exists

Every retail crypto investor eventually faces the same problem: *checking too often is bad for your strategy and your sleep, but never checking means missing the moments that matter*. Existing solutions are either:
- Mobile exchange apps that incentivize frequent checking and cross-selling
- Paid signal services with opaque algorithms and recurring fees
- Self-hosted scripts that require always-on hardware

This is the third path: a stateless, idempotent, cron-driven monitor that **only interrupts you when something matters**, runs entirely on free-tier GitHub Actions, and costs nothing beyond the API keys you already have.

## Features

| Workflow | Frequency | What it does |
|----------|-----------|--------------|
| `btc-monitor` | Every 2h | Multi-tier dip-buying ladder. Silent unless price crosses a threshold; uses past notifications as state (no DB needed). |
| `morning-briefing` | Daily 7:03 AM | Aggregates 30+ headlines from CNBC, CoinDesk, Yahoo Finance, Cointelegraph; LLM-summarizes top 4-5 most market-impactful items in your preferred language. |
| `evening-summary` | Daily 8:03 PM | HMAC-SHA256 signed OKX API call: total assets, holdings, today's DCA fills, unrealized P&L, Earn interest. |

All push to a single ntfy topic — your phone hears one channel, you set DND rules per priority level.

## Why not other tools?

| Tool | Limitation | This project's answer |
|------|-----------|----------------------|
| **3Commas / Cryptohopper** | Locked into proprietary platform; subscription fees ($30+/mo); your strategy lives on their servers | Self-hosted code, free tier only, your strategy stays in your repo |
| **SymBot / freqtrade** | Requires Docker + always-on VPS / Raspberry Pi; ops burden; restart loops | Stateless workflow runs in CI; nothing to maintain; no server to forget about |
| **binance-dca-bot** (and forks) | Single exchange; basic DCA only; no monitoring or news layer | OKX (extensible to others); dip-ladder + DCA + news + reports in one repo |
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
       ┌─────────────────────┼─────────────────────┐
       │                     │                     │
       ▼                     ▼                     ▼
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│ btc-monitor │      │  morning-    │      │  evening-    │
│             │      │  briefing    │      │  summary     │
└──────┬──────┘      └──────┬───────┘      └──────┬───────┘
       │                    │                     │
       ▼                    ▼                     ▼
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│  Coinbase   │      │ RSS feeds +  │      │  OKX API     │
│  /CoinGecko │      │ Groq LLM     │      │  (HMAC v5)   │
└──────┬──────┘      └──────┬───────┘      └──────┬───────┘
       │                    │                     │
       └─────────────┬──────┴─────────────────────┘
                     ▼
              ┌─────────────┐
              │   ntfy.sh   │
              └──────┬──────┘
                     ▼
                  📱 Phone
```

Three workflows are completely independent — they don't share state in code. The dip-ladder monitor reads its previous state from past ntfy notifications it published (idempotent, no database). New environments work out of the box without seeding.

## AI Co-pilot Layer (optional)

The cron jobs interrupt you when something matters. Once they do, you often want to **ask back** — *why did T1 fire? what's my actual cost basis? how far to T2?* — and a fixed-format push notification can't answer that.

The [`claude/`](./claude) directory ships an optional conversational layer built on [Claude Code](https://claude.com/claude-code) Skills + MCP:

| Layer | Frequency | Interface |
|-------|-----------|-----------|
| Cron workflows (`scripts/`) | Every 2h / daily | Push notification |
| Claude skills (`claude/`) | On-demand | Natural language |

First skill shipped: [`analyze-position`](./claude/skills/analyze-position/SKILL.md) — ask *"how am I doing?"* / *"看下仓位"* and Claude pulls live OKX state + current ladder tier and gives you a one-screen analysis.

The layer is **independent** of the cron jobs. You can run DCA Sentinel without it; the GitHub Actions don't depend on the skills directory. Everything stays read-only — no skill calls a trade endpoint, ever.

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

# 5) (Optional) Set the dip-ladder reference price
gh variable set BTC_REF_PRICE --body "80000"        # rolling 30-day high

# 6) Trigger workflows manually to verify
gh workflow run btc-monitor.yml
gh workflow run morning-briefing.yml
gh workflow run evening-summary.yml
```

## Strategy: how the dip-ladder works

Inspired by classic value-averaging plus capitulation-buying:

```
Reference price (e.g. 30-day rolling high)
    ↓
T1: -10% from ref  →  watch / first dip
T2: -15% from ref  →  noticeable correction
T3: -22% from ref  →  deep correction
T4: -32% from ref  →  capitulation
```

Each tier publishes a notification with escalating priority. The monitor uses past notifications as state — if T1 just fired, T2 won't fire again until BTC recovers above ref × 0.95, then drops again. No double-firing on noisy candles.

You decide tier sizes off-platform. This system only tells you *when*, never *how much*.

## Why these specific choices

| Decision | Why |
|----------|-----|
| **GitHub Actions cron** | Free; 2,000 min/mo more than enough; no server to maintain |
| **ntfy.sh (vs SMS/Discord/Slack)** | Free, self-hostable, no account needed, native iOS/Android apps with priority-based DND |
| **Groq llama-3.1-8b-instant** | Free tier, sub-second inference, plenty fast for daily news distillation |
| **State stored in ntfy itself** | No external DB, no Gist token rotation, no leakage if repo goes public |
| **Bash + Python stdlib only** | Zero external deps, runs on any Linux runner, easy to audit |
| **Coinbase + CoinGecko fallback** | Both have generous public APIs; redundancy avoids missed alerts |

## Costs

Truly $0/month if you stay within free tiers:
- GitHub Actions: 2,000 min/mo for free accounts (this uses ~30 min/mo)
- Groq: 30 req/min, 14,400 req/day on free tier (this uses 1 req/day)
- ntfy.sh: free (publish + subscribe to public topics)
- OKX API: free for read-only queries
- Coinbase price API: free for unauthenticated quotes

## Daylight Saving Time

GitHub Actions cron uses UTC. Adjust on DST transitions:
- **PDT (March – November)**: morning `3 14 * * *`, evening `3 3 * * *`
- **PST (November – March)**: morning `3 15 * * *`, evening `3 4 * * *`

## What's deliberately not included

- No trade execution. By design. This system observes; you decide.
- No leverage / futures / options. Spot only.
- No web UI. Notifications are the UI.
- No email channel. Inboxes are graveyards. Phone push is the only output.

## Testing

The Claude co-pilot layer ships with stdlib-only unit tests (no `pytest` / no third-party deps — matches the project's "Bash + Python stdlib" philosophy):

```bash
python3 -m unittest discover -s claude/skills/analyze-position -p "test_*.py" -v
```

CI runs the same command on every push to `claude/**` — see [`.github/workflows/test.yml`](.github/workflows/test.yml) and the badge at the top of this README.

The cron workflows (`scripts/`) don't yet have tests — PRs welcome.

## License

MIT — see [LICENSE](LICENSE).

## Contributions welcome

Issues and PRs welcome. Particularly interested in:
- Additional exchange integrations (Coinbase, Kraken, Binance)
- Configurable tier counts and thresholds via repo variables
- More language support for the morning briefing
- Tests for the cron scripts (`scripts/btc_monitor.sh`, `scripts/morning_briefing.py`, `scripts/evening_summary.sh`)
- More skills under `claude/skills/` (e.g. `explain-trigger`, `dca-advisor`)
