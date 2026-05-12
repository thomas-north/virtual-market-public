# Virtual Market

A local investment simulator and decision lab for agent-assisted portfolio thinking.

> **Safety:** This app never connects to a real brokerage. All cash and trades are simulated.

---

## What This Is

Virtual Market is a fake-money portfolio playground that runs on your machine. It
stores your private portfolio/watchlist state locally, fetches real daily market
prices, and gives an external coding agent such as Codex, Claude Code, or
OpenClaw enough structured context to help you discuss simulated trades,
portfolio gaps, thematic ideas, and research follow-ups.

The cockpit is the main human interface. The CLI is the stable automation layer.
The agent reads [AGENT.md](AGENT.md) and `.agents/skills/` to operate the project
safely.

---

## Fastest Path For A New User

```bash
git clone https://github.com/thomas-north/virtual-market-public.git
cd virtual-market-public
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
vmarket onboard
vmarket cockpit serve
```

Then open:

```text
http://127.0.0.1:8765/onboarding
```

The onboarding page guides you through:

- creating a private `user_data/` workspace
- setting base currency, jurisdiction, risk score, and exclusions
- importing a portfolio manually, from CSV, from pasted text, or via screenshot-assisted agent extraction
- reviewing import drafts before anything mutates the simulated portfolio
- exporting a prompt packet for Codex, Claude Code, or OpenClaw

If you do not want to activate the virtual environment each time, run:

```bash
.venv/bin/vmarket --help
```

---

## Private Data Model

Personal state lives in `user_data/`, which is ignored by git:

```text
user_data/vmarket.sqlite
user_data/imports/
user_data/screenshots/
user_data/exports/
user_data/notes/
```

This keeps the public project code separate from your simulated portfolio. You
can override the database location with `VMARKET_DB_PATH` or `--db-path`, so
older databases under `data/` still work explicitly.

Do not commit `user_data/`.

---

## Onboarding With An Agent

After running the cockpit, you can ask your local agent:

```text
Use the Virtual Market onboarding-import skill to help me set up my portfolio.
Inspect the current import drafts, review any screenshot uploads, and do not
confirm any import until I explicitly approve the rows.
```

Useful commands for agents:

```bash
vmarket onboard
vmarket import drafts
vmarket import show <draft-id>
vmarket cockpit export-context --workflow onboarding-import --format markdown --include-prompt
```

Screenshot imports are intentionally agent-assisted in v1. The cockpit stores the
image and generates an agent packet; the agent extracts candidate rows; the user
reviews the draft; only confirmation mutates the simulator.

---

## Import Data Formats

Portfolio CSV columns:

```csv
symbol,name,quantity,average_cost,currency,asset_type,trade_date,notes,current_price
AAPL.US,Apple Inc,5,180,USD,stock,2026-05-09,Opening import,182
```

If your broker/app does not show units, you can import an approximate value
snapshot instead. Provide `current_value` plus one of `cost_basis`, `gain_amount`,
or `gain_percent`:

```csv
symbol,name,current_value,gain_amount,currency,asset_type,notes
META.US,Meta Platforms Inc Class A,448.72,-46.53,GBP,stock,"AJ Bell screenshot; no units visible"
```

Approximate snapshot rows are recorded as one synthetic unit so the simulator can
track total value and P/L. Replace them with unit-based rows later if you obtain
exact units and average cost.

Watchlist CSV columns:

```csv
symbol,name,currency,asset_type,target_buy_price,target_sell_price,notes
VWRP.L,Vanguard FTSE All-World,GBP,etf,,,"Core global equity candidate"
```

Pasted portfolio text can also be simple rows such as:

```text
AAPL.US 5 180 USD Apple Inc
VWRP.L 10 95 GBP Vanguard FTSE All-World
```

All imports create drafts first:

```bash
vmarket import portfolio --csv user_data/imports/portfolio.csv
vmarket import watchlist --csv user_data/imports/watchlist.csv
vmarket import drafts
vmarket import show <draft-id>
vmarket import confirm <draft-id>
```

Some London-listed ETFs/funds report prices in pence from market-data providers.
Check unusually large LSE prices during onboarding and annotate the row if the
provider value is pence-denominated.

---

## What You Can Ask Your AI Agent To Do

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

**Thematic discussion**
- "Show me the supported themes"
- "Discuss semiconductors exposure in the context of my portfolio"
- "Compare CYSE, FCBR, and LOCK"
- "Compare an India ETF versus a direct stock basket"
- "Analyse a £1,800 AI infrastructure idea for me"

**Portfolio consultant**
- "Review my portfolio and suggest research areas"
- "Run a portfolio consultation with risk score 5"
- "Exclude defence and crypto from new ideas"
- "Expand the UK mid caps idea"
- "Summarise the VUKE factsheet"

**Reports and charts**
- "Open my portfolio overview"
- "Open the local agent cockpit"
- "Generate today's portfolio memo"
- "Show me the allocation chart"
- "Export the P/L chart to HTML"

The agent handles the translation from plain English to the correct CLI commands.
For the full agent reference, see [AGENT.md](AGENT.md).

---

## Install

If you have already followed the fast path above, you can skip this section.

```bash
cd virtual-market
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env      # add ALPHA_VANTAGE_API_KEY if you have one
vmarket onboard
```

`vmarket onboard` creates a private, gitignored `user_data/` workspace and points
you at the cockpit onboarding flow.

Database schema upgrades are applied automatically and additively when the CLI
or cockpit opens the SQLite file. Existing local databases are upgraded in
place; no destructive reset is performed.

## Quick start

The cockpit-first path is recommended:

```bash
vmarket cockpit serve
# open http://127.0.0.1:8765/onboarding
# use http://127.0.0.1:8765/overview for the live portfolio report
```

You can also drive the simulator entirely from the CLI:

```bash
vmarket cash deposit 10000 --currency GBP
vmarket watch add AAPL.US --name "Apple Inc" --currency USD --asset-type stock
vmarket sync prices --days 30
vmarket watch list
vmarket portfolio buy AAPL.US --quantity 5
vmarket portfolio show
vmarket doctor
vmarket report overview
```

## Commands

| Command | Description |
|---------|-------------|
| `vmarket onboard` | Create the private local workspace and start first-run setup |
| `vmarket init` | Initialise database and default portfolio |
| `vmarket import portfolio --csv <path>` | Create a reviewable portfolio import draft |
| `vmarket import portfolio --paste <path>` | Create a reviewable portfolio draft from pasted text |
| `vmarket import watchlist --csv <path>` | Create a reviewable watchlist import draft |
| `vmarket import drafts` | List pending and historical import drafts |
| `vmarket import confirm <id>` | Confirm an import draft and mutate simulated state |
| `vmarket import discard <id>` | Discard an import draft without side effects |
| `vmarket cash deposit <amount>` | Deposit fake cash |
| `vmarket cash withdraw <amount>` | Withdraw fake cash |
| `vmarket cash balance` | Show cash balances |
| `vmarket watch add <symbol>` | Add to watchlist |
| `vmarket watch remove <symbol>` | Remove from watchlist |
| `vmarket watch target <symbol>` | Set buy/sell price targets |
| `vmarket watch list` | Show watchlist with current prices |
| `vmarket sync prices` | Sync daily prices (Stooq → Yahoo → Alpha Vantage) |
| `vmarket sync fx` | Sync GBP/USD and GBP/EUR FX rates |
| `vmarket doctor` | Inspect data-quality warnings, sync freshness, and profile gaps |
| `vmarket portfolio prices <symbol>` | Show recent prices for one instrument |
| `vmarket portfolio buy <symbol> --quantity N` | Buy using fake cash |
| `vmarket portfolio sell <symbol> --quantity N` | Sell holdings |
| `vmarket portfolio trades` | Show trade history |
| `vmarket portfolio show` | Show holdings and unrealised P/L |
| `vmarket report overview` | Primary at-a-glance portfolio dashboard |
| `vmarket report chart portfolio` | Portfolio value chart |
| `vmarket report chart allocation` | Allocation breakdown chart |
| `vmarket report chart pnl` | P/L per holding chart |
| `vmarket report memo` | Generate daily Markdown memo |
| `vmarket cockpit serve` | Run the local agent cockpit on localhost |
| `vmarket cockpit export-context` | Export agent-ready JSON or Markdown context |
| `vmarket cockpit workflows` | List saved workflow sessions |
| `vmarket cockpit journal` | List saved decision notes |
| `vmarket consult profile show|set|clear` | Manage the saved consultant profile |
| `vmarket consult portfolio` | Diagnose the portfolio and suggest research areas |
| `vmarket consult ideas` | Show research areas only |
| `vmarket consult area <name>` | Expand one research area with trade-offs |
| `vmarket consult factsheet <id>` | Read a verified factsheet summary |
| `vmarket theme list` | Show supported starter themes |
| `vmarket theme discuss <theme>` | Portfolio-aware thematic discussion |
| `vmarket theme compare-etfs <ids...>` | Compare curated thematic ETF profiles |
| `vmarket theme compare-ideas <theme>` | Compare ETF and stock-basket implementations |
| `vmarket theme analyse <theme> --amount N` | Analyse one thematic allocation |
| `vmarket research init` | Initialize the private local research workspace |
| `vmarket research brief <symbol>` | Render a brief from normalized local evidence |
| `vmarket research collect-sec <symbol> --cik ...` | Collect recent SEC filing evidence |

## Symbol format

| Market | Format | Example |
|--------|--------|---------|
| NASDAQ / NYSE | `TICKER.US` | `AAPL.US`, `GOOG.US` |
| London Stock Exchange | `TICKER.L` | `CIBR.L`, `BUG.L` |
| UK unit trusts (OEICs) | 7-char SEDOL | `BD6PG78` |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VMARKET_DB_PATH` | `./user_data/vmarket.sqlite` | SQLite database path |
| `VMARKET_USER_DATA_DIR` | `./user_data` | Private local workspace for imports, screenshots, exports, and notes |
| `VMARKET_BASE_CURRENCY` | `GBP` | Portfolio base currency |
| `ALPHA_VANTAGE_API_KEY` | *(empty)* | Optional third-tier price provider (25 req/day free) |

## Market data

Prices are fetched via a three-provider chain, tried in order:

1. **[Stooq](https://stooq.com)** — free, no key required
2. **[Yahoo Finance](https://finance.yahoo.com)** — free, no key required, handles LSE (`.L`) tickers
3. **[Alpha Vantage](https://www.alphavantage.co)** — free key required, US stocks only, 25 req/day

FX rates use **[Frankfurter](https://www.frankfurter.app)** — free, no key required.

## AI agent skills

Workspace-native agent skills live under `.agents/skills/`, including:

| Skill | What it does |
|-------|-------------|
| `onboarding-import` | First-run setup and review-first portfolio/watchlist imports, including screenshot-assisted extraction |
| `portfolio-consultant` | Portfolio-aware consultation that suggests research areas before verified product follow-up |
| `thematic-investment-discussion` | Portfolio-aware thematic ETF and stock-basket discussion using deterministic local analysis |

## Local agent cockpit

The main user-facing collaboration surface is now the local cockpit:

```bash
vmarket cockpit serve
```

It runs on `http://127.0.0.1:8765` by default and combines:
- first-run onboarding and reviewable portfolio/watchlist imports
- the live HTML portfolio overview report
- portfolio state
- portfolio consultation
- theme analysis
- research follow-up
- staged actions
- saved workflow sessions
- decision journaling
- agent-ready context and prompt packets

The cockpit does not run a model itself. Instead, it prepares structured context
for an external harness such as Codex, Claude Code, or OpenClaw.

The standalone `reports/overview.html` export is still supported, but day-to-day
visual review can now happen inside the cockpit at `/overview`.

Useful exports:

```bash
vmarket cockpit export-context --workflow onboarding-import --format markdown --include-prompt
vmarket cockpit export-context --workflow morning-brief --format json
vmarket cockpit export-context --workflow portfolio-consultation --format json
vmarket cockpit export-context --workflow thematic-analysis --theme semiconductors --amount 1800 --format markdown --include-prompt
vmarket cockpit workflows
vmarket cockpit journal
```

### Supported workflows

| Workflow | Purpose | Main entry points |
|---------|---------|-------------------|
| `onboarding-import` | Set up private user data and review import drafts | `/onboarding`, `vmarket onboard`, `vmarket import ...`, agent export |
| `morning-brief` | Review daily portfolio state and memo freshness | Cockpit dashboard, `vmarket report memo`, agent export |
| `thematic-analysis` | Compare a theme against current holdings and sizing | `/themes`, `vmarket theme ...`, agent export |
| `portfolio-consultation` | Diagnose concentration/gaps and suggest research areas | `/consult`, `vmarket consult ...`, agent export |
| `research-follow-up` | Review local normalized evidence for a symbol | `/research`, `vmarket research ...`, saved sessions |
| `action-review` | Confirm or discard staged decisions with rationale | `/actions`, staged actions, journal |

## Automated daily sync

You can wire `scripts/sync_daily.sh` into your own cron or launcher setup if you
want a local scheduled refresh. Keep the paths local to your checkout and write
logs into the gitignored `logs/` directory.

## Tests

```bash
pytest
```
