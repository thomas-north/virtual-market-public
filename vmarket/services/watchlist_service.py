from decimal import Decimal

from sqlalchemy.orm import Session

from vmarket.models.watchlist import WatchlistItem
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import watchlist as wl_repo


def add_to_watchlist(
    session: Session,
    symbol: str,
    name: str | None = None,
    currency: str | None = None,
    asset_type: str | None = None,
) -> WatchlistItem:
    instrument = inst_repo.get_or_create(
        session,
        symbol=symbol,
        provider_symbol=symbol,
        name=name,
        currency=currency,
        asset_type=asset_type,
    )
    existing = wl_repo.get_by_instrument_id(session, instrument.id)
    if existing:
        return existing
    item = WatchlistItem(instrument_id=instrument.id)
    return wl_repo.add(session, item)


def remove_from_watchlist(session: Session, symbol: str) -> bool:
    instrument = inst_repo.get_by_symbol(session, symbol)
    if instrument is None:
        return False
    item = wl_repo.get_by_instrument_id(session, instrument.id)
    if item is None:
        return False
    wl_repo.remove(session, item)
    return True


def set_targets(
    session: Session,
    symbol: str,
    buy_below: Decimal | None,
    sell_above: Decimal | None,
) -> WatchlistItem | None:
    instrument = inst_repo.get_by_symbol(session, symbol)
    if instrument is None:
        return None
    item = wl_repo.get_by_instrument_id(session, instrument.id)
    if item is None:
        return None
    if buy_below is not None:
        item.target_buy_price = buy_below
    if sell_above is not None:
        item.target_sell_price = sell_above
    session.flush()
    return item


def list_watchlist(session: Session) -> list[WatchlistItem]:
    return wl_repo.list_all(session)
