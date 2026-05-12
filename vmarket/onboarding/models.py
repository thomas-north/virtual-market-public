from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ImportKind = Literal["portfolio", "watchlist", "screenshot"]
ImportSourceKind = Literal["manual", "csv", "paste", "screenshot", "agent"]
ImportDraftStatus = Literal["pending", "confirmed", "discarded"]


class ImportDraftRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = ""
    name: str | None = None
    quantity: Decimal | None = None
    average_cost: Decimal | None = None
    cost_basis: Decimal | None = None
    current_value: Decimal | None = None
    gain_amount: Decimal | None = None
    gain_percent: Decimal | None = None
    currency: str | None = None
    asset_type: str | None = None
    trade_date: date | None = None
    notes: str | None = None
    current_price: Decimal | None = None
    target_buy_price: Decimal | None = None
    target_sell_price: Decimal | None = None
    warnings: list[str] = Field(default_factory=list)


class ImportDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    kind: ImportKind
    source_kind: ImportSourceKind
    status: ImportDraftStatus
    rows: list[ImportDraftRow] = Field(default_factory=list)
    original_filename: str | None = None
    stored_path: str | None = None
    notes: str | None = None
    row_count: int = 0
    warning_count: int = 0
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None
    discarded_at: datetime | None = None


class OnboardingState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    db_path: str
    user_data_dir: str
    portfolio_ready: bool
    watchlist_ready: bool
    profile_ready: bool
    cash_ready: bool
    pending_imports: int = 0
    suggested_next_steps: list[str] = Field(default_factory=list)
