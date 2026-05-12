from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vmarket.models.cash_ledger import CashLedgerEntry


def add_entry(session: Session, entry: CashLedgerEntry) -> CashLedgerEntry:
    session.add(entry)
    session.flush()
    return entry


def get_balance(session: Session, portfolio_id: int, currency: str) -> Decimal:
    result = session.scalar(
        select(func.sum(CashLedgerEntry.amount)).where(
            CashLedgerEntry.portfolio_id == portfolio_id,
            CashLedgerEntry.currency == currency,
        )
    )
    return Decimal(str(result)) if result is not None else Decimal("0")


def get_balances_all_currencies(session: Session, portfolio_id: int) -> dict[str, Decimal]:
    rows = session.execute(
        select(CashLedgerEntry.currency, func.sum(CashLedgerEntry.amount))
        .where(CashLedgerEntry.portfolio_id == portfolio_id)
        .group_by(CashLedgerEntry.currency)
    ).all()
    return {currency: Decimal(str(amount)) for currency, amount in rows}


def list_entries(session: Session, portfolio_id: int) -> list[CashLedgerEntry]:
    return list(
        session.scalars(
            select(CashLedgerEntry)
            .where(CashLedgerEntry.portfolio_id == portfolio_id)
            .order_by(CashLedgerEntry.date.desc(), CashLedgerEntry.created_at.desc())
        )
    )
