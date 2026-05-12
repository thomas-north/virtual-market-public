from __future__ import annotations

import json
from pathlib import Path

import typer

from vmarket.cli.cash import cash_app
from vmarket.cli.common import console, simple_table, success, warning
from vmarket.cli.portfolio import portfolio_app, portfolio_buy, portfolio_sell, portfolio_trades
from vmarket.cli.report import chart_app, report_app, report_memo
from vmarket.cli.research import research_app
from vmarket.cli.sync import sync_app, sync_prices
from vmarket.cli.watch import watch_app, watch_list
from vmarket.config import get_base_currency
from vmarket.db import get_session, init_db
from vmarket.services.data_quality import build_data_quality_report

app = typer.Typer(help="Virtual Market - fake-money investing simulator.")

app.add_typer(cash_app, name="cash")
app.add_typer(watch_app, name="watch")
app.add_typer(sync_app, name="sync")
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(report_app, name="report")
app.add_typer(research_app, name="research")


@app.command()
def init(
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to the SQLite database."),
) -> None:
    """Initialise the database and default portfolio."""
    from vmarket.repositories import portfolios as port_repo

    init_db(db_path)
    with get_session(db_path) as session:
        port_repo.get_or_create_default(session, base_currency=get_base_currency())
        session.commit()

    success(f"Database initialised at [bold]{db_path or Path('./user_data/vmarket.sqlite')}[/bold]")
    success("Default portfolio created.")
    console.print("\nRun [bold]vmarket --help[/bold] to get started.")


@app.command()
def doctor(
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to the SQLite database."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Inspect local data quality and sync freshness."""
    init_db(db_path)
    with get_session(db_path) as session:
        report = build_data_quality_report(session)

    if json_output:
        console.print(json.dumps(report.model_dump(mode="json"), indent=2))
        return

    table = simple_table("Severity", "Label", "Message", "Symbols")
    for issue in report.issues:
        table.add_row(
            issue.severity,
            issue.label,
            issue.message,
            ", ".join(issue.symbols) if issue.symbols else "—",
        )

    console.print(table)
    if report.warning_count:
        warning(f"{report.warning_count} active warning(s) detected.")
    else:
        success("No active warnings detected.")


@app.command("watchlist")
def watchlist_alias() -> None:
    """Compatibility alias for `vmarket watch list`."""
    watch_list()


@app.command("prices")
def prices_alias(
    symbol: str | None = typer.Option(None, "--symbol", help="Sync one instrument only."),
    days: int = typer.Option(7, "--days", help="Calendar-day lookback window."),
) -> None:
    """Compatibility alias for `vmarket sync prices`."""
    sync_prices(symbol=symbol, days=days)


@app.command("buy")
def buy_alias(
    symbol: str = typer.Argument(..., help="Instrument symbol."),
    quantity: float = typer.Option(..., "--quantity", "-q"),
    price: float | None = typer.Option(None, "--price"),
    currency: str | None = typer.Option(None, "--currency"),
) -> None:
    """Compatibility alias for `vmarket portfolio buy`."""
    portfolio_buy(symbol=symbol, quantity=quantity, price=price, currency=currency)


@app.command("sell")
def sell_alias(
    symbol: str = typer.Argument(..., help="Instrument symbol."),
    quantity: float = typer.Option(..., "--quantity", "-q"),
    price: float | None = typer.Option(None, "--price"),
    currency: str | None = typer.Option(None, "--currency"),
) -> None:
    """Compatibility alias for `vmarket portfolio sell`."""
    portfolio_sell(symbol=symbol, quantity=quantity, price=price, currency=currency)


@app.command("trades")
def trades_alias() -> None:
    """Compatibility alias for `vmarket portfolio trades`."""
    portfolio_trades()


memo_app = typer.Typer(help="Generate portfolio memos.")
memo_app.command("daily")(report_memo)
app.add_typer(memo_app, name="memo")
app.add_typer(chart_app, name="chart")
