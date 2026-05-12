from datetime import date, timedelta
from decimal import Decimal

from vmarket.dto.price_bar import PriceBarDTO
from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import prices as price_repo
from vmarket.services.market_data_service import sync_prices
from vmarket.services.valuation_service import compute_positions
from vmarket.services.watchlist_service import add_to_watchlist


def test_manual_price_symbols_are_not_counted_as_sync_failures(session):
    add_to_watchlist(session, "BD6PG78", currency="GBP", asset_type="fund")
    session.commit()

    result = sync_prices(session, symbol="BD6PG78", days=7)

    assert result.failed == []
    assert result.manual_priced == ["BD6PG78"]


def test_compute_positions_marks_manual_price_holdings(session):
    from vmarket.services.cash_service import deposit
    from vmarket.services.trade_service import buy

    deposit(session, Decimal("1000"), "GBP")
    add_to_watchlist(session, "BD6PG78", currency="GBP", asset_type="fund")
    session.commit()

    buy(session, "BD6PG78", Decimal("10"), price=Decimal("5"), currency="GBP")
    session.commit()

    positions = compute_positions(session)

    assert positions[0].price_status == "manual"
    assert positions[0].latest_price is None


def test_compute_positions_marks_stale_fx(session):
    from vmarket.services.cash_service import deposit
    from vmarket.services.trade_service import buy

    deposit(session, Decimal("1000"), "GBP")
    add_to_watchlist(session, "AAPL.US", currency="GBP")
    session.commit()

    buy(session, "AAPL.US", Decimal("10"), price=Decimal("10"), currency="GBP")
    session.commit()

    instrument = inst_repo.get_by_symbol(session, "AAPL.US")
    price_repo.upsert_price_bars(
        session,
        instrument.id,
        [
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
        ],
    )
    fx_repo.upsert_fx_rate(
        session,
        fx_date=date.today() - timedelta(days=10),
        base="GBP",
        quote="USD",
        rate=Decimal("2"),
        source="test",
    )
    session.commit()

    positions = compute_positions(session, base_currency="GBP")

    assert positions[0].fx_stale is True
    assert positions[0].fx_status == "stale"
