# Virtual Market — Agent Operations Guide

This file is the primary reference for any AI agent operating this project.
Read it before taking any action. It contains the complete command reference,
symbol conventions, and step-by-step patterns for every common task.

---

## What this project is

A fake-money investing simulator. Real daily market prices are fetched and stored
locally in a SQLite database. You can deposit cash, buy and sell instruments,
manage a watchlist with price targets, and generate portfolio reports and charts.
No real money is ever involved — this is a sandbox for practising investment decisions.

---

## Running commands

All commands run from the project root.

Use the venv-local binary — no shell activation required:

```bash
.venv/bin/vmarket <command>
```

## Private user data

Default portfolio state now lives under the gitignored `user_data/` workspace:

```text
user_data/vmarket.sqlite
user_data/imports/
user_data/screenshots/
user_data/exports/
user_data/notes/
```

Do not commit files from `user_data/`. Existing databases under `data/` can still
be used explicitly with `VMARKET_DB_PATH` or `--db-path`; do not migrate or delete
them unless the user asks.

---

## Symbol format

Getting the symbol format right is critical. Wrong format = no price data.

| Market | Format | Examples |
|--------|--------|---------|
| NASDAQ / NYSE (US stocks) | `TICKER.US` | `GOOG.US`, `PANW.US`, `NBIS.US`, `NET.US` |
| London Stock Exchange | `TICKER.L` | `CIBR.L`, `BUG.L`, `LOCK.L`, `GOO3.L` |
| UK unit trusts (OEICs) | 7-char SEDOL | `BD6PG78`, `BMN91T3`, `BR2Q8G6` |

UK unit trusts (SEDOLs) have no automatic price source and must be priced manually
using the `--price` flag when recording a trade.

---

## Complete command reference

### Cash

```bash
.venv/bin/vmarket onboard                               # first-run private workspace setup
.venv/bin/vmarket cash balance                          # show all cash balances
.venv/bin/vmarket cash deposit 500                      # deposit £500 (GBP default)
.venv/bin/vmarket cash deposit 500 --currency GBP       # deposit £500 explicitly
.venv/bin/vmarket cash withdraw 200 --currency GBP      # withdraw £200
```

### Portfolio

```bash
.venv/bin/vmarket portfolio show  # show holdings, latest prices, and unrealised P/L
.venv/bin/vmarket portfolio trades
```

### Prices

```bash
.venv/bin/vmarket portfolio prices GOOG.US              # last 30 days (default)
.venv/bin/vmarket portfolio prices GOOG.US --days 7     # last 7 days
.venv/bin/vmarket portfolio prices CIBR.L --days 5      # LSE ETF
```

### Buy and sell

```bash
.venv/bin/vmarket portfolio buy GOOG.US --quantity 2                      # buy 2 shares at latest synced price
.venv/bin/vmarket portfolio buy NBIS.US --quantity 5.77 --price 147.16   # buy at an explicit price
.venv/bin/vmarket portfolio sell GOOG.US --quantity 1                     # sell 1 share
.venv/bin/vmarket portfolio sell NBIS.US --quantity 5.77 --price 151.00  # sell at explicit price
```

`--price` is optional. If omitted, the latest synced price in the database is used.
`--quantity` accepts decimals (e.g. `5.7758` for fractional shares or fund units).

### Watchlist

```bash
.venv/bin/vmarket watch list                                                  # show watchlist with prices
.venv/bin/vmarket watch add AAPL.US --name "Apple Inc" --currency USD --asset-type stock
.venv/bin/vmarket watch add CIBR.L  --name "First Trust Cybersecurity ETF" --currency GBP --asset-type etf
.venv/bin/vmarket watch remove AAPL.US                                        # remove from watchlist
.venv/bin/vmarket watch target GOOG.US --buy-below 300                        # set a buy-below target
.venv/bin/vmarket watch target GOOG.US --sell-above 450                       # set a sell-above target
.venv/bin/vmarket watch target GOOG.US --buy-below 300 --sell-above 450      # set both targets
```

### Onboarding and imports

```bash
.venv/bin/vmarket onboard
.venv/bin/vmarket import portfolio --csv user_data/imports/portfolio.csv
.venv/bin/vmarket import portfolio --paste user_data/imports/pasted_holdings.txt
.venv/bin/vmarket import watchlist --csv user_data/imports/watchlist.csv
.venv/bin/vmarket import drafts
.venv/bin/vmarket import show DRAFT_ID
.venv/bin/vmarket import confirm DRAFT_ID
.venv/bin/vmarket import discard DRAFT_ID
```

All imports are review-first. Creating a draft must not mutate portfolio or
watchlist state. Only `vmarket import confirm DRAFT_ID` writes simulated cash,
instruments, watchlist rows, or trades. If a screenshot is uploaded through the
cockpit, inspect the image and extract candidate rows into a normal import draft;
do not confirm it until the user approves.

Portfolio units are desirable but not always visible in broker screenshots. If
units are missing, create an approximate value-snapshot draft using `current_value`
plus one of `cost_basis`, `gain_amount`, or `gain_percent`. The importer records
these as one synthetic unit so total value and P/L can be tracked, but you must
describe them as approximate and prefer exact units when the user can provide
them. Watch for LSE prices reported in pence and flag pence-denominated rows in
notes when relevant.

`--asset-type` accepts: `stock`, `etf`, `etp`, `fund`
`--currency` accepts any ISO currency code: `USD`, `GBP`, `EUR`

### Sync market data

```bash
.venv/bin/vmarket sync prices                       # sync all instruments, last 7 days
.venv/bin/vmarket sync prices --days 30             # longer historical backfill
.venv/bin/vmarket sync prices --symbol GOOG.US      # single symbol only
.venv/bin/vmarket sync fx                           # sync GBP/USD and GBP/EUR FX rates
```

### Thematic analysis

```bash
.venv/bin/vmarket theme list
.venv/bin/vmarket theme discuss semiconductors
.venv/bin/vmarket theme compare-etfs CYSE FCBR LOCK
.venv/bin/vmarket theme compare-ideas ai-infrastructure --amount 900 --preferred-company NVIDIA --preferred-company Broadcom
.venv/bin/vmarket theme analyse cybersecurity --amount 1800 --preferred-company CrowdStrike --preferred-company Cloudflare --preferred-company "Palo Alto" --preferred-company Zscaler --preferred-company Okta --implementation-scope both
```

Use these commands when the user wants a portfolio-aware discussion of a theme
or wants to compare curated ETF profiles or direct stock baskets. The analysis is
deterministic and uses starter reference data from `data/reference/themes/`, not
live factsheets.

### Portfolio consultation

```bash
.venv/bin/vmarket consult profile show
.venv/bin/vmarket consult profile set --risk-score 5 --exclude defence --product-preference ETF
.venv/bin/vmarket consult portfolio
.venv/bin/vmarket consult ideas
.venv/bin/vmarket consult area "UK mid caps"
.venv/bin/vmarket consult factsheet VUKE --no-fetch
```

Use these commands when the user wants a broader portfolio review rather than a
single theme. The consultant reads the portfolio, cash, watchlist, and saved
profile first, then suggests research areas before making product-level claims.
Verified factsheet summaries live under `data/reference/consult/` and can be
cached locally in `research/`.

### Local cockpit

```bash
.venv/bin/vmarket cockpit serve
.venv/bin/vmarket cockpit export-context --workflow onboarding-import --format markdown --include-prompt
.venv/bin/vmarket cockpit export-context --workflow morning-brief --format json
.venv/bin/vmarket cockpit export-context --workflow portfolio-consultation --format json
.venv/bin/vmarket cockpit export-context --workflow thematic-analysis --theme semiconductors --amount 1800 --format markdown --include-prompt
.venv/bin/vmarket cockpit workflows
.venv/bin/vmarket cockpit journal
```

Use the local cockpit when the user wants a shared visual workspace with:
- the live portfolio overview report at `/overview`
- portfolio status
- portfolio consultation
- thematic analysis
- research follow-up
- staged actions awaiting confirmation
- saved workflow sessions
- decision journal entries
- agent-ready context or prompt packets

The cockpit is local-only and external-agent-first. It prepares artifacts for
Codex, Claude Code, or OpenClaw, but it does not run the agent model itself.
Use `/overview` for the cockpit-integrated HTML report; keep
`reports/overview.html` for file export and stable snapshots.

### Research workspace

```bash
.venv/bin/vmarket research init
.venv/bin/vmarket research brief META.US
.venv/bin/vmarket research collect-sec META.US --cik 1326801 --company-name "Meta Platforms"
```

Use the research workspace when the user wants symbol-level evidence review.
The evidence model is local and explicit: direct, class A, corroborating
journalism, and social. Use it to support theme and consult workflows, not to
replace portfolio-aware reasoning.

### Charts and memos

```bash
.venv/bin/vmarket report overview                                              # standalone HTML overview export
.venv/bin/vmarket report overview --html reports/overview.html                 # recommended stable path
.venv/bin/vmarket report chart portfolio                                        # ASCII chart in terminal
.venv/bin/vmarket report chart allocation                                       # allocation bar chart
.venv/bin/vmarket report chart pnl                                              # P/L per holding
.venv/bin/vmarket report chart portfolio --html reports/chart_portfolio.html   # export as interactive HTML
.venv/bin/vmarket report chart allocation --html reports/chart_allocation.html
.venv/bin/vmarket report chart pnl --html reports/chart_pnl.html
.venv/bin/vmarket report memo                                                   # print daily memo to stdout
.venv/bin/vmarket report memo --output reports/daily_2026-04-26.md             # save to file
```

---

## Common task patterns

These are the tasks a user is most likely to ask for. Follow these step-by-step.

---

### "Deposit £500 cash"

```bash
.venv/bin/vmarket cash deposit 500 --currency GBP
.venv/bin/vmarket cash balance    # confirm
```

---

### "How much cash do I have?"

```bash
.venv/bin/vmarket cash balance
```

---

### "Show my portfolio"

```bash
.venv/bin/vmarket portfolio show
```

---

### "Buy 3 shares of GOOG" (quantity known)

```bash
.venv/bin/vmarket portfolio prices GOOG.US --days 3   # confirm latest price
.venv/bin/vmarket cash balance                # confirm sufficient cash
.venv/bin/vmarket portfolio buy GOOG.US --quantity 3
.venv/bin/vmarket portfolio show
```

---

### "Invest £850 in NBIS" (budget given, quantity unknown)

1. Get the latest price:
   ```bash
   .venv/bin/vmarket portfolio prices NBIS.US --days 3
   ```
   Note the most recent `Close` value. Example: `147.16`

2. Get available cash:
   ```bash
   .venv/bin/vmarket cash balance
   ```

3. Calculate quantity: `budget / price`, truncated to 4 decimal places.
   Example: `850 / 147.16 = 5.7758`

4. Verify: `5.7758 × 147.16 = 849.97` — fits within budget and available cash.

5. Execute:
   ```bash
   .venv/bin/vmarket portfolio buy NBIS.US --quantity 5.7758
   ```

6. Confirm:
   ```bash
   .venv/bin/vmarket portfolio show
   .venv/bin/vmarket cash balance
   ```

---

### "Sell all my NBIS"

1. Get current holding:
   ```bash
   .venv/bin/vmarket portfolio show
   ```
2. Note the `Qty` shown for `NBIS.US`.
3. Execute:
   ```bash
   .venv/bin/vmarket portfolio sell NBIS.US --quantity <qty>
   ```

---

### "Sell half my NBIS position"

1. Get current holding from `portfolio show`. Note the `Qty` for `NBIS.US`.
2. `half = qty / 2`, truncated to 4 decimal places.
3. Execute:
   ```bash
   .venv/bin/vmarket portfolio sell NBIS.US --quantity <half>
   ```

---

### "Add Apple to my watchlist"

```bash
.venv/bin/vmarket watch add AAPL.US --name "Apple Inc" --currency USD --asset-type stock
.venv/bin/vmarket sync prices --symbol AAPL.US --days 7   # fetch its price history
.venv/bin/vmarket watch list                             # verify it appears
```

---

### "Set a buy alert on GOOG at £300"

```bash
.venv/bin/vmarket watch target GOOG.US --buy-below 300
.venv/bin/vmarket watch list    # confirm target is set
```

---

### "What's the current price of Cloudflare?"

Cloudflare's symbol is `NET.US`.

```bash
.venv/bin/vmarket portfolio prices NET.US --days 5
```

---

### "Discuss a theme in the context of my current portfolio"

1. Inspect the current portfolio and cash:
   ```bash
   .venv/bin/vmarket portfolio show
   .venv/bin/vmarket cash balance
   ```
2. Discover the supported starter themes if needed:
   ```bash
   .venv/bin/vmarket theme list
   ```
3. If the user gave an amount or preferred companies, run:
   ```bash
   .venv/bin/vmarket theme analyse <theme> --amount <amount> --implementation-scope both
   ```
4. If the user wants a broader conversation without a fixed amount, run:
   ```bash
   .venv/bin/vmarket theme discuss <theme>
   ```
5. If the user wants a direct ETF comparison, run:
   ```bash
   .venv/bin/vmarket theme compare-etfs <etf ids...>
   ```
6. If the user wants ETF versus direct-basket comparison, run:
   ```bash
   .venv/bin/vmarket theme compare-ideas <theme> --implementation-scope both
   ```

In your response, distinguish:
- best thematic fit
- best risk-adjusted implementation
- why ETF versus basket trade-offs differ
- why the answer changes when allocation size or overlap changes

---

### "Review my portfolio and suggest what I should research next"

1. Inspect the current portfolio, cash, and watchlist:
   ```bash
   .venv/bin/vmarket portfolio show
   .venv/bin/vmarket cash balance
   .venv/bin/vmarket watch list
   ```
2. Load the saved consultant profile:
   ```bash
   .venv/bin/vmarket consult profile show
   ```
3. Run the consultant diagnosis:
   ```bash
   .venv/bin/vmarket consult portfolio
   ```
4. If the user has already supplied constraints, pass them directly:
   ```bash
   .venv/bin/vmarket consult portfolio --risk-score <1-7> --exclude <term>
   ```
5. If the user wants one idea expanded, run:
   ```bash
   .venv/bin/vmarket consult area "<research area>"
   ```
6. Only make product-level claims after a verified factsheet lookup:
   ```bash
   .venv/bin/vmarket consult factsheet <identifier> --no-fetch
   ```

In your response:
- suggest research areas first, not immediate buys
- use the watchlist as intent evidence
- explain concentration and diversification trade-offs
- respect exclusions
- stay on the decision-support side of the line rather than giving regulated advice

---

### "Open the cockpit" or "prepare something for the agent"

1. If the user wants the visual workspace, run:
   ```bash
   .venv/bin/vmarket cockpit serve
   ```
2. If the user wants an agent-ready bundle without opening the UI, export:
   ```bash
   .venv/bin/vmarket cockpit export-context --workflow <workflow> --format json
   ```
3. For thematic work, include the same theme inputs you would use at the CLI:
   ```bash
   .venv/bin/vmarket cockpit export-context --workflow thematic-analysis --theme <theme> --amount <amount> --format markdown --include-prompt
   ```
4. For consultant work, export the consultation workflow:
   ```bash
   .venv/bin/vmarket cockpit export-context --workflow portfolio-consultation --format json
   ```
5. For saved workflow sessions or historical rationale, inspect:
   ```bash
   .venv/bin/vmarket cockpit workflows
   .venv/bin/vmarket cockpit journal
   ```
6. Treat cockpit exports as another source of truth alongside direct CLI commands.

---

### "Follow up the research on a symbol"

1. Make sure the local research workspace exists:
   ```bash
   .venv/bin/vmarket research init
   ```
2. If the user wants direct-source validation, collect recent SEC evidence when applicable:
   ```bash
   .venv/bin/vmarket research collect-sec <symbol> --cik <cik>
   ```
3. Review the local evidence brief:
   ```bash
   .venv/bin/vmarket research brief <symbol>
   ```
4. If the user wants the visual workspace, open:
   ```bash
   .venv/bin/vmarket cockpit serve
   ```
5. Use research findings to support, not replace, the portfolio context from theme
   and consult workflows.

---

### "Run the daily sync"

```bash
.venv/bin/vmarket sync prices --days 7
.venv/bin/vmarket sync fx --days 7
.venv/bin/vmarket report overview --html reports/overview.html
.venv/bin/vmarket report memo --output reports/daily_$(date +%F).md
.venv/bin/vmarket report chart portfolio --html reports/chart_portfolio.html
.venv/bin/vmarket report chart allocation --html reports/chart_allocation.html
.venv/bin/vmarket report chart pnl --html reports/chart_pnl.html
```

---

## What will fail (expected, not errors)

- **UK OEICs (SEDOLs)**: `BD6PG78`, `BMN91T3`, `BR2Q8G6` — no automatic price source.
  These are unlisted unit trusts. Price sync will always report them as failed. This is expected.
  Record trades for them using an explicit `--price` flag.

- **Stooq failures**: Stooq occasionally returns no data for a symbol. The system
  automatically falls back to Yahoo Finance, then Alpha Vantage. Failure messages
  for individual symbols during a full sync are normal as long as some instruments succeed.

---

## Price provider chain

Providers are tried in this order for each symbol:

1. **Stooq** — primary, free, no key required
2. **Yahoo Finance** — automatic fallback for all symbols (including `.L`), free, no key required
3. **Alpha Vantage** — final fallback for non-LSE symbols only; requires `ALPHA_VANTAGE_API_KEY` in `.env` (25 req/day on free tier)

---

## Skills

Reusable agent skills live under `.agents/skills/`.

Current public skills include:

| Skill | What it does |
|-------|--------------|
| `onboarding-import` | First-run setup and review-first portfolio/watchlist imports |
| `portfolio-consultant` | Portfolio-aware consultation with research-area-first reasoning |
| `thematic-investment-discussion` | Theme analysis using deterministic ETF and stock-basket logic |

Agents that do not support skills can use the CLI commands directly as shown above.

---

## Data files

| Path | Contents |
|------|----------|
| `data/vmarket.sqlite` | Legacy/explicit database location — never edit directly |
| `user_data/` | Private local state, import drafts, screenshots, exports, and notes — never commit |
| `.env` | API keys — `ALPHA_VANTAGE_API_KEY` |
| `reports/` | Generated HTML charts and daily memos |
| `logs/sync.log` | Cron job output |

Use `vmarket init` only to initialise a fresh database.

---

## Package layout (for code-reading agents)

```
vmarket/
  cli/                — Typer CLI entry point and command groups
  config.py           — Env-var config helpers
  db.py               — SQLAlchemy engine, session, Base
  errors.py           — Custom exception hierarchy
  models/             — SQLAlchemy ORM models (Instrument, Trade, WatchlistItem, ...)
  dto/                — Frozen dataclass transfer objects (PriceBarDTO, PositionDTO)
  providers/          — Market data providers (stooq, yahoo_finance, alpha_vantage)
  repositories/       — DB query helpers (no business logic)
  services/           — Business logic layer (market_data_service, trade_service, ...)
  web/                — Local cockpit app, templates, and agent context exports
```
