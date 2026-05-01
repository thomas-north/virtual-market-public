import time
from datetime import date
from decimal import Decimal

import requests

from vmarket.dto.price_bar import PriceBarDTO
from vmarket.errors import ProviderError

_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageProvider:
    name = "alpha_vantage"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def fetch_daily_prices(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> list[PriceBarDTO]:
        bars: list[PriceBarDTO] = []
        for symbol in symbols:
            bars.extend(self._fetch_symbol(symbol, start_date, end_date))
        return bars

    def _fetch_symbol(self, symbol: str, start_date: date, end_date: date) -> list[PriceBarDTO]:
        time.sleep(1.2)  # free tier: max 1 req/sec, 25 req/day
        # Alpha Vantage uses bare tickers (e.g. "AVGO", not "AVGO.US")
        av_symbol = symbol.split(".")[0].upper()
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": av_symbol,
            "outputsize": "full" if (end_date - start_date).days > 90 else "compact",
            "apikey": self._api_key,
        }
        try:
            resp = requests.get(_BASE_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise ProviderError(f"Alpha Vantage request failed for {symbol}: {exc}") from exc

        if "Error Message" in data:
            raise ProviderError(f"Alpha Vantage error for {symbol}: {data['Error Message']}")
        if "Note" in data:
            raise ProviderError(f"Alpha Vantage rate limit hit for {symbol}: {data['Note']}")
        if "Information" in data:
            raise ProviderError(f"Alpha Vantage access denied for {symbol}: {data['Information']}")

        ts = data.get("Time Series (Daily)", {})
        if not ts:
            raise ProviderError(f"Alpha Vantage returned no data for {symbol}")

        bars: list[PriceBarDTO] = []
        for date_str, vals in ts.items():
            row_date = date.fromisoformat(date_str)
            if row_date < start_date or row_date > end_date:
                continue
            bars.append(
                PriceBarDTO(
                    symbol=symbol,
                    date=row_date,
                    open=_d(vals.get("1. open")),
                    high=_d(vals.get("2. high")),
                    low=_d(vals.get("3. low")),
                    close=_d(vals.get("4. close")),
                    adjusted_close=None,
                    volume=_i(vals.get("5. volume")),
                    currency=None,
                    source="alpha_vantage",
                )
            )
        return bars


def _d(val: str | None) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(val)
    except Exception:
        return None


def _i(val: str | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except Exception:
        return None
