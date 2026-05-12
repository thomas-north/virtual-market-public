from datetime import UTC, date, datetime
from decimal import Decimal

import requests

from vmarket.dto.price_bar import PriceBarDTO
from vmarket.errors import ProviderError

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}


class YahooFinanceProvider:
    name = "yahoo_finance"

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
        start_dt = datetime(
            start_date.year,
            start_date.month,
            start_date.day,
            tzinfo=UTC,
        )
        end_dt = datetime(
            end_date.year,
            end_date.month,
            end_date.day,
            23,
            59,
            59,
            tzinfo=UTC,
        )
        start_ts = int(start_dt.timestamp())
        end_ts = int(end_dt.timestamp())

        url = _CHART_URL.format(symbol=symbol)
        params = {"interval": "1d", "period1": start_ts, "period2": end_ts}
        try:
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise ProviderError(f"Yahoo Finance request failed for {symbol}: {exc}") from exc

        result_list = data.get("chart", {}).get("result")
        if not result_list:
            error = data.get("chart", {}).get("error") or "no data returned"
            raise ProviderError(f"Yahoo Finance returned no data for {symbol}: {error}")

        result = result_list[0]
        timestamps = result.get("timestamp", [])
        quotes = result.get("indicators", {}).get("quote", [{}])[0]
        opens = quotes.get("open", [])
        highs = quotes.get("high", [])
        lows = quotes.get("low", [])
        closes = quotes.get("close", [])
        volumes = quotes.get("volume", [])

        bars: list[PriceBarDTO] = []
        for i, ts in enumerate(timestamps):
            close_val = closes[i] if i < len(closes) else None
            if close_val is None:
                continue
            row_date = datetime.fromtimestamp(ts, tz=UTC).date()
            bars.append(
                PriceBarDTO(
                    symbol=symbol,
                    date=row_date,
                    open=_d(opens[i] if i < len(opens) else None),
                    high=_d(highs[i] if i < len(highs) else None),
                    low=_d(lows[i] if i < len(lows) else None),
                    close=_d(close_val),
                    adjusted_close=None,
                    volume=_i(volumes[i] if i < len(volumes) else None),
                    currency=None,
                    source="yahoo_finance",
                )
            )

        if not bars:
            raise ProviderError(f"Yahoo Finance returned no parseable bars for {symbol}")
        return bars


def _d(val: float | None) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(round(val, 6)))
    except Exception:
        return None


def _i(val: float | None) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except Exception:
        return None
