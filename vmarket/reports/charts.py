"""Terminal charts using plotext and optional HTML export via plotly."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import plotext as plt
from rich import box
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session

from vmarket.services.chart_service import portfolio_value_series
from vmarket.services.valuation_service import compute_positions

console = Console()


# ── portfolio value over time ─────────────────────────────────────────────────

def chart_portfolio_value(session: Session, days: int = 30, html: Path | None = None) -> None:
    points = portfolio_value_series(session, days=days)

    if not points:
        console.print("[yellow]No data for portfolio value chart.[/yellow]")
        return

    dates = [p.date.isoformat() for p in points]
    total_vals = [float(p.value) for p in points]
    invested_vals = [float(p.invested) for p in points]
    cash_vals = [float(p.cash) for p in points]

    # Filter x-axis labels to avoid crowding
    step = max(1, len(dates) // 8)
    x_labels = [d if i % step == 0 else "" for i, d in enumerate(dates)]

    plt.clf()
    plt.theme("dark")
    plt.plot_size(plt.terminal_width(), 22)
    plt.title(f"Portfolio Value — last {days} days")
    plt.xlabel("Date")
    plt.ylabel("GBP")
    plt.plot(total_vals, label="Total", color="cyan+")
    plt.plot(invested_vals, label="Invested", color="green+")
    plt.plot(cash_vals, label="Cash", color="yellow+")
    plt.xticks(list(range(len(dates))), x_labels)
    plt.show()

    if html is not None:
        _export_value_html(points, html, days)
        console.print(f"[green]✓[/green] Chart saved to [bold]{html}[/bold]")


def _export_value_html(points, path: Path, days: int) -> None:
    try:
        import plotly.graph_objects as go
    except ImportError:
        console.print("[yellow]Install plotly for HTML export: pip install plotly[/yellow]")
        return

    dates = [p.date.isoformat() for p in points]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=[float(p.value) for p in points],
            name="Total",
            line=dict(color="#00bcd4", width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=[float(p.invested) for p in points],
            name="Invested",
            line=dict(color="#4caf50", width=2),
            fill="tozeroy",
            fillcolor="rgba(76,175,80,0.08)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=[float(p.cash) for p in points],
            name="Cash",
            line=dict(color="#ffeb3b", width=1, dash="dot"),
        )
    )
    fig.update_layout(
        title=f"Portfolio Value — last {days} days",
        xaxis_title="Date",
        yaxis_title="GBP",
        template="plotly_dark",
        legend=dict(x=0, y=1),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(path))


# ── allocation bar ────────────────────────────────────────────────────────────

def chart_allocation(session: Session, html: Path | None = None) -> None:
    positions = compute_positions(session)
    positions = [p for p in positions if p.value_in_base is not None and p.value_in_base > 0]

    if not positions:
        _print_chart_gap(
            session,
            "No positions with current mark-to-market prices are available for allocation.",
        )
        return

    total = sum(p.value_in_base for p in positions if p.value_in_base)
    symbols = [p.symbol for p in positions]
    weights = [
        float(p.value_in_base / total * 100) if total and p.value_in_base else 0
        for p in positions
    ]

    plt.clf()
    plt.theme("dark")
    plt.plot_size(plt.terminal_width(), max(14, len(symbols) * 2 + 4))
    plt.title("Portfolio Allocation (% of invested)")
    plt.bar(symbols, weights, orientation="h", color="cyan+")
    plt.xlabel("Weight %")
    plt.show()

    if html is not None:
        _export_allocation_html(positions, total, html)
        console.print(f"[green]✓[/green] Chart saved to [bold]{html}[/bold]")


def _export_allocation_html(positions, total: Decimal, path: Path) -> None:
    try:
        import plotly.graph_objects as go
    except ImportError:
        console.print("[yellow]Install plotly for HTML export: pip install plotly[/yellow]")
        return

    labels = [p.symbol for p in positions]
    values = [float(p.value_in_base) for p in positions if p.value_in_base]
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.4, textinfo="label+percent"))
    fig.update_layout(title="Portfolio Allocation", template="plotly_dark")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(path))


# ── P/L bar ───────────────────────────────────────────────────────────────────

def chart_pnl(session: Session, html: Path | None = None) -> None:
    positions = compute_positions(session)
    positions = [p for p in positions if p.unrealised_pnl_pct is not None]

    if not positions:
        _print_chart_gap(
            session,
            "No unrealised P/L data is available yet. Sync prices or add automatic price coverage.",
        )
        return

    positions_sorted = sorted(positions, key=lambda p: p.unrealised_pnl_pct or Decimal("0"))
    symbols = [p.symbol for p in positions_sorted]
    pcts = [float(p.unrealised_pnl_pct) for p in positions_sorted]
    colors = ["red+" if v < 0 else "green+" for v in pcts]

    plt.clf()
    plt.theme("dark")
    plt.plot_size(plt.terminal_width(), max(14, len(symbols) * 2 + 4))
    plt.title("Unrealised P/L per Holding (%)")
    plt.bar(symbols, pcts, orientation="h", color=colors)
    plt.xlabel("P/L %")
    plt.show()

    if html is not None:
        _export_pnl_html(positions_sorted, html)
        console.print(f"[green]✓[/green] Chart saved to [bold]{html}[/bold]")


def _export_pnl_html(positions, path: Path) -> None:
    try:
        import plotly.graph_objects as go
    except ImportError:
        console.print("[yellow]Install plotly for HTML export: pip install plotly[/yellow]")
        return

    symbols = [p.symbol for p in positions]
    pcts = [float(p.unrealised_pnl_pct) for p in positions]
    colors = ["#f44336" if v < 0 else "#4caf50" for v in pcts]
    fig = go.Figure(go.Bar(x=pcts, y=symbols, orientation="h", marker_color=colors))
    fig.update_layout(
        title="Unrealised P/L per Holding (%)",
        xaxis_title="P/L %",
        template="plotly_dark",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(path))


def _print_chart_gap(session: Session, message: str) -> None:
    console.print(f"[yellow]{message}[/yellow]")
    positions = compute_positions(session)
    missing = [p for p in positions if p.latest_price is None]
    if not missing:
        return

    table = Table("Symbol", "Status", "Why", box=box.SIMPLE)
    for position in missing:
        table.add_row(position.symbol, position.price_status, position.price_status_note)
    console.print(table)
