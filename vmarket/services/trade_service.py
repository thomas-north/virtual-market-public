from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from vmarket.errors import InsufficientCashError, InsufficientHoldingsError, NoPriceError
from vmarket.models.cash_ledger import CashLedgerEntry
from vmarket.models.trade import Trade
from vmarket.repositories import cash as cash_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.repositories import prices as price_repo
from vmarket.repositories import trades as trade_repo


def _compute_quantity(session: Session, portfolio_id: int, instrument_id: int) -> Decimal:
    trades = trade_repo.list_trades_for_instrument(session, portfolio_id, instrument_id)
    qty = Decimal("0")
    for t in trades:
        if t.side == "buy":
            qty += t.quantity
        else:
            qty -= t.quantity
    return qty


def buy(
    session: Session,
    symbol: str,
    quantity: Decimal,
    price: Decimal | None = None,
    currency: str | None = None,
    on_date: date | None = None,
    notes: str | None = None,
    provenance_kind: str | None = None,
    provenance_confidence: Decimal | None = None,
    provenance_note: str | None = None,
) -> Trade:
    portfolio = port_repo.get_or_create_default(session)
    instrument = inst_repo.get_by_symbol(session, symbol)
    if instrument is None:
        raise NoPriceError(
            f"Instrument {symbol} not found. Add it to the watchlist first: "
            f"vmarket watch add {symbol}"
        )

    trade_date = on_date or date.today()
    price_source = "manual" if price is not None else "latest_close"

    if price is None:
        bar = price_repo.get_latest(session, instrument.id)
        if bar is None:
            raise NoPriceError(
                f"No latest price found for {symbol}. Run: vmarket sync prices --symbol {symbol}"
            )
        price = price_repo.best_price(bar)
        currency = currency or bar.currency or instrument.currency or "GBP"
    else:
        currency = currency or instrument.currency or "GBP"

    currency = currency.upper()
    cost = quantity * price

    balance = cash_repo.get_balance(session, portfolio.id, currency)
    if balance < cost:
        raise InsufficientCashError(
            f"Insufficient fake cash. Required: {cost:.2f} {currency}. "
            f"Available: {balance:.2f} {currency}."
        )

    trade = Trade(
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        side="buy",
        quantity=quantity,
        price=price,
        currency=currency,
        trade_date=trade_date,
        price_source=price_source,
        provenance_kind=provenance_kind,
        provenance_confidence=provenance_confidence,
        provenance_note=provenance_note,
        notes=notes,
    )
    trade_repo.add_trade(session, trade)

    cash_entry = CashLedgerEntry(
        portfolio_id=portfolio.id,
        date=trade_date,
        currency=currency,
        amount=-cost,
        type="trade_buy",
        notes=f"Buy {quantity} {symbol} @ {price}",
    )
    cash_repo.add_entry(session, cash_entry)

    return trade


def sell(
    session: Session,
    symbol: str,
    quantity: Decimal,
    price: Decimal | None = None,
    currency: str | None = None,
    on_date: date | None = None,
    notes: str | None = None,
    provenance_kind: str | None = None,
    provenance_confidence: Decimal | None = None,
    provenance_note: str | None = None,
) -> Trade:
    portfolio = port_repo.get_or_create_default(session)
    instrument = inst_repo.get_by_symbol(session, symbol)
    if instrument is None:
        raise NoPriceError(
            f"Instrument {symbol} not found. Add it to the watchlist first."
        )

    current_qty = _compute_quantity(session, portfolio.id, instrument.id)
    if current_qty < quantity:
        raise InsufficientHoldingsError(
            f"Cannot sell {quantity} shares of {symbol}. Current holding: {current_qty}."
        )

    trade_date = on_date or date.today()
    price_source = "manual" if price is not None else "latest_close"

    if price is None:
        bar = price_repo.get_latest(session, instrument.id)
        if bar is None:
            raise NoPriceError(
                f"No latest price found for {symbol}. Run: vmarket sync prices --symbol {symbol}"
            )
        price = price_repo.best_price(bar)
        currency = currency or bar.currency or instrument.currency or "GBP"
    else:
        currency = currency or instrument.currency or "GBP"

    currency = currency.upper()
    proceeds = quantity * price

    trade = Trade(
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        side="sell",
        quantity=quantity,
        price=price,
        currency=currency,
        trade_date=trade_date,
        price_source=price_source,
        provenance_kind=provenance_kind,
        provenance_confidence=provenance_confidence,
        provenance_note=provenance_note,
        notes=notes,
    )
    trade_repo.add_trade(session, trade)

    cash_entry = CashLedgerEntry(
        portfolio_id=portfolio.id,
        date=trade_date,
        currency=currency,
        amount=proceeds,
        type="trade_sell",
        notes=f"Sell {quantity} {symbol} @ {price}",
    )
    cash_repo.add_entry(session, cash_entry)

    return trade
