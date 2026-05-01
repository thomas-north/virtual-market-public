from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from vmarket.dto.portfolio import PositionDTO
from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.repositories import prices as price_repo
from vmarket.repositories import trades as trade_repo

STALE_DAYS = 5


def _infer_price_currency(symbol: str) -> str | None:
    symbol = symbol.upper()
    if symbol.endswith(".US"):
        return "USD"
    if symbol.endswith(".L"):
        return "GBP"
    if len(symbol) == 7 and symbol.isalnum():
        return "GBP"
    return None


def _latest_fx_rate(session: Session, from_currency: str, to_currency: str) -> Decimal | None:
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    if from_currency == to_currency:
        return Decimal("1")

    direct = fx_repo.get_latest_rate(session, from_currency, to_currency)
    if direct:
        return direct[1]

    inverse = fx_repo.get_latest_rate(session, to_currency, from_currency)
    if inverse and inverse[1] != 0:
        return Decimal("1") / inverse[1]

    return None


def _convert(
    session: Session,
    amount: Decimal,
    from_currency: str,
    to_currency: str,
) -> Decimal | None:
    rate = _latest_fx_rate(session, from_currency, to_currency)
    return amount * rate if rate is not None else None


def compute_positions(session: Session, base_currency: str | None = None) -> list[PositionDTO]:
    portfolio = port_repo.get_or_create_default(session)
    base_currency = (base_currency or portfolio.base_currency).upper()

    all_trades = trade_repo.list_trades(session, portfolio.id)
    by_instrument: dict[int, list] = {}
    for t in all_trades:
        by_instrument.setdefault(t.instrument_id, []).append(t)

    positions: list[PositionDTO] = []
    today = date.today()

    for instrument_id, trades in by_instrument.items():
        qty = Decimal("0")
        cost_total = Decimal("0")
        currency = trades[0].currency.upper()

        for t in trades:
            if t.side == "buy":
                qty += t.quantity
                cost_total += t.quantity * t.price
            else:
                avg = cost_total / qty if qty > 0 else Decimal("0")
                cost_total -= t.quantity * avg
                qty -= t.quantity

        if qty <= 0:
            continue

        avg_cost = cost_total / qty

        instrument = inst_repo.get_by_symbol(session, trades[0].instrument.symbol)
        latest_bar = price_repo.get_latest(session, instrument_id)
        latest_price: Decimal | None = None
        latest_date: date | None = None
        latest_currency: str | None = None
        stale = False

        if latest_bar:
            latest_price = price_repo.best_price(latest_bar)
            latest_date = latest_bar.date
            latest_currency = (
                latest_bar.currency
                or _infer_price_currency(instrument.symbol)
                or instrument.currency
                or currency
            ).upper()
            stale = (today - latest_date).days > STALE_DAYS

        market_value: Decimal | None = None
        unrealised_pnl: Decimal | None = None
        unrealised_pnl_pct: Decimal | None = None
        value_in_base: Decimal | None = None
        fx_missing = False

        if latest_price is not None:
            native_market_value = qty * latest_price

            if latest_currency == currency:
                market_value = native_market_value
            else:
                converted = _convert(session, native_market_value, latest_currency, currency)
                if converted is not None:
                    market_value = converted
                else:
                    fx_missing = True

            if market_value is not None and not fx_missing:
                unrealised_pnl = market_value - cost_total
                unrealised_pnl_pct = (unrealised_pnl / cost_total * 100) if cost_total else None

            if market_value is not None and currency == base_currency:
                value_in_base = market_value
            elif market_value is not None and not fx_missing:
                value_in_base = _convert(session, market_value, currency, base_currency)
                if value_in_base is None:
                    fx_missing = True
            else:
                value_in_base = _convert(
                    session,
                    native_market_value,
                    latest_currency,
                    base_currency,
                )
                if value_in_base is None:
                    fx_missing = True

        positions.append(
            PositionDTO(
                symbol=instrument.symbol,
                name=instrument.name,
                quantity=qty,
                avg_cost=avg_cost,
                cost_currency=currency,
                latest_price=latest_price,
                latest_price_date=latest_date,
                latest_price_currency=latest_currency,
                market_value=market_value,
                unrealised_pnl=unrealised_pnl,
                unrealised_pnl_pct=unrealised_pnl_pct,
                value_in_base=value_in_base,
                stale=stale,
                fx_missing=fx_missing,
            )
        )

    return positions
