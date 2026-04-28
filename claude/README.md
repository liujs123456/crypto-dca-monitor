# Claude Co-pilot Layer

An optional **conversational layer** for [DCA Sentinel](../README.md). The cron workflows send notifications *to* you; the skills in this directory let you ask questions *back*, in natural language, from inside [Claude Code](https://claude.com/claude-code) or any compatible Skills host.

> **The cron jobs and the co-pilot are independent.** You can run DCA Sentinel without ever installing these skills — the GitHub Actions don't depend on them. This layer exists for moments when a notification fires and you want to dig deeper than "BTC \$71,200, T1 triggered".

## Why a separate layer

The base project's design goal is to **interrupt you only when something matters**. That's the right design for cron — silent unless escalating.

But once you *do* get interrupted, the question becomes *what's actually going on?* — and the cron output is a fixed-format push notification, not a conversation. The Claude layer fills that gap:

| Layer | Frequency | Latency | Interface |
|-------|-----------|---------|-----------|
| Cron workflows (`scripts/`) | Every 2h / daily | None — fire and forget | Push notification |
| Claude skills (this dir) | On-demand | Sub-second | Natural language |

You don't need both. But once you have both, the workflow becomes: **notification fires → open Claude → ask follow-up → decide → close.**

## What's here

| Skill | Purpose | Trigger phrases |
|-------|---------|-----------------|
| [analyze-position](./skills/analyze-position/SKILL.md) | Live account snapshot + ladder context, natural-language analysis | "how am I doing", "看下仓位", "我亏多少", "ladder 在哪一档" |

More planned (PRs welcome):
- `explain-trigger` — when a tier fires, explain why and what changed since the previous tier
- `dca-advisor` — answer "should I manually add now?" given current state + cooldown rules
- `morning-recap` — chat with the morning briefing instead of just reading it

## Installation

The skills here are plain markdown + scripts. You can:

1. **Use them via Claude Code's plugin system** — point Claude at this directory as a local skill source.
2. **Copy them into your existing skills directory** — each skill is self-contained.
3. **Run the scripts directly** — `python3 skills/analyze-position/fetch_position.py` works as a standalone CLI; the SKILL.md is just the trigger contract for the LLM.

All skills require the same env vars as the cron workflows (`OKX_API_KEY`, `OKX_SECRET`, `OKX_PASSPHRASE`). See [.env.example](../.env.example) at the repo root.

## Design rules

These apply to every skill in this directory:

1. **Read-only.** No skill calls a trade, transfer, or withdraw endpoint. Ever.
2. **No leverage anywhere.** Spot-only mirrors the base project.
3. **Stdlib over deps.** Match the cron workflows' "bash + Python stdlib" philosophy. If a skill needs `requests` or `pandas`, push back on whether it actually needs to exist.
4. **Errors surface; no silent fallbacks.** A failed OKX call returns an error to the user, not a stale-cached guess.
5. **Match the user's language.** Chinese in → Chinese out. English in → English out.

## Why "Skills + MCP" instead of a chatbot wrapper

A REST API wrapping `fetch_position.py` would also work. But Skills (and the MCP protocol Claude Code uses) gives you:

- **Trigger discovery for free** — the LLM picks the right skill based on phrasing, no router logic.
- **Schema-typed I/O** — JSON contract between script and LLM, not free-form text.
- **Composability** — future skills can chain (analyze-position → dca-advisor) without you writing glue.
- **Local-first** — no server, no auth layer, runs on your laptop next to the cron workflows.

This makes the co-pilot a **distribution channel** for Sentinel's data, not just a chat bubble around it.
