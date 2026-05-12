from __future__ import annotations

import json
from pathlib import Path

import typer

from vmarket.cli.cash import cash_app
from vmarket.cli.cockpit import cockpit_app
from vmarket.cli.common import console, simple_table, success, warning
from vmarket.cli.consult import consult_app
from vmarket.cli.imports import import_app
from vmarket.cli.portfolio import portfolio_app
from vmarket.cli.report import report_app
from vmarket.cli.research import research_app
from vmarket.cli.sync import sync_app
from vmarket.cli.theme import theme_app
from vmarket.cli.watch import watch_app
from vmarket.db import get_session, init_db
from vmarket.services.data_quality import build_data_quality_report

app = typer.Typer(help="Virtual Market - fake-money investing simulator.")

app.add_typer(cash_app, name="cash")
app.add_typer(cockpit_app, name="cockpit")
app.add_typer(consult_app, name="consult")
app.add_typer(import_app, name="import")
app.add_typer(watch_app, name="watch")
app.add_typer(sync_app, name="sync")
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(report_app, name="report")
app.add_typer(research_app, name="research")
app.add_typer(theme_app, name="theme")


@app.command()
def init(
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to the SQLite database."),
) -> None:
    """Initialise the database and default portfolio."""
    from vmarket.config import get_base_currency
    from vmarket.repositories import portfolios as port_repo

    init_db(db_path)
    with get_session(db_path) as session:
        port_repo.get_or_create_default(session, base_currency=get_base_currency())
        session.commit()

    db_file = db_path or Path("./user_data/vmarket.sqlite")
    success(f"Database initialised at [bold]{db_file}[/bold]")
    success("Default portfolio created.")
    console.print("\nRun [bold]vmarket --help[/bold] to get started.")


@app.command()
def onboard(
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to the SQLite database."),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
) -> None:
    """Create the private local workspace and point the user at cockpit onboarding."""
    from vmarket.config import get_base_currency
    from vmarket.onboarding.service import ensure_user_data_dirs, get_onboarding_state
    from vmarket.repositories import portfolios as port_repo

    user_data = ensure_user_data_dirs()
    init_db(db_path)
    with get_session(db_path) as session:
        port_repo.get_or_create_default(session, base_currency=get_base_currency())
        state = get_onboarding_state(session, db_path=db_path)
        session.commit()

    db_file = db_path or user_data / "vmarket.sqlite"
    success(f"Private workspace ready at [bold]{user_data}[/bold]")
    success(f"Database ready at [bold]{db_file}[/bold]")
    console.print(
        f"\nOpen the cockpit with "
        f"[bold]vmarket cockpit serve --host {host} --port {port}[/bold]"
    )
    console.print(f"Then visit [bold]http://{host}:{port}/onboarding[/bold]")
    for step in state.suggested_next_steps:
        console.print(f"- {step}")


@app.command()
def doctor(
    db_path: Path | None = typer.Option(None, "--db-path", help="Path to the SQLite database."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Inspect local data quality, sync freshness, and profile gaps."""
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
