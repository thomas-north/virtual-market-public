from sqlalchemy import select
from sqlalchemy.orm import Session

from vmarket.models.watchlist import WatchlistItem


def get_by_instrument_id(session: Session, instrument_id: int) -> WatchlistItem | None:
    return session.scalar(
        select(WatchlistItem).where(WatchlistItem.instrument_id == instrument_id)
    )


def add(session: Session, item: WatchlistItem) -> WatchlistItem:
    session.add(item)
    session.flush()
    return item


def remove(session: Session, item: WatchlistItem) -> None:
    session.delete(item)
    session.flush()


def list_all(session: Session) -> list[WatchlistItem]:
    return list(session.scalars(select(WatchlistItem)))
