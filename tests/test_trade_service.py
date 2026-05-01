from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from vmarket.dto.price_bar import PriceBarDTO
from vmarket.errors import InsufficientCashError, InsufficientHoldingsError, NoPriceError
from vmarket.services.cash_service import deposit
from vmarket.services.trade_service import buy, sell
from vmarket.services.watchlist_service import add_to_watchlist
from vmarket.repositories import prices as price_repo
from vmarket.repositories import instruments as inst_repo


def _seed(session, cash: float = 10000.0):
    deposit(session, Decimal(str(cash)), "USD")
    add_to_watchlist(session, "AAPL.US", currency="USD")
    session.commit()


def _mock_price(session, symbol: str, close: float):
    inst = inst_repo.get_by_symbol(session, symbol)
    from vmarket.dto.price_bar import PriceBarDTO
    bars = [PriceBarDTO(
        symbol=symbol, date=date.today(),
        open=None, high=None, low=None,
        close=Decimal(str(close)), adjusted_close=Decimal(str(close)),
        volume=None, currency="USD", source="stooq",
    )]
    price_repo.upsert_price_bars(session, inst.id, bars)
    session.commit()


def test_buy_succeeds(session):
    _seed(session)
    _mock_price(session, "AAPL.US", 185.0)
    trade = buy(session, "AAPL.US", Decimal("5"))
    session.commit()
    assert trade.side == "buy"
    assert trade.quantity == Decimal("5")


def test_buy_deducts_cash(session):
    from vmarket.services.cash_service import get_all_balances
    _seed(session, 10000)
    _mock_price(session, "AAPL.US", 200.0)
    buy(session, "AAPL.US", Decimal("10"))
    session.commit()
    balances = get_all_balances(session)
    assert balances["USD"] == Decimal("8000")


def test_buy_fails_insufficient_cash(session):
    _seed(session, 100)
    _mock_price(session, "AAPL.US", 200.0)
    with pytest.raises(InsufficientCashError):
        buy(session, "AAPL.US", Decimal("10"))


def test_buy_fails_no_price(session):
    _seed(session)
    with pytest.raises(NoPriceError):
        buy(session, "AAPL.US", Decimal("5"))


def test_sell_succeeds(session):
    _seed(session)
    _mock_price(session, "AAPL.US", 185.0)
    buy(session, "AAPL.US", Decimal("5"))
    session.commit()
    trade = sell(session, "AAPL.US", Decimal("3"))
    session.commit()
    assert trade.side == "sell"
    assert trade.quantity == Decimal("3")


def test_cannot_oversell(session):
    _seed(session)
    _mock_price(session, "AAPL.US", 185.0)
    buy(session, "AAPL.US", Decimal("5"))
    session.commit()
    with pytest.raises(InsufficientHoldingsError):
        sell(session, "AAPL.US", Decimal("10"))
