from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

STALE_PRICE_DAYS = 5
STALE_FX_DAYS = 5


class PriceState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"
    MANUAL = "manual"


class FxState(StrEnum):
    NOT_NEEDED = "not_needed"
    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"


@dataclass(frozen=True)
class PriceStatus:
    state: PriceState
    label: str
    note: str


def is_manual_price_symbol(symbol: str) -> bool:
    normalized = symbol.upper()
    return len(normalized) == 7 and normalized.isalnum() and "." not in normalized


def price_status_for(
    symbol: str,
    latest_date: date | None,
    *,
    as_of: date | None = None,
) -> PriceStatus:
    today = as_of or date.today()
    normalized = symbol.upper()

    if latest_date is None:
        if is_manual_price_symbol(normalized):
            return PriceStatus(
                state=PriceState.MANUAL,
                label="manual",
                note="Manual-price instrument. Automatic market sync is not available.",
            )
        return PriceStatus(
            state=PriceState.MISSING,
            label="missing",
            note="No synced market price is available yet.",
        )

    age_days = (today - latest_date).days
    if age_days > STALE_PRICE_DAYS:
        return PriceStatus(
            state=PriceState.STALE,
            label=f"stale {age_days}d",
            note=f"Latest market price is {age_days} days old.",
        )

    return PriceStatus(
        state=PriceState.FRESH,
        label="fresh",
        note="Latest market price is current.",
    )


def fx_state_for(
    latest_date: date | None,
    *,
    same_currency: bool = False,
    as_of: date | None = None,
) -> FxState:
    if same_currency:
        return FxState.NOT_NEEDED
    if latest_date is None:
        return FxState.MISSING

    today = as_of or date.today()
    if (today - latest_date).days > STALE_FX_DAYS:
        return FxState.STALE
    return FxState.FRESH


def combine_fx_states(*states: FxState) -> FxState:
    ordered = [FxState.MISSING, FxState.STALE, FxState.FRESH, FxState.NOT_NEEDED]
    for state in ordered:
        if state in states:
            return state
    return FxState.NOT_NEEDED


def fx_state_label(state: FxState) -> str:
    if state == FxState.FRESH:
        return "fresh"
    if state == FxState.STALE:
        return "stale"
    if state == FxState.MISSING:
        return "missing"
    return "n/a"
