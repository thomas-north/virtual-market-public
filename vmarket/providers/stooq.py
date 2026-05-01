"""Stooq daily price provider — uses Stooq CSV API directly, no pandas-datareader."""
import csv
import io
from datetime import date
from decimal import Decimal

import requests

from vmarket.dto.price_bar import PriceBarDTO
from vmarket.errors import ProviderError

_BASE_URL = "https://stooq.com/q/d/l/"


class StooqProvider:
    name = "stooq"

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
        params = {
            "s": symbol.lower(),
            "d1": start_date.strftime("%Y%m%d"),
            "d2": end_date.strftime("%Y%m%d"),
            "i": "d",
        }
        try:
            resp = requests.get(_BASE_URL, params=params, timeout=20)
            resp.raise_for_status()
        except Exception as exc:
            raise ProviderError(f"Stooq request failed for {symbol}: {exc}") from exc

        text = resp.text.strip()
        if not text or "No data" in text or len(text.splitlines()) < 2:
            raise ProviderError(f"Stooq returned no data for {symbol}")

        bars: list[PriceBarDTO] = []
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            try:
                row_date = date.fromisoformat(row["Date"])
            except (KeyError, ValueError):
                continue
            close_raw = row.get("Close", "")
            if not close_raw or close_raw in ("null", ""):
                continue
            try:
                close = Decimal(close_raw)
            except Exception:
                continue
            bars.append(
                PriceBarDTO(
                    symbol=symbol,
                    date=row_date,
                    open=_d(row.get("Open")),
                    high=_d(row.get("High")),
                    low=_d(row.get("Low")),
                    close=close,
                    adjusted_close=None,
                    volume=_i(row.get("Volume")),
                    currency=None,
                    source="stooq",
                )
            )

        if not bars:
            raise ProviderError(f"Stooq returned no parseable rows for {symbol}")

        return bars


def _d(val: str | None) -> Decimal | None:
    if not val or val in ("null", ""):
        return None
    try:
        return Decimal(val)
    except Exception:
        return None


def _i(val: str | None) -> int | None:
    if not val or val in ("null", ""):
        return None
    try:
        return int(float(val))
    except Exception:
        return None
