from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import job_runs as job_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.services.freshness import is_manual_price_symbol
from vmarket.services.valuation_service import compute_positions

DataQualitySeverity = Literal["neutral", "warning"]
DataQualityCategory = Literal[
    "price_sync",
    "stale_market_prices",
    "missing_market_prices",
    "manual_price_holdings",
    "missing_fx",
    "stale_fx",
    "approximate_holdings",
    "symbol_format_review",
    "pence_quote_review",
]

_SYMBOL_FORMAT = re.compile(r"^[A-Z0-9.-]+\.[A-Z]{1,4}$")


class DataQualityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: DataQualityCategory
    severity: DataQualitySeverity
    label: str
    message: str
    symbols: list[str] = Field(default_factory=list)


class DataQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    issues: list[DataQualityIssue] = Field(default_factory=list)
    warning_count: int = 0
    neutral_count: int = 0


def build_data_quality_report(session: Session) -> DataQualityReport:
    portfolio = port_repo.get_or_create_default(session)
    positions = compute_positions(session, base_currency=portfolio.base_currency)
    last_sync = job_repo.get_latest(session, "sync_prices")
    issues: list[DataQualityIssue] = []

    if last_sync and last_sync.finished_at:
        issues.append(
            DataQualityIssue(
                category="price_sync",
                severity="neutral",
                label="Last successful price sync",
                message=last_sync.finished_at.isoformat(sep=" ", timespec="seconds"),
            )
        )
    else:
        issues.append(
            DataQualityIssue(
                category="price_sync",
                severity="warning",
                label="Price sync",
                message="No successful price sync has been recorded yet.",
            )
        )

    stale_symbols = sorted(position.symbol for position in positions if position.stale)
    if stale_symbols:
        issues.append(
            DataQualityIssue(
                category="stale_market_prices",
                severity="warning",
                label="Stale market prices",
                message=", ".join(stale_symbols),
                symbols=stale_symbols,
            )
        )

    missing_symbols = sorted(
        position.symbol
        for position in positions
        if position.latest_price is None and position.price_status != "manual"
    )
    if missing_symbols:
        issues.append(
            DataQualityIssue(
                category="missing_market_prices",
                severity="warning",
                label="Missing market prices",
                message=", ".join(missing_symbols),
                symbols=missing_symbols,
            )
        )

    manual_symbols = sorted(
        position.symbol for position in positions if position.price_status == "manual"
    )
    if manual_symbols:
        issues.append(
            DataQualityIssue(
                category="manual_price_holdings",
                severity="neutral",
                label="Manual-price holdings",
                message=", ".join(manual_symbols),
                symbols=manual_symbols,
            )
        )

    fx_missing = sorted(position.symbol for position in positions if position.fx_missing)
    if fx_missing:
        issues.append(
            DataQualityIssue(
                category="missing_fx",
                severity="warning",
                label="Missing FX",
                message=", ".join(fx_missing),
                symbols=fx_missing,
            )
        )

    fx_stale = sorted(position.symbol for position in positions if position.fx_stale)
    if fx_stale:
        issues.append(
            DataQualityIssue(
                category="stale_fx",
                severity="warning",
                label="Stale FX",
                message=", ".join(fx_stale),
                symbols=fx_stale,
            )
        )

    approximate_symbols = _approximate_holding_symbols(positions)
    if approximate_symbols:
        issues.append(
            DataQualityIssue(
                category="approximate_holdings",
                severity="warning",
                label="Approximate imported holdings",
                message=(
                    "Some positions are being tracked from approximate broker snapshots "
                    "rather than exact unit-level imports."
                ),
                symbols=approximate_symbols,
            )
        )

    unresolved_symbols = _symbol_format_review_symbols(session)
    if unresolved_symbols:
        issues.append(
            DataQualityIssue(
                category="symbol_format_review",
                severity="warning",
                label="Symbols needing review",
                message=(
                    "Some active instruments are missing the usual market suffix format "
                    "(for example `.US` or `.L`)."
                ),
                symbols=unresolved_symbols,
            )
        )

    pence_symbols = _pence_quote_review_symbols(positions)
    if pence_symbols:
        issues.append(
            DataQualityIssue(
                category="pence_quote_review",
                severity="warning",
                label="Possible pence/GBP mismatch",
                message=(
                    "Price units may be mixed between pounds and pence. Review the imported "
                    "cost basis against the current quote."
                ),
                symbols=pence_symbols,
            )
        )

    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    neutral_count = sum(1 for issue in issues if issue.severity == "neutral")
    return DataQualityReport(
        generated_at=datetime.now(UTC),
        issues=issues,
        warning_count=warning_count,
        neutral_count=neutral_count,
    )


def _approximate_holding_symbols(positions) -> list[str]:
    return sorted(
        position.symbol
        for position in positions
        if position.provenance_kind != "exact" or position.provenance_confidence < 1.0
    )


def _symbol_format_review_symbols(session: Session) -> list[str]:
    flagged: list[str] = []
    for instrument in inst_repo.list_all_active(session):
        symbol = instrument.symbol.upper()
        if is_manual_price_symbol(symbol):
            continue
        if _SYMBOL_FORMAT.fullmatch(symbol):
            continue
        flagged.append(instrument.symbol)
    return sorted(flagged)


def _pence_quote_review_symbols(positions) -> list[str]:
    flagged: list[str] = []
    for position in positions:
        if not position.symbol.endswith(".L"):
            continue
        if position.avg_cost in (None, Decimal("0")):
            continue
        if position.latest_price in (None, Decimal("0")):
            continue
        if position.cost_currency != "GBP" or position.latest_price_currency != "GBP":
            continue
        ratio = position.latest_price / position.avg_cost
        if ratio >= Decimal("20") or ratio <= Decimal("0.05"):
            flagged.append(position.symbol)
    return sorted(flagged)
