from __future__ import annotations

from decimal import Decimal

import typer
from rich import box
from rich.console import Console
from rich.table import Table

console = Console()
err_console = Console(stderr=True)


def abort(message: str) -> None:
    err_console.print(f"[bold red]Error:[/bold red] {message}")
    raise typer.Exit(1)


def success(message: str) -> None:
    console.print(f"[green]OK[/green] {message}")


def warning(message: str) -> None:
    console.print(f"[yellow]Warning:[/yellow] {message}")


def info(message: str) -> None:
    console.print(message)


def simple_table(*headers: str) -> Table:
    return Table(*headers, box=box.SIMPLE)


def format_decimal(value: Decimal | None, places: int = 2, missing: str = "-") -> str:
    if value is None:
        return missing
    return f"{value:,.{places}f}"
