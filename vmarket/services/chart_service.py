"""Compute data series for charts from existing trade and price history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from vmarket.models.cash_ledger import CashLedgerEntry
from vmarket.models.price import PriceBar
from vmarket.models.trade import Trade
from vmarket.repositories import portfolios as port_repo
from vmarket.repositories import prices as price_repo


@dataclass
class ValuePoint:
    date: date
    value: Decimal
    cash: Decimal
    invested: Decimal


@dataclass
class HoldingValuePoint:
    date: date
    symbol: str
    value: Decimal | None
    quantity: Decimal


def portfolio_value_series(session: Session, days: int = 30) -> list[ValuePoint]:
    """
    Reconstruct total portfolio value for each calendar day over the last `days` days.
    Uses trade history + stored price bars; skips days with no price data.
    """
    portfolio = port_repo.get_or_create_default(session)
    end = date.today()
    start = end - timedelta(days=days - 1)

    # Load all trades once, sorted ascending
    all_trades = list(
        session.scalars(
            select(Trade)
            .where(Trade.portfolio_id == portfolio.id)
            .order_by(Trade.trade_date.asc(), Trade.created_at.asc())
        )
    )

    points: list[ValuePoint] = []
    current = start

    while current <= end:
        # Positions as-of this date
        positions: dict[int, Decimal] = {}  # instrument_id → net qty
        cost_basis: dict[int, Decimal] = {}  # instrument_id → total cost (for avg)

        for t in all_trades:
            if t.trade_date > current:
                break
            iid = t.instrument_id
            if t.side == "buy":
                positions[iid] = positions.get(iid, Decimal("0")) + t.quantity
                cost_basis[iid] = cost_basis.get(iid, Decimal("0")) + t.quantity * t.price
            else:
                qty = positions.get(iid, Decimal("0"))
                avg = cost_basis.get(iid, Decimal("0")) / qty if qty > 0 else Decimal("0")
                positions[iid] = qty - t.quantity
                cost_basis[iid] = cost_basis.get(iid, Decimal("0")) - t.quantity * avg

        # Cash as-of this date
        from sqlalchemy import func

        cash_result = session.scalar(
            select(func.sum(CashLedgerEntry.amount)).where(
                CashLedgerEntry.portfolio_id == portfolio.id,
                CashLedgerEntry.date <= current,
            )
        )
        cash = Decimal(str(cash_result)) if cash_result is not None else Decimal("0")

        # Market value of open positions
        invested = Decimal("0")
        for iid, qty in positions.items():
            if qty <= 0:
                continue
            # Find the closest price bar on or before this date
            bar = session.scalar(
                select(PriceBar)
                .where(PriceBar.instrument_id == iid, PriceBar.date <= current)
                .order_by(PriceBar.date.desc())
                .limit(1)
            )
            if bar is not None:
                invested += qty * price_repo.best_price(bar)

        points.append(
            ValuePoint(
                date=current,
                value=cash + invested,
                cash=cash,
                invested=invested,
            )
        )
        current += timedelta(days=1)

    return points


def benchmark_price_series(
    session: Session,
    symbol: str,
    dates: list[date],
) -> list[float | None]:
    """Return a raw closing price for each date in dates, or None where unavailable."""
    from vmarket.repositories import instruments as inst_repo

    instrument = inst_repo.get_by_symbol(session, symbol)
    if instrument is None:
        return [None] * len(dates)

    result: list[float | None] = []
    for d in dates:
        bar = session.scalar(
            select(PriceBar)
            .where(PriceBar.instrument_id == instrument.id, PriceBar.date <= d)
            .order_by(PriceBar.date.desc())
            .limit(1)
        )
        result.append(float(price_repo.best_price(bar)) if bar is not None else None)
    return result


def holding_value_series(session: Session, days: int = 30) -> dict[str, list[HoldingValuePoint]]:
    portfolio = port_repo.get_or_create_default(session)
    end = date.today()
    start = end - timedelta(days=days - 1)

    all_trades = list(
        session.scalars(
            select(Trade)
            .where(Trade.portfolio_id == portfolio.id)
            .order_by(Trade.trade_date.asc(), Trade.created_at.asc())
        )
    )

    instrument_symbols = {
        trade.instrument_id: trade.instrument.symbol
        for trade in all_trades
    }
    series: dict[str, list[HoldingValuePoint]] = {
        symbol: []
        for symbol in instrument_symbols.values()
    }

    current = start
    while current <= end:
        positions: dict[int, Decimal] = {}

        for trade in all_trades:
            if trade.trade_date > current:
                break
            if trade.side == "buy":
                positions[trade.instrument_id] = (
                    positions.get(trade.instrument_id, Decimal("0"))
                    + trade.quantity
                )
            else:
                positions[trade.instrument_id] = (
                    positions.get(trade.instrument_id, Decimal("0"))
                    - trade.quantity
                )

        for instrument_id, symbol in instrument_symbols.items():
            quantity = positions.get(instrument_id, Decimal("0"))
            value: Decimal | None = None
            if quantity > 0:
                bar = session.scalar(
                    select(PriceBar)
                    .where(PriceBar.instrument_id == instrument_id, PriceBar.date <= current)
                    .order_by(PriceBar.date.desc())
                    .limit(1)
                )
                if bar is not None:
                    value = quantity * price_repo.best_price(bar)

            series[symbol].append(
                HoldingValuePoint(
                    date=current,
                    symbol=symbol,
                    value=value,
                    quantity=quantity,
                )
            )
        current += timedelta(days=1)

    return series
