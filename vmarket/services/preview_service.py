from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from vmarket.repositories import fx as fx_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.repositories import prices as price_repo
from vmarket.services.cash_service import get_all_balances
from vmarket.services.valuation_service import compute_positions
from vmarket.web.models import StagedAction


@dataclass
class ActionPreview:
    symbol: str
    action_kind: str
    quantity: Decimal
    price: Decimal
    price_is_estimated: bool
    currency: str
    estimated_cost: Decimal
    cash_balance: Decimal
    cash_after: Decimal
    cash_sufficient: bool
    current_quantity: Decimal
    new_quantity: Decimal
    oversell: bool
    new_weight_pct: float | None
    invalid: bool
    invalid_reason: str | None


def compute_action_preview(session: Session, action: StagedAction) -> ActionPreview | None:
    """Compute a what-if preview for a pending buy or sell action."""
    if action.kind not in ("buy", "sell"):
        return None

    payload = action.payload
    symbol = str(payload.get("symbol") or "").strip()
    currency = str(payload.get("currency") or "").strip().upper()

    try:
        quantity = Decimal(str(payload.get("quantity") or "0"))
    except Exception:
        return _invalid(symbol, action.kind, currency, "Could not parse quantity.")

    price_raw = str(payload.get("price") or "").strip()
    price_is_estimated = False
    price: Decimal | None = None

    if price_raw:
        try:
            price = Decimal(price_raw)
        except Exception:
            price = None

    if price is None:
        instrument = inst_repo.get_by_symbol(session, symbol)
        if instrument:
            bar = price_repo.get_latest(session, instrument.id)
            price = price_repo.best_price(bar) if bar else None
        price_is_estimated = price is not None

    if price is None:
        return _invalid(
            symbol, action.kind, currency,
            "No price available — sync prices or specify one explicitly.",
        )

    estimated_cost = quantity * price

    balances = get_all_balances(session)
    cash_balance = balances.get(currency, Decimal("0"))

    if action.kind == "buy":
        cash_after = cash_balance - estimated_cost
        cash_sufficient = cash_after >= 0
    else:
        cash_after = cash_balance + estimated_cost
        cash_sufficient = True

    positions = compute_positions(session)
    pos = next((p for p in positions if p.symbol == symbol), None)
    current_quantity = pos.quantity if pos else Decimal("0")
    new_quantity = (
        current_quantity + quantity if action.kind == "buy" else current_quantity - quantity
    )
    oversell = action.kind == "sell" and new_quantity < 0

    portfolio = port_repo.get_or_create_default(session)
    base_currency = portfolio.base_currency.upper()

    current_total_base = sum(
        (p.value_in_base for p in positions if p.value_in_base is not None), Decimal("0")
    )

    cost_in_base: Decimal | None
    if currency == base_currency:
        cost_in_base = estimated_cost
    else:
        fx = fx_repo.get_latest_rate(session, base=base_currency, quote=currency)
        cost_in_base = (estimated_cost / fx[1]) if fx else None

    new_weight_pct: float | None = None
    if cost_in_base is not None and current_total_base > 0:
        pos_base = pos.value_in_base or Decimal("0")
        new_pos_base = pos_base + cost_in_base if action.kind == "buy" else pos_base - cost_in_base
        projected_total = (
            current_total_base + cost_in_base
            if action.kind == "buy"
            else current_total_base - cost_in_base
        )
        if projected_total > 0:
            new_weight_pct = float(new_pos_base / projected_total * 100)

    return ActionPreview(
        symbol=symbol,
        action_kind=action.kind,
        quantity=quantity,
        price=price,
        price_is_estimated=price_is_estimated,
        currency=currency,
        estimated_cost=estimated_cost,
        cash_balance=cash_balance,
        cash_after=cash_after,
        cash_sufficient=cash_sufficient,
        current_quantity=current_quantity,
        new_quantity=new_quantity,
        oversell=oversell,
        new_weight_pct=new_weight_pct,
        invalid=False,
        invalid_reason=None,
    )


def _invalid(
    symbol: str, action_kind: str, currency: str, reason: str
) -> ActionPreview:
    z = Decimal("0")
    return ActionPreview(
        symbol=symbol, action_kind=action_kind, quantity=z, price=z,
        price_is_estimated=False, currency=currency, estimated_cost=z,
        cash_balance=z, cash_after=z, cash_sufficient=False,
        current_quantity=z, new_quantity=z, oversell=False,
        new_weight_pct=None, invalid=True, invalid_reason=reason,
    )
