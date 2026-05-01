from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from vmarket.errors import InsufficientCashError
from vmarket.models.cash_ledger import CashLedgerEntry
from vmarket.repositories import cash as cash_repo
from vmarket.repositories import portfolios as port_repo


def deposit(
    session: Session,
    amount: Decimal,
    currency: str,
    notes: str | None = None,
    on_date: date | None = None,
) -> CashLedgerEntry:
    portfolio = port_repo.get_or_create_default(session)
    entry = CashLedgerEntry(
        portfolio_id=portfolio.id,
        date=on_date or date.today(),
        currency=currency.upper(),
        amount=amount,
        type="deposit",
        notes=notes,
    )
    return cash_repo.add_entry(session, entry)


def withdraw(
    session: Session,
    amount: Decimal,
    currency: str,
    notes: str | None = None,
    on_date: date | None = None,
) -> CashLedgerEntry:
    portfolio = port_repo.get_or_create_default(session)
    balance = cash_repo.get_balance(session, portfolio.id, currency.upper())
    if balance < amount:
        raise InsufficientCashError(
            f"Insufficient fake cash. Required: {amount} {currency.upper()}. "
            f"Available: {balance} {currency.upper()}."
        )
    entry = CashLedgerEntry(
        portfolio_id=portfolio.id,
        date=on_date or date.today(),
        currency=currency.upper(),
        amount=-amount,
        type="withdrawal",
        notes=notes,
    )
    return cash_repo.add_entry(session, entry)


def get_balance(session: Session, currency: str) -> Decimal:
    portfolio = port_repo.get_or_create_default(session)
    return cash_repo.get_balance(session, portfolio.id, currency.upper())


def get_all_balances(session: Session) -> dict[str, Decimal]:
    portfolio = port_repo.get_or_create_default(session)
    return cash_repo.get_balances_all_currencies(session, portfolio.id)
