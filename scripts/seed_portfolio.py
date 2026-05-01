#!/usr/bin/env python3
"""One-time seed: loads the PORTFOLIO.md snapshot (2026-04-12) into vmarket."""
from datetime import date
from decimal import Decimal

from vmarket.db import init_db, get_session
from vmarket.config import get_base_currency
from vmarket.repositories import portfolios as port_repo
from vmarket.services.cash_service import deposit as cash_deposit
from vmarket.services.watchlist_service import add_to_watchlist
from vmarket.services.trade_service import buy

SNAPSHOT_DATE = date(2026, 4, 12)

# (symbol, name, currency, asset_type, quantity, gbp_price_per_unit, notes)
# US stocks: recorded at GBP-converted cost basis from portfolio snapshot.
# UK funds: SEDOL used as symbol; won't sync from Stooq — manual price only.
HOLDINGS = [
    (
        "AVGO.US", "Broadcom Inc", "GBP", "stock",
        Decimal("1"), Decimal("276.08"),
        "Broadcom — chip deal with OpenAI thesis",
    ),
    (
        "META.US", "Meta Platforms", "GBP", "stock",
        Decimal("1"), Decimal("468.02"),
        "Meta — undervalued AI product thesis",
    ),
    (
        "NBIS.US", "Nebius Group", "GBP", "stock",
        Decimal("8"), Decimal("107.6975"),  # 861.58 / 8
        "Nebius — Reddit semantic analysis thesis",
    ),
    (
        "BR2Q8G6", "Ranmore Global Equity Institutional GBP", "GBP", "fund",
        Decimal("3.3591"), Decimal("52.9241"),  # 177.78 / 3.3591
        "Ranmore — alternative global equity exposure ETF",
    ),
    (
        "BMN91T3", "UBS S&P 500 Index C Acc", "GBP", "fund",
        Decimal("1005.3016"), Decimal("2.3206"),  # 2332.90 / 1005.3016
        "UBS S&P 500 — USA exposure, long-term",
    ),
    (
        "BD6PG78", "WS Blue Whale Growth R Sterling Acc", "GBP", "fund",
        Decimal("189.365"), Decimal("3.7849"),  # 716.75 / 189.365
        "Blue Whale — growth exposure ETF",
    ),
]

CASH_GBP = Decimal("920.28")


def main() -> None:
    print("Initialising database...")
    init_db()

    total_holdings_cost = sum(q * p for _, _, _, _, q, p, _ in HOLDINGS)
    total_deposit = total_holdings_cost + CASH_GBP

    with get_session() as session:
        port_repo.get_or_create_default(session, base_currency="GBP")

        print(f"Depositing {total_deposit:.2f} GBP (holdings cost + cash buffer)...")
        cash_deposit(session, total_deposit, "GBP", notes="Portfolio seed — April 2026 snapshot", on_date=SNAPSHOT_DATE)
        session.commit()

        for symbol, name, currency, asset_type, qty, price, notes in HOLDINGS:
            print(f"Adding {symbol} to watchlist...")
            add_to_watchlist(session, symbol, name=name, currency=currency, asset_type=asset_type)
            session.commit()

            print(f"Buying {qty} x {symbol} @ {price:.4f} GBP (cost: {qty * price:.2f} GBP)...")
            buy(
                session,
                symbol=symbol,
                quantity=qty,
                price=price,
                currency="GBP",
                on_date=SNAPSHOT_DATE,
                notes=notes,
            )
            session.commit()

    print("\n✓ Portfolio seeded successfully.")
    print(f"  Snapshot date: {SNAPSHOT_DATE}")
    print(f"  Holdings loaded: {len(HOLDINGS)}")
    print(f"  Cash after purchases: {CASH_GBP:.2f} GBP")
    print(f"\nNote: UK fund symbols (BR2Q8G6, BMN91T3, BD6PG78) will not sync from Stooq.")
    print("       US stocks (AVGO.US, META.US, NBIS.US) will sync normally.")
    print("\nRun: vmarket portfolio")


if __name__ == "__main__":
    main()
