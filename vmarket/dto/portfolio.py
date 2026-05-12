from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass
class PositionDTO:
    symbol: str
    name: str | None
    quantity: Decimal
    avg_cost: Decimal
    cost_currency: str
    latest_price: Decimal | None
    latest_price_date: date | None
    latest_price_currency: str | None
    market_value: Decimal | None
    unrealised_pnl: Decimal | None
    unrealised_pnl_pct: Decimal | None
    value_in_base: Decimal | None
    asset_type: str | None = None
    price_status: str = "missing"
    price_status_note: str = ""
    fx_status: str = "not_needed"
    stale: bool = False
    fx_missing: bool = False
    fx_stale: bool = False
