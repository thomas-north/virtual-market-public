from dataclasses import dataclass
from decimal import Decimal
from datetime import date


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
    stale: bool = False
    fx_missing: bool = False
