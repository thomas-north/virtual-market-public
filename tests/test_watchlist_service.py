from decimal import Decimal

from vmarket.services.watchlist_service import (
    add_to_watchlist,
    remove_from_watchlist,
    list_watchlist,
    set_targets,
)


def test_add_to_watchlist(session):
    add_to_watchlist(session, "AAPL.US", name="Apple Inc", currency="USD", asset_type="stock")
    session.commit()
    items = list_watchlist(session)
    assert len(items) == 1
    assert items[0].instrument.symbol == "AAPL.US"


def test_add_same_symbol_twice_is_idempotent(session):
    add_to_watchlist(session, "AAPL.US")
    add_to_watchlist(session, "AAPL.US")
    session.commit()
    items = list_watchlist(session)
    assert len(items) == 1


def test_remove_from_watchlist(session):
    add_to_watchlist(session, "AAPL.US")
    session.commit()
    removed = remove_from_watchlist(session, "AAPL.US")
    session.commit()
    assert removed is True
    assert list_watchlist(session) == []


def test_remove_unknown_symbol_returns_false(session):
    assert remove_from_watchlist(session, "UNKNOWN.XX") is False


def test_set_targets(session):
    add_to_watchlist(session, "AAPL.US")
    session.commit()
    item = set_targets(session, "AAPL.US", buy_below=Decimal("150"), sell_above=Decimal("200"))
    session.commit()
    assert item is not None
    assert item.target_buy_price == Decimal("150")
    assert item.target_sell_price == Decimal("200")
