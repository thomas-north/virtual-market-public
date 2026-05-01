# Virtual Market

A local fake-money investing simulator using real daily market prices.

> **Safety:** This app never connects to a real brokerage. All cash and trades are simulated.

---

## What you can ask your AI agent to do

Virtual Market is designed to be operated by an AI agent (Claude Code, or any agent
that can run shell commands). Here are examples of natural language instructions
you can give — the agent reads [AGENT.md](AGENT.md) to know exactly how to carry them out.

**Cash**
- "Deposit £1,000 cash"
- "How much cash do I have?"
- "Withdraw £200"

**Portfolio**
- "Show me my portfolio"
- "What are my unrealised gains?"
- "Show my trade history"

**Buying and selling**
- "Invest £850 in NASDAQ:NBIS"
- "Buy 2 shares of Alphabet"
- "Sell half my Palo Alto position"
- "Sell all my Zscaler"

**Watchlist**
- "Add Apple to my watchlist"
- "Remove Intuit from my watchlist"
- "Set a buy alert on Cloudflare at £180"
- "Show my watchlist with current prices"

**Market data and research**
- "Sync today's prices"
- "What's the current price of Palo Alto?"
- "Show me GOOG's price history for the last 30 days"
- "Research Rubrik for me — is it worth buying?"

**Reports and charts**
- "Generate today's portfolio memo"
- "Show me the allocation chart"
- "Export the P/L chart to HTML"

The agent handles the translation from plain English to the correct CLI commands.
For the full agent reference, see [AGENT.md](AGENT.md).

---

## Install

```bash
cd virtual-market
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env      # add ALPHA_VANTAGE_API_KEY if you have one
vmarket init
```

## Quick start

```bash
vmarket cash deposit 10000 --currency GBP
vmarket watch add AAPL.US --name "Apple Inc" --currency USD --asset-type stock
vmarket sync prices --days 30
vmarket watchlist
vmarket buy AAPL.US --quantity 5
vmarket portfolio
vmarket memo daily
```

## Commands

| Command | Description |
|---------|-------------|
| `vmarket init` | Initialise database and default portfolio |
| `vmarket cash deposit <amount>` | Deposit fake cash |
| `vmarket cash withdraw <amount>` | Withdraw fake cash |
| `vmarket cash balance` | Show cash balances |
| `vmarket watch add <symbol>` | Add to watchlist |
| `vmarket watch remove <symbol>` | Remove from watchlist |
| `vmarket watch target <symbol>` | Set buy/sell price targets |
| `vmarket watchlist` | Show watchlist with current prices |
| `vmarket sync prices` | Sync daily prices (Stooq → Yahoo → Alpha Vantage) |
| `vmarket sync fx` | Sync GBP/USD and GBP/EUR FX rates |
| `vmarket prices <symbol>` | Show recent prices for one instrument |
| `vmarket buy <symbol> --quantity N` | Buy using fake cash |
| `vmarket sell <symbol> --quantity N` | Sell holdings |
| `vmarket trades` | Show trade history |
| `vmarket portfolio` | Show holdings and unrealised P/L |
| `vmarket chart portfolio` | Portfolio value chart |
| `vmarket chart allocation` | Allocation breakdown chart |
| `vmarket chart pnl` | P/L per holding chart |
| `vmarket memo daily` | Generate daily Markdown memo |

## Symbol format

| Market | Format | Example |
|--------|--------|---------|
| NASDAQ / NYSE | `TICKER.US` | `AAPL.US`, `GOOG.US` |
| London Stock Exchange | `TICKER.L` | `CIBR.L`, `BUG.L` |
| UK unit trusts (OEICs) | 7-char SEDOL | `BD6PG78` |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VMARKET_DB_PATH` | `./data/vmarket.sqlite` | SQLite database path |
| `VMARKET_BASE_CURRENCY` | `GBP` | Portfolio base currency |
| `ALPHA_VANTAGE_API_KEY` | *(empty)* | Optional third-tier price provider (25 req/day free) |

## Market data

Prices are fetched via a three-provider chain, tried in order:

1. **[Stooq](https://stooq.com)** — free, no key required
2. **[Yahoo Finance](https://finance.yahoo.com)** — free, no key required, handles LSE (`.L`) tickers
3. **[Alpha Vantage](https://www.alphavantage.co)** — free key required, US stocks only, 25 req/day

FX rates use **[Frankfurter](https://www.frankfurter.app)** — free, no key required.

## AI agent skills (Claude Code)

For Claude Code agents, ready-made skills live in `.claude/commands/`:

| Skill | What it does |
|-------|-------------|
| `/vm-sync` | Full daily sync: prices, FX, memo, HTML charts |
| `/vm-brief` | Morning portfolio brief |
| `/vm-research SYMBOL` | Research an instrument |
| `/vm-trade buy SYMBOL QTY` | Guided buy/sell with confirmation |
| `/vm-cash deposit 500` | Cash management |
| `/vm-watch add SYMBOL` | Watchlist management |

## Automated daily sync

A cron job runs `scripts/sync_daily.sh` each weeknight at 22:30 BST:

```
30 21 * * 1-5 /path/to/virtual-market/scripts/sync_daily.sh >> /path/to/virtual-market/logs/sync.log 2>&1
```

## Tests

```bash
pytest
```
