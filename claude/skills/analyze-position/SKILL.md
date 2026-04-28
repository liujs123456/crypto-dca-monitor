---
name: analyze-position
description: Use this skill when the user asks to analyze their crypto position, check account status, or interpret current dip-ladder state. Triggers include "how am I doing", "what's my P&L", "analyze my position", "看下仓位", "我亏多少", "现在 ladder 在哪一档", "现在该不该加仓". Fetches live OKX account data + current ladder tier and produces a natural-language analysis with clear next-step guidance.
---

# analyze-position

A read-only conversational layer on top of [DCA Sentinel](https://github.com/liujs123456/crypto-dca-monitor). The cron jobs send you push notifications; this skill lets you *ask questions back*.

## When to invoke

The user wants to understand their **current** account state, not historical. Examples:

- "How am I doing on BTC?"
- "我亏多少 / 浮盈多少？"
- "Are we close to T1?"
- "Why hasn't the ladder triggered yet?"
- "What's my average cost basis?"

Skip this skill if the user wants:
- Historical performance over weeks/months → write a separate analytics skill
- News / market sentiment → use a sentiment skill
- To place an order → **never**; this project is observation-only by design

## What the skill does

1. Run `fetch_position.py` (stdlib-only Python, mirrors the OKX HMAC pattern from `scripts/evening_summary.sh`).
2. Receive a structured JSON object containing live price, holdings, P&L, today's DCA fills, and ladder state.
3. Synthesize into a short Chinese-or-English response (match the user's input language).
4. End with one concrete next-step suggestion if relevant — but **never auto-execute trades**.

## Required environment

```bash
OKX_API_KEY=...
OKX_SECRET=...
OKX_PASSPHRASE=...
BTC_REF_PRICE=79500   # optional, defaults to 79500
```

The OKX key MUST be read-only. This skill never calls trade endpoints.

## How to run

```bash
python3 ./fetch_position.py
```

Output is a single JSON object on stdout. Errors go to stderr with a non-zero exit.

Example output:
```json
{
  "price":    { "last": 71200, "open24h": 70100, "change24h_pct": 1.57 },
  "holdings": { "btc": 0.0142, "btc_avg_cost": 68450, "usdt_spot": 312.4, "usdt_earn_amt": 1850.0, "usdt_earn_interest": 12.3 },
  "pnl":      { "btc_value_usd": 1011.04, "total_usd": 3173.44, "unrealized_pl": 39.05, "unrealized_pl_pct": 4.02 },
  "dca_today":{ "count": 1, "total_usd": 20.0, "avg_px": 71150 },
  "ladder":   { "ref": 79500, "watch": 73140, "t1": 71550, "t2": 67575, "t3": 62010, "t4": 54060, "current_state": "T1" }
}
```

## Response style

Keep it scannable on a phone screen. Lead with **the number that matters most** for what the user asked:

- "我亏多少" → lead with `unrealized_pl` and `unrealized_pl_pct`
- "ladder 在哪" → lead with `current_state` and how far to next tier
- "总资产" → lead with `total_usd`

Don't dump the full JSON. Don't editorialize about whether BTC will go up or down — you don't know.

## Hard rules

- **No leverage advice.** This project is spot-only by design.
- **No trade execution.** Even if the user asks "place the order for me", refuse and remind them this is the observation layer.
- **No stale data.** If `fetch_position.py` errors, surface the error — never fall back to a guess.
