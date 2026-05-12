from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from vmarket.config import get_base_currency
from vmarket.db import get_session, init_db
from vmarket.errors import VMarketError

app = typer.Typer(help="Virtual Market — fake-money investing simulator.")
cash_app = typer.Typer(help="Manage fake cash.")
watch_app = typer.Typer(help="Manage watchlist.")
sync_app = typer.Typer(help="Sync market data.")
memo_app = typer.Typer(help="Generate memos.")
chart_app = typer.Typer(help="Visualise portfolio data.")
research_app = typer.Typer(help="Manage private research workspace.")

app.add_typer(cash_app, name="cash")
app.add_typer(watch_app, name="watch")
app.add_typer(sync_app, name="sync")
app.add_typer(memo_app, name="memo")
app.add_typer(chart_app, name="chart")
app.add_typer(research_app, name="research")

console = Console()
err_console = Console(stderr=True)


def _abort(msg: str) -> None:
    err_console.print(f"[bold red]Error:[/bold red] {msg}")
    raise typer.Exit(1)


# ─── init ────────────────────────────────────────────────────────────────────

@app.command()
def init(
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to SQLite database."),
) -> None:
    """Initialise the database and default portfolio."""
    from vmarket.config import get_base_currency
    from vmarket.repositories import portfolios as port_repo

    init_db(db_path)
    with get_session(db_path) as session:
        port_repo.get_or_create_default(session, base_currency=get_base_currency())
        session.commit()

    db_file = db_path or Path("./data/vmarket.sqlite")
    console.print(f"[green]✓[/green] Database initialised at [bold]{db_file}[/bold]")
    console.print("[green]✓[/green] Default portfolio created.")
    console.print("\nRun [bold]vmarket --help[/bold] to get started.")


# ─── cash ────────────────────────────────────────────────────────────────────

@cash_app.command("deposit")
def cash_deposit(
    amount: float = typer.Argument(..., help="Amount to deposit."),
    currency: str = typer.Option(get_base_currency(), "--currency", "-c"),
) -> None:
    """Deposit fake cash."""
    from vmarket.services.cash_service import deposit

    with get_session() as session:
        try:
            deposit(session, Decimal(str(amount)), currency)
            session.commit()
        except VMarketError as exc:
            _abort(str(exc))

    console.print(f"[green]✓[/green] Deposited [bold]{amount:.2f} {currency.upper()}[/bold]")


@cash_app.command("withdraw")
def cash_withdraw(
    amount: float = typer.Argument(..., help="Amount to withdraw."),
    currency: str = typer.Option(get_base_currency(), "--currency", "-c"),
) -> None:
    """Withdraw fake cash."""
    from vmarket.services.cash_service import withdraw

    with get_session() as session:
        try:
            withdraw(session, Decimal(str(amount)), currency)
            session.commit()
        except VMarketError as exc:
            _abort(str(exc))

    console.print(f"[green]✓[/green] Withdrew [bold]{amount:.2f} {currency.upper()}[/bold]")


@cash_app.command("balance")
def cash_balance() -> None:
    """Show fake cash balances."""
    from vmarket.services.cash_service import get_all_balances

    with get_session() as session:
        balances = get_all_balances(session)
        session.commit()

    if not balances:
        console.print("No cash balances found.")
        return

    table = Table("Currency", "Balance", box=box.SIMPLE)
    for currency, bal in sorted(balances.items()):
        table.add_row(currency, f"{bal:,.2f}")
    console.print(table)


# ─── watchlist ───────────────────────────────────────────────────────────────

@watch_app.command("add")
def watch_add(
    symbol: str = typer.Argument(...),
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
            _abort(str(exc))

    console.print(f"[green]✓[/green] Added [bold]{symbol}[/bold] to watchlist.")


@watch_app.command("remove")
def watch_remove(symbol: str = typer.Argument(...)) -> None:
    """Remove an instrument from the watchlist."""
    from vmarket.services.watchlist_service import remove_from_watchlist

    with get_session() as session:
        removed = remove_from_watchlist(session, symbol)
        session.commit()

    if removed:
        console.print(f"[green]✓[/green] Removed [bold]{symbol}[/bold] from watchlist.")
    else:
        console.print(f"[yellow]Warning:[/yellow] {symbol} was not on the watchlist.")


@watch_app.command("target")
def watch_target(
    symbol: str = typer.Argument(...),
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

    if item:
        console.print(f"[green]✓[/green] Targets updated for [bold]{symbol}[/bold].")
    else:
        _abort(f"{symbol} not found in watchlist.")


@app.command("watchlist")
def show_watchlist() -> None:
    """Show the watchlist."""
    from vmarket.repositories import prices as price_repo
    from vmarket.services.watchlist_service import list_watchlist

    with get_session() as session:
        items = list_watchlist(session)
        rows = []
        for item in items:
            bar = price_repo.get_latest(session, item.instrument_id)
            price = f"{price_repo.best_price(bar):,.4f}" if bar else "—"
            rows.append((
                item.instrument.symbol,
                item.instrument.name or "",
                item.instrument.currency or "",
                item.instrument.asset_type or "",
                price,
                f"{item.target_buy_price:,.4f}" if item.target_buy_price else "—",
                f"{item.target_sell_price:,.4f}" if item.target_sell_price else "—",
            ))

    if not rows:
        console.print("Watchlist is empty.")
        return

    table = Table(
        "Symbol",
        "Name",
        "CCY",
        "Type",
        "Latest",
        "Buy Target",
        "Sell Target",
        box=box.SIMPLE,
    )
    for row in rows:
        table.add_row(*row)
    console.print(table)


# ─── sync ────────────────────────────────────────────────────────────────────

@sync_app.command("prices")
def sync_prices(
    symbol: str | None = typer.Option(None, "--symbol"),
    days: int = typer.Option(7, "--days"),
) -> None:
    """Sync daily prices from market data providers."""
    from vmarket.services.market_data_service import sync_prices as _sync

    with get_session() as session:
        result = _sync(session, symbol=symbol, days=days)
        session.commit()

    console.print("\n[bold]Price sync complete.[/bold]")
    console.print(f"Fetched:  {result.fetched} instruments")
    console.print(f"Updated:  {result.updated_bars} price bars")
    console.print(f"Failed:   {len(result.failed)} instruments")
    if result.failed:
        console.print(f"Failed symbols: {', '.join(result.failed)}")
    for w in result.warnings:
        console.print(f"[yellow]Warning:[/yellow] {w}")


@sync_app.command("fx")
def sync_fx(days: int = typer.Option(7, "--days")) -> None:
    """Sync GBP/USD and GBP/EUR FX rates via Frankfurter (free, no key)."""
    from vmarket.services.fx_service import sync_fx_rates

    with get_session() as session:
        count = sync_fx_rates(session, base="GBP", quotes=["USD", "EUR"], days=days)
        session.commit()

    console.print(f"[green]✓[/green] FX rates synced: {count} rows")


@app.command("prices")
def show_prices(
    symbol: str = typer.Argument(...),
    days: int = typer.Option(30, "--days"),
) -> None:
    """Show recent prices for an instrument."""
    from datetime import timedelta

    from vmarket.repositories import instruments as inst_repo
    from vmarket.repositories import prices as price_repo

    with get_session() as session:
        instrument = inst_repo.get_by_symbol(session, symbol)
        if not instrument:
            _abort(f"Instrument {symbol} not found.")

        end = date.today()
        start = end - timedelta(days=days - 1)
        bars = price_repo.get_prices_for_range(session, instrument.id, start, end)

        rows = [
            (str(b.date), f"{b.open or '—'}", f"{b.high or '—'}", f"{b.low or '—'}",
             f"{b.close:.4f}", f"{b.adjusted_close:.4f}" if b.adjusted_close else "—",
             str(b.volume or "—"), b.source)
            for b in reversed(bars)
        ]

    if not rows:
        console.print(f"No prices found for {symbol} in the last {days} days.")
        return

    table = Table(
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
        "Adj Close",
        "Volume",
        "Source",
        box=box.SIMPLE,
    )
    for row in rows:
        table.add_row(*row)
    console.print(table)


# ─── trading ─────────────────────────────────────────────────────────────────

@app.command()
def buy(
    symbol: str = typer.Argument(...),
    quantity: float = typer.Option(..., "--quantity", "-q"),
    price: float | None = typer.Option(None, "--price"),
    currency: str | None = typer.Option(None, "--currency"),
) -> None:
    """Buy an instrument using fake money."""
    from vmarket.services.trade_service import buy as _buy

    with get_session() as session:
        try:
            trade = _buy(
                session,
                symbol=symbol,
                quantity=Decimal(str(quantity)),
                price=Decimal(str(price)) if price is not None else None,
                currency=currency,
            )
            session.commit()
        except VMarketError as exc:
            _abort(str(exc))

    console.print(
        f"[green]✓[/green] Bought [bold]{quantity} {symbol}[/bold] @ "
        f"{trade.price:.4f} {trade.currency}"
    )


@app.command()
def sell(
    symbol: str = typer.Argument(...),
    quantity: float = typer.Option(..., "--quantity", "-q"),
    price: float | None = typer.Option(None, "--price"),
    currency: str | None = typer.Option(None, "--currency"),
) -> None:
    """Sell an instrument."""
    from vmarket.services.trade_service import sell as _sell

    with get_session() as session:
        try:
            trade = _sell(
                session,
                symbol=symbol,
                quantity=Decimal(str(quantity)),
                price=Decimal(str(price)) if price is not None else None,
                currency=currency,
            )
            session.commit()
        except VMarketError as exc:
            _abort(str(exc))

    console.print(
        f"[green]✓[/green] Sold [bold]{quantity} {symbol}[/bold] @ "
        f"{trade.price:.4f} {trade.currency}"
    )


@app.command()
def trades() -> None:
    """Show trade history."""
    from vmarket.repositories import portfolios as port_repo
    from vmarket.repositories import trades as trade_repo

    with get_session() as session:
        portfolio = port_repo.get_or_create_default(session)
        all_trades = trade_repo.list_trades(session, portfolio.id)
        rows = [
            (
                str(t.trade_date),
                t.side.upper(),
                t.instrument.symbol,
                f"{t.quantity:.4f}",
                f"{t.price:.4f}",
                t.currency,
                t.price_source,
                t.notes or "",
            )
            for t in all_trades
        ]
        session.commit()

    if not rows:
        console.print("No trades found.")
        return

    table = Table(
        "Date",
        "Side",
        "Symbol",
        "Qty",
        "Price",
        "CCY",
        "Source",
        "Notes",
        box=box.SIMPLE,
    )
    for row in rows:
        table.add_row(*row)
    console.print(table)


# ─── portfolio ───────────────────────────────────────────────────────────────

@app.command()
def portfolio(
    base: str | None = typer.Option(None, "--base"),
) -> None:
    """Show portfolio holdings and valuations."""
    from vmarket.services.valuation_service import compute_positions

    with get_session() as session:
        positions = compute_positions(session, base_currency=base)

    if not positions:
        console.print("No open positions.")
        return

    table = Table(
        "Symbol", "Name", "Qty", "Avg Cost", "Latest", "Mkt Value",
        "P/L", "P/L %", "CCY", "Base Value",
        box=box.SIMPLE,
    )
    for p in positions:
        pnl_pct = f"{p.unrealised_pnl_pct:.1f}%" if p.unrealised_pnl_pct is not None else "N/A"
        stale = " ⚠" if p.stale else ""
        fx_warn = " ¹" if p.fx_missing else ""
        table.add_row(
            p.symbol,
            (p.name or "")[:30],
            f"{p.quantity:.4f}",
            f"{p.avg_cost:.4f}",
            f"{p.latest_price:.4f}{stale}" if p.latest_price else "—",
            f"{p.market_value:.2f}{fx_warn}" if p.market_value else "—",
            f"{p.unrealised_pnl:.2f}" if p.unrealised_pnl else "—",
            pnl_pct,
            p.cost_currency,
            f"{p.value_in_base:.2f}" if p.value_in_base else "—",
        )
    console.print(table)

    if any(p.stale for p in positions):
        console.print(f"[yellow]⚠ Stale price (>{5} calendar days old)[/yellow]")
    if any(p.fx_missing for p in positions):
        console.print("[yellow]¹ FX rate missing — native currency shown[/yellow]")


# ─── memo ─────────────────────────────────────────────────────────────────────

@memo_app.command("daily")
def memo_daily(
    output: Path | None = typer.Option(None, "--output", "-o"),
) -> None:
    """Generate daily financial memo."""
    from vmarket.reports.daily_memo import write_or_print

    with get_session() as session:
        content = write_or_print(session, output=output)
        session.commit()

    if output:
        console.print(f"[green]✓[/green] Memo written to [bold]{output}[/bold]")
    else:
        console.print(content)


# ─── charts ───────────────────────────────────────────────────────────────────

@chart_app.command("portfolio")
def chart_portfolio(
    days: int = typer.Option(30, "--days", "-d", help="7, 30, or 90 days"),
    html: Path | None = typer.Option(None, "--html", help="Also export interactive HTML"),
) -> None:
    """Line chart: total portfolio value over time."""
    from vmarket.reports.charts import chart_portfolio_value

    with get_session() as session:
        chart_portfolio_value(session, days=days, html=html)
        session.commit()


@chart_app.command("allocation")
def chart_allocation(
    html: Path | None = typer.Option(None, "--html", help="Also export interactive HTML donut"),
) -> None:
    """Bar chart: current allocation by holding (% of invested)."""
    from vmarket.reports.charts import chart_allocation as _chart

    with get_session() as session:
        _chart(session, html=html)
        session.commit()


@chart_app.command("pnl")
def chart_pnl(
    html: Path | None = typer.Option(None, "--html", help="Also export interactive HTML"),
) -> None:
    """Bar chart: unrealised P/L % per holding."""
    from vmarket.reports.charts import chart_pnl as _chart

    with get_session() as session:
        _chart(session, html=html)
        session.commit()


# ─── research ─────────────────────────────────────────────────────────────────

@research_app.command("init")
def research_init(
    root: Path = typer.Option(Path("research"), "--root", help="Research workspace root."),
) -> None:
    """Initialise private research and LLM wiki directories."""
    from vmarket.research.wiki import append_log_entry, init_research_workspace

    created = init_research_workspace(root)
    append_log_entry("research init", root=root)

    console.print(f"[green]✓[/green] Research workspace ready at [bold]{root}[/bold]")
    console.print("[dim]Private research paths are ignored by git.[/dim]")
    for path in created:
        console.print(f"- {path}")


@research_app.command("brief")
def research_brief(
    symbol: str = typer.Argument(..., help="Symbol to brief, e.g. META.US"),
    root: Path = typer.Option(Path("research"), "--root", help="Research workspace root."),
) -> None:
    """Render a brief from local normalized research evidence."""
    from vmarket.research.brief import render_evidence_brief
    from vmarket.research.store import read_symbol_evidence

    items = read_symbol_evidence(symbol, root=root)
    console.print(render_evidence_brief(symbol, items))


@research_app.command("collect-sec")
def research_collect_sec(
    symbol: str = typer.Argument(..., help="Symbol to collect, e.g. META.US"),
    cik: str = typer.Option(..., "--cik", help="SEC CIK for the company."),
    company_name: str | None = typer.Option(None, "--company-name"),
    days: int = typer.Option(30, "--days", help="Lookback window."),
    root: Path = typer.Option(Path("research"), "--root", help="Research workspace root."),
) -> None:
    """Collect recent SEC EDGAR filings into private normalized evidence."""
    from vmarket.research.sec import collect_recent_sec_evidence
    from vmarket.research.store import evidence_path, write_evidence_items
    from vmarket.research.wiki import append_log_entry, init_research_workspace

    init_research_workspace(root)
    items = collect_recent_sec_evidence(
        symbol=symbol,
        cik=cik,
        company_name=company_name,
        days=days,
    )
    output = evidence_path(symbol, root=root)
    count = write_evidence_items(output, items)
    append_log_entry(f"collect-sec {symbol.upper()} items={count}", root=root)

    console.print(
        f"[green]✓[/green] Wrote [bold]{count}[/bold] SEC evidence items to [bold]{output}[/bold]"
    )
