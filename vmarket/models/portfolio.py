from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vmarket.db import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="GBP")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    trades: Mapped[list["Trade"]] = relationship(back_populates="portfolio")  # noqa: F821
    cash_entries: Mapped[list["CashLedgerEntry"]] = relationship(back_populates="portfolio")  # noqa: F821
