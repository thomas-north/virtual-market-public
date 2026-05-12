---
name: "onboarding-import"
description: "First-run Virtual Market onboarding, private user_data setup, and review-first portfolio/watchlist imports including agent-assisted screenshot extraction."
---

# onboarding-import

Use this skill when a user is setting up Virtual Market for the first time,
importing portfolio/watchlist data, or asking an agent to extract holdings from
a broker/app screenshot.

## Behaviour standard

- Treat `user_data/` as private local state. Never commit it.
- Inspect existing portfolio, cash, watchlist, and import drafts before adding new data.
- Imports are draft-first. Creating a draft must not mutate portfolio/watchlist state.
- Only confirm an import after the user explicitly approves the reviewed rows.
- For screenshots, extract candidate rows into the import schema; do not pretend OCR is authoritative.
- Flag ambiguous symbols, currencies, quantities, and cost basis instead of guessing silently.
- If units are unavailable, use an approximate value-snapshot row rather than blocking onboarding.

## Workspace sequence

All commands run from the project root.

1. Read `AGENT.md` if command conventions are unclear.
2. Ensure the private workspace exists:

```bash
.venv/bin/vmarket onboard
```

3. Inspect current state:

```bash
.venv/bin/vmarket cash balance
.venv/bin/vmarket portfolio show
.venv/bin/vmarket watch list
.venv/bin/vmarket import drafts
```

4. For CSV or pasted text imports, create a draft:

```bash
.venv/bin/vmarket import portfolio --csv user_data/imports/portfolio.csv
.venv/bin/vmarket import portfolio --paste user_data/imports/pasted_holdings.txt
.venv/bin/vmarket import watchlist --csv user_data/imports/watchlist.csv
```

5. Review before confirmation:

```bash
.venv/bin/vmarket import show DRAFT_ID
```

6. Confirm only after explicit user approval:

```bash
.venv/bin/vmarket import confirm DRAFT_ID
```

7. Discard bad drafts without side effects:

```bash
.venv/bin/vmarket import discard DRAFT_ID
```

## Screenshot extraction

When the cockpit stores a screenshot draft, inspect the image and extract rows
into these fields where visible:

- Portfolio rows: `symbol`, `name`, `quantity`, `average_cost`, `currency`,
  `asset_type`, `trade_date`, `notes`, `current_price`, `current_value`,
  `cost_basis`, `gain_amount`, `gain_percent`
- Watchlist rows: `symbol`, `name`, `currency`, `asset_type`,
  `target_buy_price`, `target_sell_price`, `notes`

If a value is uncertain, leave it blank or put the uncertainty in `notes`. Ask
the user to resolve missing cost basis, quantity, or currency before confirmation.
When units are not visible, provide `current_value` plus `cost_basis`,
`gain_amount`, or `gain_percent`; the app will record an approximate one-unit
snapshot and mark it as such. Prefer exact units and average cost when available.
For London-listed funds/ETFs, check whether displayed/provider prices are in
pence and note that explicitly.
