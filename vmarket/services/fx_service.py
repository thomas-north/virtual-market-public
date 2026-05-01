from datetime import date, timedelta
from decimal import Decimal

import requests
from sqlalchemy.orm import Session

from vmarket.repositories import fx as fx_repo

_FRANKFURTER_BASE = "https://api.frankfurter.app"


def sync_fx_rates(session: Session, base: str, quotes: list[str], days: int = 7) -> int:
    """Fetch FX rates from Frankfurter API (free, no key required). Returns rows upserted."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    count = 0
    for quote in quotes:
        if quote.upper() == base.upper():
            continue
        try:
            url = f"{_FRANKFURTER_BASE}/{start}..{end}"
            resp = requests.get(url, params={"from": base, "to": quote}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            for date_str, rates in data.get("rates", {}).items():
                rate_val = rates.get(quote)
                if rate_val is None:
                    continue
                fx_repo.upsert_fx_rate(
                    session,
                    fx_date=date.fromisoformat(date_str),
                    base=base.upper(),
                    quote=quote.upper(),
                    rate=Decimal(str(rate_val)),
                    source="frankfurter",
                )
                count += 1
        except Exception:
            pass
    return count
