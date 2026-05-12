from __future__ import annotations

from pathlib import Path

import typer

from vmarket.cli.common import console, success
from vmarket.db import get_session

report_app = typer.Typer(help="Generate memos, overviews, and charts.")
chart_app = typer.Typer(help="Render portfolio charts.")

report_app.add_typer(chart_app, name="chart")


@report_app.command("overview")
def report_overview(
    html: Path = typer.Option(
        Path("reports/overview.html"),
        "--html",
        help="Output path for the standalone overview page.",
    ),
    days: int = typer.Option(30, "--days", help="Lookback window for portfolio history."),
) -> None:
    """Generate the primary portfolio overview page."""
    from vmarket.reports.overview import write_overview_html

    with get_session() as session:
        output = write_overview_html(session, html, days=days)
        session.commit()

    success(f"Overview written to [bold]{output}[/bold]")


@report_app.command("memo")
def report_memo(
    output: Path | None = typer.Option(None, "--output", "-o", help="Write the memo to a file."),
) -> None:
    """Generate the daily portfolio memo."""
    from vmarket.reports.daily_memo import write_or_print

    with get_session() as session:
        content = write_or_print(session, output=output)
        session.commit()

    if output is not None:
        success(f"Memo written to [bold]{output}[/bold]")
    else:
        console.print(content)


@chart_app.command("portfolio")
def chart_portfolio(
    days: int = typer.Option(30, "--days", "-d", help="7, 30, or 90 days."),
    html: Path | None = typer.Option(None, "--html", help="Optional HTML export path."),
) -> None:
    """Render a total portfolio value chart."""
    from vmarket.reports.charts import chart_portfolio_value

    with get_session() as session:
        chart_portfolio_value(session, days=days, html=html)
        session.commit()


@chart_app.command("allocation")
def chart_allocation(
    html: Path | None = typer.Option(None, "--html", help="Optional HTML export path."),
) -> None:
    """Render a current allocation chart."""
    from vmarket.reports.charts import chart_allocation as render_allocation_chart

    with get_session() as session:
        render_allocation_chart(session, html=html)
        session.commit()


@chart_app.command("pnl")
def chart_pnl(
    html: Path | None = typer.Option(None, "--html", help="Optional HTML export path."),
) -> None:
    """Render unrealised P/L by holding."""
    from vmarket.reports.charts import chart_pnl as render_pnl_chart

    with get_session() as session:
        render_pnl_chart(session, html=html)
        session.commit()
