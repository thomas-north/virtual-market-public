from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from vmarket.dto.portfolio import PositionDTO
from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.repositories import prices as price_repo
from vmarket.repositories import trades as trade_repo
from vmarket.services.freshness import (
    STALE_PRICE_DAYS,
    FxState,
    PriceState,
    combine_fx_states,
    fx_state_for,
    price_status_for,
)

STALE_DAYS = STALE_PRICE_DAYS

_APPROXIMATE_IMPORT_NOTE = "Approximate value-snapshot import"


def _infer_price_currency(symbol: str) -> str | None:
    symbol = symbol.upper()
    if symbol.endswith(".US"):
        return "USD"
    if symbol.endswith(".L"):
        return "GBP"
    if len(symbol) == 7 and symbol.isalnum():
        return "GBP"
    return None


def _latest_fx_rate_info(
    session: Session,
    from_currency: str,
    to_currency: str,
) -> tuple[date | None, Decimal | None]:
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    if from_currency == to_currency:
        return (date.today(), Decimal("1"))

    direct = fx_repo.get_latest_rate(session, from_currency, to_currency)
    if direct:
        return direct

    inverse = fx_repo.get_latest_rate(session, to_currency, from_currency)
    if inverse and inverse[1] != 0:
        return (inverse[0], Decimal("1") / inverse[1])

    return (None, None)


def _convert(
    session: Session,
    amount: Decimal,
    from_currency: str,
    to_currency: str,
) -> tuple[Decimal | None, FxState]:
    same_currency = from_currency.upper() == to_currency.upper()
    rate_date, rate = _latest_fx_rate_info(session, from_currency, to_currency)
    state = fx_state_for(rate_date, same_currency=same_currency)
    return (amount * rate if rate is not None else None, state)


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
        provenance_kinds: list[str] = []
        provenance_confidences: list[float] = []
        provenance_notes: list[str] = []

        for t in trades:
            provenance_kind = (t.provenance_kind or "").strip().lower()
            if not provenance_kind:
                provenance_kind = (
                    "approximate_snapshot"
                    if t.notes and _APPROXIMATE_IMPORT_NOTE in t.notes
                    else "exact"
                )
            provenance_kinds.append(provenance_kind)
            if t.provenance_confidence is not None:
                provenance_confidences.append(float(t.provenance_confidence))
            else:
                provenance_confidences.append(
                    0.5 if provenance_kind == "approximate_snapshot" else 1.0
                )
            if t.provenance_note:
                provenance_notes.append(t.provenance_note)
            elif provenance_kind == "approximate_snapshot" and t.notes:
                provenance_notes.append(_APPROXIMATE_IMPORT_NOTE)

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
        price_status = price_status_for(instrument.symbol, None, as_of=today)

        if latest_bar:
            latest_price = price_repo.best_price(latest_bar)
            latest_date = latest_bar.date
            latest_currency = (
                latest_bar.currency
                or _infer_price_currency(instrument.symbol)
                or instrument.currency
                or currency
            ).upper()
            price_status = price_status_for(instrument.symbol, latest_date, as_of=today)

        market_value: Decimal | None = None
        unrealised_pnl: Decimal | None = None
        unrealised_pnl_pct: Decimal | None = None
        value_in_base: Decimal | None = None
        fx_missing = False
        fx_stale = False
        fx_status = FxState.NOT_NEEDED

        if latest_price is not None:
            native_market_value = qty * latest_price

            if latest_currency == currency:
                market_value = native_market_value
            else:
                converted, market_fx_state = _convert(
                    session,
                    native_market_value,
                    latest_currency,
                    currency,
                )
                fx_status = combine_fx_states(fx_status, market_fx_state)
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
                value_in_base, base_fx_state = _convert(
                    session,
                    market_value,
                    currency,
                    base_currency,
                )
                fx_status = combine_fx_states(fx_status, base_fx_state)
                if value_in_base is None:
                    fx_missing = True
            else:
                value_in_base, base_fx_state = _convert(
                    session,
                    native_market_value,
                    latest_currency,
                    base_currency,
                )
                fx_status = combine_fx_states(fx_status, base_fx_state)
                if value_in_base is None:
                    fx_missing = True

        fx_stale = fx_status == FxState.STALE
        fx_missing = fx_missing or fx_status == FxState.MISSING

        if provenance_kinds and all(kind == "exact" for kind in provenance_kinds):
            holding_provenance_kind = "exact"
            provenance_confidence = 1.0
        elif provenance_kinds and all(kind == "approximate_snapshot" for kind in provenance_kinds):
            holding_provenance_kind = "approximate_snapshot"
            provenance_confidence = min(provenance_confidences) if provenance_confidences else 0.5
        elif provenance_kinds:
            holding_provenance_kind = "mixed"
            provenance_confidence = min(provenance_confidences) if provenance_confidences else 0.75
        else:
            holding_provenance_kind = "exact"
            provenance_confidence = 1.0

        if holding_provenance_kind == "approximate_snapshot":
            provenance_note = _APPROXIMATE_IMPORT_NOTE
        elif holding_provenance_kind == "mixed":
            provenance_note = "Mixed trade provenance"
        else:
            provenance_note = "Exact unit-based position"
        if provenance_notes and holding_provenance_kind != "exact":
            provenance_note = provenance_notes[0]

        positions.append(
            PositionDTO(
                symbol=instrument.symbol,
                name=instrument.name,
                asset_type=instrument.asset_type,
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
                price_status=price_status.state.value,
                price_status_note=price_status.note,
                fx_status=fx_status.value,
                provenance_kind=holding_provenance_kind,
                provenance_confidence=provenance_confidence,
                provenance_note=provenance_note,
                stale=price_status.state == PriceState.STALE,
                fx_missing=fx_missing,
                fx_stale=fx_stale,
            )
        )

    return positions
