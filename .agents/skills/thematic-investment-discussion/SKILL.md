---
name: "thematic-investment-discussion"
description: "Portfolio-aware thematic ETF and stock-basket discussion for Virtual Market using deterministic local analysis."
---

# thematic-investment-discussion

Use this skill when the user wants to discuss a theme, compare thematic ETFs, or
stress-test a thematic idea or direct stock basket against the current Virtual Market
portfolio.

This skill is designed for OpenClaw-style local workspace reasoning: inspect the
repo, inspect current reports and memos, inspect portfolio state through the CLI,
and then use the deterministic theme-analysis commands before writing a nuanced
answer.

## Behaviour standard

- Be analytical, conversational, and practical.
- Do not behave like a hype-driven stock picker.
- Do not rank ETFs only by historical performance.
- Distinguish the best thematic fit from the best risk-adjusted implementation.
- Explain why the answer changes when sizing, overlap, or user preferences change.
- Compare ETF implementations against direct equal-weight stock baskets when relevant.
- Treat the output as decision support for a simulated portfolio, not financial advice.

## Workspace crawl sequence

All commands run from the project root.

1. Read `AGENT.md` if you need the current repo command conventions.
2. Inspect the current portfolio:

```bash
.venv/bin/vmarket portfolio show
.venv/bin/vmarket cash balance
```

3. Discover the available starter themes first:

```bash
.venv/bin/vmarket theme list
```

4. Check whether a fresh memo or overview already exists:

```bash
ls reports/
```

If relevant, read the latest memo in `reports/`.

5. Compare or analyse the theme with the deterministic commands:

```bash
.venv/bin/vmarket theme discuss semiconductors
.venv/bin/vmarket theme analyse cybersecurity --amount 1800 --preferred-company CrowdStrike --preferred-company Cloudflare --preferred-company "Palo Alto" --preferred-company Zscaler --preferred-company Okta --implementation-scope both
.venv/bin/vmarket theme compare-etfs CYSE FCBR LOCK
.venv/bin/vmarket theme compare-ideas ai-infrastructure --amount 900 --preferred-company NVIDIA --preferred-company Broadcom
```

## Missing preferences

Only ask for information that the workspace cannot tell you:

- proposed allocation size
- preferred companies
- volatility tolerance
- time horizon
- whether the user wants core or satellite exposure

If one of those is missing, make the gap explicit and explain how it could change
the implementation choice.

## Output pattern

Structure the response around:

1. Current portfolio context
2. Best thematic fit
3. Best risk-adjusted implementation
4. Why direct stock baskets or ETFs are weaker alternatives
5. Main risk and what would change the recommendation
6. Why the answer changes under different sizing or preference assumptions
7. Implementation warnings such as overlap, concentration, currency friction, or rebalancing burden
