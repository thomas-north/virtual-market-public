from datetime import date
from decimal import Decimal

from vmarket.dto.price_bar import PriceBarDTO
from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import prices as price_repo
from vmarket.services.cash_service import deposit
from vmarket.services.trade_service import buy, sell
from vmarket.services.valuation_service import compute_positions
from vmarket.services.watchlist_service import add_to_watchlist


def _setup(session, cash=10000.0, price=100.0):
    deposit(session, Decimal(str(cash)), "USD")
    add_to_watchlist(session, "TEST.US", currency="USD")
    session.commit()
    inst = inst_repo.get_by_symbol(session, "TEST.US")
    bars = [PriceBarDTO(
        symbol="TEST.US", date=date.today(),
        open=None, high=None, low=None,
        close=Decimal(str(price)), adjusted_close=Decimal(str(price)),
        volume=None, currency="USD", source="stooq",
    )]
    price_repo.upsert_price_bars(session, inst.id, bars)
    session.commit()


def test_position_computed_from_trades(session):
    _setup(session, price=100.0)
    buy(session, "TEST.US", Decimal("10"))
    session.commit()
    positions = compute_positions(session)
    assert len(positions) == 1
    assert positions[0].quantity == Decimal("10")


def test_avg_cost_correct(session):
    _setup(session, price=100.0)
    buy(session, "TEST.US", Decimal("10"), price=Decimal("100"), currency="USD")
    session.commit()
    positions = compute_positions(session)
    assert positions[0].avg_cost == Decimal("100")


def test_unrealised_pnl(session):
    _setup(session, price=120.0)
    buy(session, "TEST.US", Decimal("10"), price=Decimal("100"), currency="USD")
    session.commit()
    # Update price to 120
    inst = inst_repo.get_by_symbol(session, "TEST.US")
    bars = [PriceBarDTO(
        symbol="TEST.US", date=date.today(),
        open=None, high=None, low=None,
        close=Decimal("120"), adjusted_close=Decimal("120"),
        volume=None, currency="USD", source="stooq",
    )]
    price_repo.upsert_price_bars(session, inst.id, bars)
    session.commit()
    positions = compute_positions(session)
    assert positions[0].unrealised_pnl == Decimal("200")


def test_zero_quantity_position_excluded(session):
    _setup(session, price=100.0)
    buy(session, "TEST.US", Decimal("5"))
    session.commit()
    sell(session, "TEST.US", Decimal("5"))
    session.commit()
    positions = compute_positions(session)
    assert positions == []


def test_gbp_cost_position_converts_usd_market_value_for_pnl(session):
    deposit(session, Decimal("1000"), "GBP")
    add_to_watchlist(session, "AAPL.US", currency="GBP")
    session.commit()

    buy(session, "AAPL.US", Decimal("10"), price=Decimal("10"), currency="GBP")
    session.commit()

    inst = inst_repo.get_by_symbol(session, "AAPL.US")
    bars = [
        PriceBarDTO(
            symbol="AAPL.US",
            date=date.today(),
            open=None,
            high=None,
            low=None,
            close=Decimal("20"),
            adjusted_close=Decimal("20"),
            volume=None,
            currency="USD",
            source="stooq",
        )
    ]
    price_repo.upsert_price_bars(session, inst.id, bars)
    fx_repo.upsert_fx_rate(
        session,
        fx_date=date.today(),
        base="GBP",
        quote="USD",
        rate=Decimal("2"),
        source="test",
    )
    session.commit()

    positions = compute_positions(session, base_currency="GBP")

    assert positions[0].market_value == Decimal("100")
    assert positions[0].value_in_base == Decimal("100")
    assert positions[0].unrealised_pnl == Decimal("0")
    assert positions[0].fx_missing is False
