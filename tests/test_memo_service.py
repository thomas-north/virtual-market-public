from datetime import date
from decimal import Decimal

from vmarket.services.cash_service import deposit
from vmarket.services.memo_service import generate_daily_memo
from vmarket.services.watchlist_service import add_to_watchlist
from vmarket.services.trade_service import buy
from vmarket.repositories import prices as price_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.dto.price_bar import PriceBarDTO


def test_memo_contains_portfolio_summary(session):
    deposit(session, Decimal("5000"), "GBP")
    session.commit()
    memo = generate_daily_memo(session)
    assert "Portfolio Summary" in memo
    assert "5,000.00" in memo


def test_memo_contains_holdings(session):
    deposit(session, Decimal("10000"), "USD")
    add_to_watchlist(session, "AAPL.US", currency="USD")
    session.commit()
    inst = inst_repo.get_by_symbol(session, "AAPL.US")
    price_repo.upsert_price_bars(session, inst.id, [
        PriceBarDTO("AAPL.US", date.today(), None, None, None,
                    Decimal("185"), Decimal("185"), None, "USD", "stooq")
    ])
    session.commit()
    buy(session, "AAPL.US", Decimal("5"))
    session.commit()
    memo = generate_daily_memo(session)
    assert "AAPL.US" in memo
    assert "Portfolio Holdings" in memo


def test_memo_data_quality_section(session):
    deposit(session, Decimal("1000"), "GBP")
    session.commit()
    memo = generate_daily_memo(session)
    assert "Data Quality" in memo


def test_memo_empty_portfolio(session):
    memo = generate_daily_memo(session)
    assert "No open positions" in memo
