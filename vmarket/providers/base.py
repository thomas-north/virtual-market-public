from datetime import date
from typing import Protocol

from vmarket.dto.price_bar import PriceBarDTO


class MarketDataProvider(Protocol):
    name: str

    def fetch_daily_prices(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> list[PriceBarDTO]:
        ...
