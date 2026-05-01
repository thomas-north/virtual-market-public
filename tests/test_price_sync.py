from datetime import date
from decimal import Decimal
from unittest.mock import patch

from vmarket.dto.price_bar import PriceBarDTO
from vmarket.services.market_data_service import sync_prices
from vmarket.services.watchlist_service import add_to_watchlist


def _make_bar(symbol: str, d: date, close: float) -> PriceBarDTO:
    return PriceBarDTO(
        symbol=symbol,
        date=d,
        open=None, high=None, low=None,
        close=Decimal(str(close)),
        adjusted_close=Decimal(str(close)),
        volume=None, currency="USD",
        source="stooq",
    )


def test_sync_stores_price_bars(session):
    add_to_watchlist(session, "AAPL.US")
    session.commit()

    bars = [_make_bar("AAPL.US", date(2026, 4, 24), 185.0)]

    with patch(
        "vmarket.services.market_data_service.StooqProvider.fetch_daily_prices",
        return_value=bars,
    ):
        result = sync_prices(session, symbol="AAPL.US", days=7)
        session.commit()

    assert result.fetched == 1
    assert result.updated_bars == 1
    assert result.failed == []


def test_sync_is_idempotent(session):
    add_to_watchlist(session, "AAPL.US")
    session.commit()

    bars = [_make_bar("AAPL.US", date(2026, 4, 24), 185.0)]

    with patch(
        "vmarket.services.market_data_service.StooqProvider.fetch_daily_prices",
        return_value=bars,
    ):
        sync_prices(session, symbol="AAPL.US", days=7)
        session.commit()
        result = sync_prices(session, symbol="AAPL.US", days=7)
        session.commit()

    assert result.fetched == 1
    # second sync still processes 1 bar (upsert)
    assert result.updated_bars == 1


def test_stooq_failure_falls_back_to_alpha_vantage(session):
    from vmarket.errors import ProviderError

    add_to_watchlist(session, "AAPL.US")
    session.commit()

    bars = [_make_bar("AAPL.US", date(2026, 4, 24), 185.0)]

    with (
        patch(
            "vmarket.services.market_data_service.StooqProvider.fetch_daily_prices",
            side_effect=ProviderError("stooq down"),
        ),
        patch(
            "vmarket.services.market_data_service.AlphaVantageProvider.fetch_daily_prices",
            return_value=bars,
        ),
        patch(
            "vmarket.services.market_data_service.get_alpha_vantage_key",
            return_value="test-key",
        ),
    ):
        result = sync_prices(session, symbol="AAPL.US", days=7)
        session.commit()

    assert result.fetched == 1
    assert result.failed == []


def test_stooq_failure_falls_back_to_yahoo_without_av_key(session):
    from vmarket.errors import ProviderError
    from vmarket.repositories import instruments as inst_repo
    from vmarket.repositories import prices as price_repo

    add_to_watchlist(session, "AAPL.US")
    session.commit()

    bars = [
        PriceBarDTO(
            symbol="AAPL",
            date=date(2026, 4, 24),
            open=None,
            high=None,
            low=None,
            close=Decimal("185"),
            adjusted_close=Decimal("185"),
            volume=None,
            currency=None,
            source="yahoo_finance",
        )
    ]

    with (
        patch(
            "vmarket.services.market_data_service.StooqProvider.fetch_daily_prices",
            side_effect=ProviderError("stooq down"),
        ),
        patch(
            "vmarket.services.market_data_service.YahooFinanceProvider.fetch_daily_prices",
            return_value=bars,
        ),
        patch("vmarket.services.market_data_service.get_alpha_vantage_key", return_value=None),
    ):
        result = sync_prices(session, symbol="AAPL.US", days=7)
        session.commit()

    instrument = inst_repo.get_by_symbol(session, "AAPL.US")
    latest = price_repo.get_latest(session, instrument.id)

    assert result.fetched == 1
    assert result.failed == []
    assert latest.currency == "USD"
