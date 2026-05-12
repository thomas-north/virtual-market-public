from sqlalchemy import select
from sqlalchemy.orm import Session

from vmarket.models.instrument import Instrument


def get_by_symbol(session: Session, symbol: str) -> Instrument | None:
    return session.scalar(select(Instrument).where(Instrument.symbol == symbol))


def get_or_create(
    session: Session,
    symbol: str,
    provider_symbol: str,
    provider: str = "stooq",
    name: str | None = None,
    asset_type: str | None = None,
    exchange: str | None = None,
    currency: str | None = None,
) -> Instrument:
    inst = get_by_symbol(session, symbol)
    if inst is None:
        inst = Instrument(
            symbol=symbol,
            provider_symbol=provider_symbol,
            provider=provider,
            name=name,
            asset_type=asset_type,
            exchange=exchange,
            currency=currency,
        )
        session.add(inst)
        session.flush()
    else:
        if name is not None:
            inst.name = name
        if currency is not None:
            inst.currency = currency
        if asset_type is not None:
            inst.asset_type = asset_type
        session.flush()
    return inst


def list_all_active(session: Session) -> list[Instrument]:
    return list(session.scalars(select(Instrument).where(Instrument.active == True)))  # noqa: E712
