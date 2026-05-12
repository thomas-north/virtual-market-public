from __future__ import annotations

from decimal import Decimal

import typer

from vmarket.cli.common import abort, console, simple_table, success, warning
from vmarket.db import get_session
from vmarket.errors import VMarketError
from vmarket.repositories import prices as price_repo
from vmarket.services.freshness import price_status_for

watch_app = typer.Typer(help="Manage the watchlist.")


@watch_app.command("add")
def watch_add(
    symbol: str = typer.Argument(..., help="Instrument symbol."),
    name: str | None = typer.Option(None, "--name"),
    currency: str | None = typer.Option(None, "--currency"),
    asset_type: str | None = typer.Option(None, "--asset-type"),
) -> None:
    """Add an instrument to the watchlist."""
    from vmarket.services.watchlist_service import add_to_watchlist

    with get_session() as session:
        try:
            add_to_watchlist(session, symbol, name=name, currency=currency, asset_type=asset_type)
            session.commit()
        except VMarketError as exc:
            abort(str(exc))

    success(f"Added [bold]{symbol}[/bold] to the watchlist.")


@watch_app.command("remove")
def watch_remove(symbol: str = typer.Argument(..., help="Instrument symbol.")) -> None:
    """Remove an instrument from the watchlist."""
    from vmarket.services.watchlist_service import remove_from_watchlist

    with get_session() as session:
        removed = remove_from_watchlist(session, symbol)
        session.commit()

    if removed:
        success(f"Removed [bold]{symbol}[/bold] from the watchlist.")
    else:
        warning(f"{symbol} was not on the watchlist.")


@watch_app.command("target")
def watch_target(
    symbol: str = typer.Argument(..., help="Instrument symbol."),
    buy_below: float | None = typer.Option(None, "--buy-below"),
    sell_above: float | None = typer.Option(None, "--sell-above"),
) -> None:
    """Set target prices for a watchlist instrument."""
    from vmarket.services.watchlist_service import set_targets

    with get_session() as session:
        item = set_targets(
            session,
            symbol,
            buy_below=Decimal(str(buy_below)) if buy_below is not None else None,
            sell_above=Decimal(str(sell_above)) if sell_above is not None else None,
        )
        session.commit()

    if item is None:
        abort(f"{symbol} is not on the watchlist.")
    success(f"Updated targets for [bold]{symbol}[/bold].")


@watch_app.command("list")
def watch_list() -> None:
    """Show watchlist prices and freshness."""
    from vmarket.services.watchlist_service import list_watchlist

    with get_session() as session:
        items = list_watchlist(session)
        rows: list[tuple[str, str, str, str, str, str, str, str]] = []
        for item in items:
            bar = price_repo.get_latest(session, item.instrument_id)
            price = f"{price_repo.best_price(bar):,.4f}" if bar else "-"
            status = price_status_for(item.instrument.symbol, bar.date if bar else None)
            rows.append(
                (
                    item.instrument.symbol,
                    item.instrument.name or "",
                    item.instrument.currency or "",
                    item.instrument.asset_type or "",
                    price,
                    status.label,
                    f"{item.target_buy_price:,.4f}" if item.target_buy_price else "-",
                    f"{item.target_sell_price:,.4f}" if item.target_sell_price else "-",
                )
            )

    if not rows:
        console.print("The watchlist is empty. Add one with `vmarket watch add SYMBOL`.")
        return

    table = simple_table(
        "Symbol",
        "Name",
        "CCY",
        "Type",
        "Latest",
        "Status",
        "Buy Target",
        "Sell Target",
    )
    for row in rows:
        table.add_row(*row)
    console.print(table)
