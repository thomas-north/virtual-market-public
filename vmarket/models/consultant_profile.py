from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from vmarket.db import Base


class ConsultantProfileRecord(Base):
    __tablename__ = "consultant_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_name: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, default="default"
    )
    risk_score: Mapped[int | None] = mapped_column(Integer)
    exclusions_json: Mapped[str] = mapped_column(Text, default="[]")
    product_preferences_json: Mapped[str] = mapped_column(Text, default="[]")
    preference_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    account_wrappers_json: Mapped[str] = mapped_column(Text, default="[]")
    investment_horizon: Mapped[str | None] = mapped_column(String(32))
    amount: Mapped[str | None] = mapped_column(String(64))
    monthly_amount: Mapped[str | None] = mapped_column(String(64))
    income_preference: Mapped[str | None] = mapped_column(String(32))
    distribution_preference: Mapped[str | None] = mapped_column(String(32))
    country_jurisdiction: Mapped[str | None] = mapped_column(String(32))
    base_currency: Mapped[str | None] = mapped_column(String(8))
    prefers_uk_listed: Mapped[bool] = mapped_column(Boolean, default=True)
    prefers_gbp_lines: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
