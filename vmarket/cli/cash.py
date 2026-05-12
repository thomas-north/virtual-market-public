from __future__ import annotations

from decimal import Decimal

import typer

from vmarket.cli.common import abort, console, format_decimal, simple_table, success
from vmarket.config import get_base_currency
from vmarket.db import get_session
from vmarket.errors import VMarketError

cash_app = typer.Typer(help="Manage fake cash balances.")


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
            abort(str(exc))

    success(f"Deposited [bold]{amount:.2f} {currency.upper()}[/bold]")


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
            abort(str(exc))

    success(f"Withdrew [bold]{amount:.2f} {currency.upper()}[/bold]")


@cash_app.command("balance")
def cash_balance() -> None:
    """Show fake cash balances."""
    from vmarket.services.cash_service import get_all_balances

    with get_session() as session:
        balances = get_all_balances(session)

    if not balances:
        console.print("No fake cash balances yet. Use `vmarket cash deposit` to get started.")
        return

    table = simple_table("Currency", "Balance")
    for currency, balance in sorted(balances.items()):
        table.add_row(currency, format_decimal(balance))
    console.print(table)
