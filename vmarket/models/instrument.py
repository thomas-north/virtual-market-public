from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vmarket.db import Base


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    provider_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="stooq")
    name: Mapped[str | None] = mapped_column(String(256))
    asset_type: Mapped[str | None] = mapped_column(String(32))
    exchange: Mapped[str | None] = mapped_column(String(32))
    currency: Mapped[str | None] = mapped_column(String(8))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    price_bars: Mapped[list["PriceBar"]] = relationship(  # noqa: F821
        back_populates="instrument",
        cascade="all, delete-orphan",
    )
    trades: Mapped[list["Trade"]] = relationship(back_populates="instrument")  # noqa: F821
    watchlist_item: Mapped["WatchlistItem | None"] = relationship(  # noqa: F821
        back_populates="instrument",
        uselist=False,
    )
