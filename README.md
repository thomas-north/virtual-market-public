# Virtual Market

A local investment simulator and decision lab for agent-assisted portfolio thinking.

> **Safety:** This app never connects to a real brokerage. All cash and trades are simulated.

---

## What This Repo Is

`virtual-market-public` is the open-source home of Virtual Market.

It is intentionally maintained as a **curated public mirror** of a faster-moving
private working repository. That means:

- the public repo is the place for outside contributors, issues, and PRs
- the private repo is where feature work may be incubated first
- public updates are published in clear, reviewable batches instead of replaying
  every private commit verbatim

The product direction is a **cockpit-first local decision lab** for portfolio
thinking with an external coding agent. The public repo is being brought into
that shape in staged sync PRs.

---

## Current Public Status

Today, this public repo already supports:

- fake-money cash, trades, holdings, and watchlists
- daily market price sync
- FX sync
- portfolio valuation
- memo generation
- research evidence storage and brief rendering

The next public sync waves will add:

- first-run onboarding and import drafts
- the local cockpit web app
- thematic analysis
- portfolio consultation
- staged actions, workspace sessions, and decision journaling

So the long-term product story is already set, even though this public repo is
still catching up to it.

---

## Fastest Path For A New User

```bash
git clone https://github.com/thomas-north/virtual-market-public.git
cd virtual-market-public
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
vmarket init
```

Then try:

```bash
vmarket cash deposit 10000 --currency GBP
vmarket watch add AAPL.US --name "Apple Inc" --currency USD --asset-type stock
vmarket sync prices --days 30
vmarket portfolio
vmarket memo daily
```

---

## Private Data Model

Local state should live in a gitignored `user_data/` workspace:

```text
user_data/vmarket.sqlite
user_data/imports/
user_data/screenshots/
user_data/exports/
user_data/notes/
```

This public repo is for code. Your personal simulated portfolio, notes, and
imports should stay local and untracked.

The current public codebase still supports explicit database overrides through
`VMARKET_DB_PATH`, and the staged sync PRs will finish aligning the runtime
default with the `user_data/` layout.

---

## What You Can Ask Your AI Agent To Do

Virtual Market is designed to work well with external coding agents such as
Codex, Claude Code, or OpenClaw.

Examples:

- "Deposit GBP 1,000 of fake cash"
- "Show me my current portfolio"
- "Add Apple to my watchlist"
- "Sync today's prices"
- "Generate today's memo"
- "Research META.US and summarise the evidence"

The public agent workflow is documented in [AGENT.md](AGENT.md).

---

## Install

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Commands

Current public commands include:

- `vmarket init`
- `vmarket cash ...`
- `vmarket watch ...`
- `vmarket watchlist`
- `vmarket sync prices`
- `vmarket sync fx`
- `vmarket buy`
- `vmarket sell`
- `vmarket trades`
- `vmarket portfolio`
- `vmarket chart ...`
- `vmarket memo daily`
- `vmarket research ...`

Run:

```bash
vmarket --help
```

---

## Symbol Format

| Market | Format | Example |
|--------|--------|---------|
| NASDAQ / NYSE | `TICKER.US` | `AAPL.US`, `GOOG.US` |
| London Stock Exchange | `TICKER.L` | `CIBR.L`, `BUG.L` |
| UK unit trusts (OEICs) | 7-char SEDOL | `BD6PG78` |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VMARKET_DB_PATH` | `./user_data/vmarket.sqlite` | SQLite database path |
| `VMARKET_BASE_CURRENCY` | `GBP` | Portfolio base currency |
| `ALPHA_VANTAGE_API_KEY` | *(empty)* | Optional fallback price provider |
| `VMARKET_SEC_USER_AGENT` | example value in `.env.example` | Identifier for SEC requests |

---

## Market Data

Prices are fetched via a provider chain:

1. **[Stooq](https://stooq.com)**
2. **[Yahoo Finance](https://finance.yahoo.com)**
3. **[Alpha Vantage](https://www.alphavantage.co)** when configured

FX rates use **[Frankfurter](https://www.frankfurter.app)**.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, checks, and the curated
public/private sync workflow.

---

## License

Licensed under [Apache-2.0](LICENSE).
