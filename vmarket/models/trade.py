from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vmarket.db import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # buy | sell
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_source: Mapped[str] = mapped_column(String(32), nullable=False, default="latest_close")
    notes: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    portfolio: Mapped["Portfolio"] = relationship(back_populates="trades")  # noqa: F821
    instrument: Mapped["Instrument"] = relationship(back_populates="trades")  # noqa: F821
