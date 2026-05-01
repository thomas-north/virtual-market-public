from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from vmarket.models.fx import FxRate


def upsert_fx_rate(
    session: Session,
    fx_date: date,
    base: str,
    quote: str,
    rate: Decimal,
    source: str,
) -> None:
    stmt = (
        sqlite_insert(FxRate)
        .values(date=fx_date, base_currency=base, quote_currency=quote, rate=rate, source=source)
        .on_conflict_do_update(
            index_elements=["date", "base_currency", "quote_currency", "source"],
            set_={"rate": rate},
        )
    )
    session.execute(stmt)


def get_rate(
    session: Session, fx_date: date, base: str, quote: str
) -> Decimal | None:
    row = session.scalar(
        select(FxRate).where(
            FxRate.date == fx_date,
            FxRate.base_currency == base,
            FxRate.quote_currency == quote,
        )
    )
    return row.rate if row else None


def get_latest_rate(session: Session, base: str, quote: str) -> tuple[date, Decimal] | None:
    row = session.scalar(
        select(FxRate)
        .where(FxRate.base_currency == base, FxRate.quote_currency == quote)
        .order_by(FxRate.date.desc())
        .limit(1)
    )
    return (row.date, row.rate) if row else None
