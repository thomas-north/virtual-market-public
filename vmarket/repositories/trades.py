from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from vmarket.models.trade import Trade


def add_trade(session: Session, trade: Trade) -> Trade:
    session.add(trade)
    session.flush()
    return trade


def list_trades(session: Session, portfolio_id: int) -> list[Trade]:
    return list(
        session.scalars(
            select(Trade)
            .where(Trade.portfolio_id == portfolio_id)
            .order_by(Trade.trade_date.desc(), Trade.created_at.desc())
        )
    )


def list_trades_for_date(session: Session, portfolio_id: int, trade_date: date) -> list[Trade]:
    return list(
        session.scalars(
            select(Trade)
            .where(Trade.portfolio_id == portfolio_id, Trade.trade_date == trade_date)
            .order_by(Trade.created_at.asc())
        )
    )


def list_trades_for_instrument(
    session: Session, portfolio_id: int, instrument_id: int
) -> list[Trade]:
    return list(
        session.scalars(
            select(Trade)
            .where(Trade.portfolio_id == portfolio_id, Trade.instrument_id == instrument_id)
            .order_by(Trade.trade_date.asc(), Trade.created_at.asc())
        )
    )
