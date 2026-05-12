from __future__ import annotations

from pathlib import Path

import typer

from vmarket.cli.common import console, success

research_app = typer.Typer(help="Manage the private research workspace.")


@research_app.command("init")
def research_init(
    root: Path = typer.Option(Path("research"), "--root", help="Research workspace root."),
) -> None:
    """Initialise private research and wiki directories."""
    from vmarket.research.wiki import append_log_entry, init_research_workspace

    created = init_research_workspace(root)
    append_log_entry("research init", root=root)

    success(f"Research workspace ready at [bold]{root}[/bold]")
    console.print("[dim]Private research paths stay ignored by git.[/dim]")
    for path in created:
        console.print(f"- {path}")


@research_app.command("brief")
def research_brief(
    symbol: str = typer.Argument(..., help="Symbol to brief, for example META.US."),
    root: Path = typer.Option(Path("research"), "--root", help="Research workspace root."),
) -> None:
    """Render a brief from local normalized evidence."""
    from vmarket.research.brief import render_evidence_brief
    from vmarket.research.store import read_symbol_evidence

    items = read_symbol_evidence(symbol, root=root)
    console.print(render_evidence_brief(symbol, items))


@research_app.command("collect-sec")
def research_collect_sec(
    symbol: str = typer.Argument(..., help="Symbol to collect, for example META.US."),
    cik: str = typer.Option(..., "--cik", help="SEC CIK for the company."),
    company_name: str | None = typer.Option(None, "--company-name"),
    days: int = typer.Option(30, "--days", help="Lookback window."),
    root: Path = typer.Option(Path("research"), "--root", help="Research workspace root."),
) -> None:
    """Collect recent SEC EDGAR filings into local normalized evidence."""
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

    success(f"Wrote [bold]{count}[/bold] SEC evidence items to [bold]{output}[/bold]")
