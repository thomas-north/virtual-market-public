from __future__ import annotations

import typer

from vmarket.cli.common import console, success, warning
from vmarket.db import get_session

sync_app = typer.Typer(help="Sync market and FX data.")


@sync_app.command("prices")
def sync_prices(
    symbol: str | None = typer.Option(None, "--symbol", help="Sync one instrument only."),
    days: int = typer.Option(7, "--days", help="Calendar-day lookback window."),
) -> None:
    """Sync daily prices from market data providers."""
    from vmarket.services.market_data_service import sync_prices as run_price_sync

    with get_session() as session:
        result = run_price_sync(session, symbol=symbol, days=days)
        session.commit()

    console.print("\n[bold]Price sync complete[/bold]")
    console.print(f"Fetched instruments: {result.fetched}")
    console.print(f"Updated price bars:  {result.updated_bars}")
    console.print(f"Manual-price only:   {len(result.manual_priced)}")
    console.print(f"Failed instruments:  {len(result.failed)}")
    if result.manual_priced:
        console.print(f"Manual-price symbols: {', '.join(result.manual_priced)}")
    if result.failed:
        console.print(f"Failed symbols:       {', '.join(result.failed)}")
    for item in result.warnings:
        warning(item)


@sync_app.command("fx")
def sync_fx(days: int = typer.Option(7, "--days", help="Calendar-day lookback window.")) -> None:
    """Sync GBP/USD and GBP/EUR FX rates."""
    from vmarket.services.fx_service import sync_fx_rates

    with get_session() as session:
        count = sync_fx_rates(session, base="GBP", quotes=["USD", "EUR"], days=days)
        session.commit()

    success(f"FX rates synced: [bold]{count}[/bold] rows")
