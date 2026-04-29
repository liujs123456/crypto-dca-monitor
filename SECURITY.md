# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability — **especially anything that could expose secrets, leak account data, or trigger unauthorized actions on a fork** — please report it privately rather than opening a public issue.

**How to report:**

1. Open a [private security advisory](https://github.com/liujs123456/crypto-dca-monitor/security/advisories/new) on this repository.
2. Or send a direct message via GitHub to `@liujs123456`.

I'll acknowledge within 7 days and aim to ship a fix within 30 days for high-severity issues.

## Scope

This project is **read-only by design**. There is no trade-execution code path in this repo. If you find any code that reaches a write/trade endpoint on OKX (or any other exchange) without explicit human-in-the-loop approval, please treat that as a critical issue and report it immediately.

In-scope:
- Secret leakage (API keys, tokens, ntfy topics) via logs, error messages, or commit history
- Authentication bypass in the GitHub Actions workflows
- Code injection via RSS feed content, LLM responses, or environment variables
- Anything that could cause a fork's secrets to be exposed in workflow logs

Out of scope:
- Vulnerabilities in upstream dependencies (Groq, OKX, ntfy.sh, GitHub Actions runners) — please report those upstream
- Attacks requiring physical or network access to the user's own machine
- ntfy topic guessing (topics are inherently public — users are advised in the README to use random unguessable topics)

## Disclosure

Once a fix is available, I'll publish a security advisory crediting the reporter (unless they prefer to remain anonymous).
