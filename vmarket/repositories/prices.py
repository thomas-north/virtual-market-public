from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from vmarket.dto.price_bar import PriceBarDTO
from vmarket.models.price import PriceBar


def upsert_price_bars(session: Session, instrument_id: int, bars: list[PriceBarDTO]) -> int:
    """Insert or update price bars. Returns number of rows affected."""
    if not bars:
        return 0
    count = 0
    for bar in bars:
        stmt = (
            sqlite_insert(PriceBar)
            .values(
                instrument_id=instrument_id,
                date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                adjusted_close=bar.adjusted_close,
                volume=bar.volume,
                currency=bar.currency,
                source=bar.source,
            )
            .on_conflict_do_update(
                index_elements=["instrument_id", "date", "source"],
                set_={
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "adjusted_close": bar.adjusted_close,
                    "volume": bar.volume,
                    "currency": bar.currency,
                },
            )
        )
        session.execute(stmt)
        count += 1
    return count


def get_latest(session: Session, instrument_id: int) -> PriceBar | None:
    return session.scalar(
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument_id)
        .order_by(PriceBar.date.desc(), PriceBar.id.desc())
        .limit(1)
    )


def get_prices_for_range(
    session: Session, instrument_id: int, start: date, end: date
) -> list[PriceBar]:
    return list(
        session.scalars(
            select(PriceBar)
            .where(
                PriceBar.instrument_id == instrument_id,
                PriceBar.date >= start,
                PriceBar.date <= end,
            )
            .order_by(PriceBar.date.asc())
        )
    )


def best_price(bar: PriceBar) -> Decimal:
    """Return adjusted_close if available, else close."""
    return bar.adjusted_close if bar.adjusted_close is not None else bar.close
