from decimal import Decimal

from sqlalchemy.orm import Session

from vmarket.models.watchlist import WatchlistItem
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import prices as price_repo
from vmarket.repositories import watchlist as wl_repo
from vmarket.services.freshness import is_manual_price_symbol, price_status_for


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


def build_watchlist_rows(
    session: Session,
    held_symbols: set[str] | None = None,
) -> list[dict]:
    """Return enriched watchlist rows suitable for cockpit display."""
    if held_symbols is None:
        held_symbols = set()

    rows: list[dict] = []
    for item in wl_repo.list_all(session):
        symbol = item.instrument.symbol
        latest_bar = price_repo.get_latest(session, item.instrument_id)
        latest_price = price_repo.best_price(latest_bar) if latest_bar else None
        status = price_status_for(symbol, latest_bar.date if latest_bar else None)

        buy_target = item.target_buy_price
        sell_target = item.target_sell_price

        dist_buy_pct: float | None = None
        dist_sell_pct: float | None = None

        if latest_price is not None and buy_target is not None and buy_target > 0:
            dist_buy_pct = float((latest_price - buy_target) / buy_target * 100)
        if latest_price is not None and sell_target is not None and sell_target > 0:
            dist_sell_pct = float((latest_price - sell_target) / sell_target * 100)

        flag = ""
        flag_tone = "neutral"
        priority = 4

        if latest_price is not None and buy_target is not None and latest_price <= buy_target:
            flag = "buy target hit"
            flag_tone = "positive"
            priority = 0
        elif latest_price is not None and sell_target is not None and latest_price >= sell_target:
            flag = "sell target hit"
            flag_tone = "warning"
            priority = 0
        elif dist_buy_pct is not None and 0 < dist_buy_pct <= 5:
            flag = "near buy target"
            flag_tone = "warning"
            priority = 1
        elif dist_sell_pct is not None and -5 <= dist_sell_pct < 0:
            flag = "near sell target"
            flag_tone = "warning"
            priority = 1
        elif symbol in held_symbols:
            flag = "currently held"
            flag_tone = "neutral"
            priority = 2
        elif status.state.value == "manual" or is_manual_price_symbol(symbol):
            flag = "manual price"
            flag_tone = "neutral"
            priority = 3

        rows.append(
            {
                "id": item.id,
                "symbol": symbol,
                "name": item.instrument.name or "",
                "currency": item.instrument.currency or "GBP",
                "latest_price": latest_price,
                "target_buy_price": buy_target,
                "target_sell_price": sell_target,
                "dist_buy_pct": dist_buy_pct,
                "dist_sell_pct": dist_sell_pct,
                "flag": flag,
                "flag_tone": flag_tone,
                "priority": priority,
                "status_note": status.note,
            }
        )

    rows.sort(key=lambda r: (r["priority"], r["symbol"]))
    return rows
