from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import typer

from vmarket.cli.common import abort, console, format_decimal, simple_table, success, warning
from vmarket.db import get_session
from vmarket.errors import VMarketError

portfolio_app = typer.Typer(help="Inspect and trade the portfolio.")


@portfolio_app.command("show")
def portfolio_show(
    base: str | None = typer.Option(None, "--base", help="Base currency override."),
) -> None:
    """Show portfolio holdings and valuations."""
    from vmarket.services.valuation_service import compute_positions

    with get_session() as session:
        positions = compute_positions(session, base_currency=base)

    if not positions:
        console.print(
            "No open positions yet. Use `vmarket portfolio buy` after funding the account."
        )
        return

    table = simple_table(
        "Symbol",
        "Name",
        "Qty",
        "Avg Cost",
        "Latest",
        "Status",
        "Mkt Value",
        "P/L",
        "P/L %",
        "CCY",
        "Base Value",
        "FX",
    )
    for position in positions:
        pnl_pct = (
            f"{position.unrealised_pnl_pct:.1f}%"
            if position.unrealised_pnl_pct is not None
            else "N/A"
        )
        table.add_row(
            position.symbol,
            (position.name or "")[:30],
            f"{position.quantity:.4f}",
            f"{position.avg_cost:.4f}",
            f"{position.latest_price:.4f}" if position.latest_price is not None else "-",
            position.price_status,
            format_decimal(position.market_value),
            format_decimal(position.unrealised_pnl),
            pnl_pct,
            position.cost_currency,
            format_decimal(position.value_in_base),
            position.fx_status.replace("_", " "),
        )
    console.print(table)

    status_notes = {
        position.price_status_note
        for position in positions
        if position.price_status_note and position.price_status != "fresh"
    }
    for note in sorted(status_notes):
        warning(note)
    if any(position.fx_missing for position in positions):
        warning("Some valuations are missing FX rates.")
    elif any(position.fx_stale for position in positions):
        warning("Some valuations use stale FX rates.")


@portfolio_app.command("prices")
def portfolio_prices(
    symbol: str = typer.Argument(..., help="Instrument symbol."),
    days: int = typer.Option(30, "--days", help="Calendar-day lookback window."),
) -> None:
    """Show recent prices for one instrument."""
    from vmarket.repositories import instruments as inst_repo
    from vmarket.repositories import prices as price_repo
    from vmarket.services.freshness import price_status_for

    with get_session() as session:
        instrument = inst_repo.get_by_symbol(session, symbol)
        if not instrument:
            abort(f"Instrument {symbol} was not found.")

        end = date.today()
        start = end - timedelta(days=days - 1)
        bars = price_repo.get_prices_for_range(session, instrument.id, start, end)

    if not bars:
        status = price_status_for(symbol, None)
        console.print(f"No price history found for {symbol}.")
        warning(status.note)
        return

    status = price_status_for(symbol, bars[-1].date)
    table = simple_table("Date", "Open", "High", "Low", "Close", "Adj Close", "Volume", "Source")
    for bar in reversed(bars):
        table.add_row(
            str(bar.date),
            f"{bar.open}" if bar.open is not None else "-",
            f"{bar.high}" if bar.high is not None else "-",
            f"{bar.low}" if bar.low is not None else "-",
            f"{bar.close:.4f}",
            f"{bar.adjusted_close:.4f}" if bar.adjusted_close is not None else "-",
            str(bar.volume or "-"),
            bar.source,
        )
    console.print(table)
    warning(status.note)


@portfolio_app.command("buy")
def portfolio_buy(
    symbol: str = typer.Argument(..., help="Instrument symbol."),
    quantity: float = typer.Option(..., "--quantity", "-q"),
    price: float | None = typer.Option(None, "--price"),
    currency: str | None = typer.Option(None, "--currency"),
) -> None:
    """Buy an instrument using fake cash."""
    from vmarket.services.trade_service import buy

    with get_session() as session:
        try:
            trade = buy(
                session,
                symbol=symbol,
                quantity=Decimal(str(quantity)),
                price=Decimal(str(price)) if price is not None else None,
                currency=currency,
            )
            session.commit()
        except VMarketError as exc:
            abort(str(exc))

    success(f"Bought [bold]{quantity} {symbol}[/bold] @ {trade.price:.4f} {trade.currency}")


@portfolio_app.command("sell")
def portfolio_sell(
    symbol: str = typer.Argument(..., help="Instrument symbol."),
    quantity: float = typer.Option(..., "--quantity", "-q"),
    price: float | None = typer.Option(None, "--price"),
    currency: str | None = typer.Option(None, "--currency"),
) -> None:
    """Sell an instrument."""
    from vmarket.services.trade_service import sell

    with get_session() as session:
        try:
            trade = sell(
                session,
                symbol=symbol,
                quantity=Decimal(str(quantity)),
                price=Decimal(str(price)) if price is not None else None,
                currency=currency,
            )
            session.commit()
        except VMarketError as exc:
            abort(str(exc))

    success(f"Sold [bold]{quantity} {symbol}[/bold] @ {trade.price:.4f} {trade.currency}")


@portfolio_app.command("trades")
def portfolio_trades() -> None:
    """Show trade history."""
    from vmarket.repositories import portfolios as port_repo
    from vmarket.repositories import trades as trade_repo

    with get_session() as session:
        portfolio = port_repo.get_or_create_default(session)
        trades = trade_repo.list_trades(session, portfolio.id)

    if not trades:
        console.print("No trades recorded yet.")
        return

    table = simple_table("Date", "Side", "Symbol", "Qty", "Price", "CCY", "Source", "Notes")
    for trade in trades:
        table.add_row(
            str(trade.trade_date),
            trade.side.upper(),
            trade.instrument.symbol,
            f"{trade.quantity:.4f}",
            f"{trade.price:.4f}",
            trade.currency,
            trade.price_source,
            trade.notes or "",
        )
    console.print(table)
