from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy.orm import Session

from vmarket.config import get_db_path, get_user_data_dir
from vmarket.dto.price_bar import PriceBarDTO
from vmarket.models.import_draft import ImportDraftRecord
from vmarket.onboarding.models import (
    ImportDraft,
    ImportDraftRow,
    ImportKind,
    ImportSourceKind,
    OnboardingState,
)
from vmarket.repositories import cash as cash_repo
from vmarket.repositories import import_drafts as draft_repo
from vmarket.repositories import instruments as inst_repo
from vmarket.repositories import portfolios as port_repo
from vmarket.repositories import prices as price_repo
from vmarket.repositories import trades as trade_repo
from vmarket.repositories import watchlist as watch_repo
from vmarket.services.cash_service import deposit
from vmarket.services.trade_service import buy
from vmarket.services.watchlist_service import add_to_watchlist

PORTFOLIO_FIELDS = {
    "symbol",
    "name",
    "quantity",
    "average_cost",
    "cost_basis",
    "current_value",
    "gain_amount",
    "gain_percent",
    "currency",
    "asset_type",
    "trade_date",
    "notes",
    "current_price",
}
WATCHLIST_FIELDS = {
    "symbol",
    "name",
    "currency",
    "asset_type",
    "target_buy_price",
    "target_sell_price",
    "notes",
}
FIELD_ALIASES = {
    "ticker": "symbol",
    "holding": "symbol",
    "company": "name",
    "fund": "name",
    "qty": "quantity",
    "units": "quantity",
    "shares": "quantity",
    "avg_cost": "average_cost",
    "avg_price": "average_cost",
    "average_price": "average_cost",
    "cost": "average_cost",
    "book_cost": "cost_basis",
    "total_cost": "cost_basis",
    "cost_basis": "cost_basis",
    "value": "current_value",
    "current_value": "current_value",
    "market_value": "current_value",
    "holding_value": "current_value",
    "change": "gain_amount",
    "gain": "gain_amount",
    "profit": "gain_amount",
    "p_l": "gain_amount",
    "p/l": "gain_amount",
    "gain_percent": "gain_percent",
    "gain_pct": "gain_percent",
    "p_l_percent": "gain_percent",
    "p/l_percent": "gain_percent",
    "price": "average_cost",
    "ccy": "currency",
    "type": "asset_type",
    "date": "trade_date",
    "latest": "current_price",
    "current": "current_price",
    "buy_target": "target_buy_price",
    "buy below": "target_buy_price",
    "sell_target": "target_sell_price",
    "sell above": "target_sell_price",
}


def ensure_user_data_dirs(root: Path | None = None) -> Path:
    user_data = root or get_user_data_dir()
    for child in ["imports", "screenshots", "exports", "notes"]:
        (user_data / child).mkdir(parents=True, exist_ok=True)
    return user_data


def _decimal(raw: object) -> Decimal | None:
    text = str(raw or "").strip().replace(",", "").replace("£", "").replace("$", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _date(raw: object) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _field_name(raw: str) -> str:
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return FIELD_ALIASES.get(normalized, normalized)


def _normalize_row(raw: dict[str, object], kind: ImportKind) -> ImportDraftRow:
    fields = PORTFOLIO_FIELDS if kind == "portfolio" else WATCHLIST_FIELDS
    mapped = {_field_name(key): value for key, value in raw.items()}
    row = ImportDraftRow(
        symbol=str(mapped.get("symbol") or "").strip().upper(),
        name=str(mapped.get("name") or "").strip() or None,
        quantity=_decimal(mapped.get("quantity")),
        average_cost=_decimal(mapped.get("average_cost")),
        cost_basis=_decimal(mapped.get("cost_basis")),
        current_value=_decimal(mapped.get("current_value")),
        gain_amount=_decimal(mapped.get("gain_amount")),
        gain_percent=_decimal(mapped.get("gain_percent")),
        currency=(str(mapped.get("currency") or "").strip().upper() or None),
        asset_type=str(mapped.get("asset_type") or "").strip().lower() or None,
        trade_date=_date(mapped.get("trade_date")),
        notes=str(mapped.get("notes") or "").strip() or None,
        current_price=_decimal(mapped.get("current_price")),
        target_buy_price=_decimal(mapped.get("target_buy_price")),
        target_sell_price=_decimal(mapped.get("target_sell_price")),
    )
    row.warnings = _warnings_for_row(row, kind)
    unknown = sorted(set(mapped) - fields)
    if unknown:
        row.warnings.append(f"Ignored unrecognised fields: {', '.join(unknown)}")
    return row


def _warnings_for_row(row: ImportDraftRow, kind: ImportKind) -> list[str]:
    warnings: list[str] = []
    if not row.symbol:
        warnings.append("Missing symbol")
    elif "." not in row.symbol and not re.fullmatch(r"[A-Z0-9]{7}", row.symbol):
        warnings.append("Symbol may need a market suffix such as .US or .L")
    if kind == "portfolio":
        unit_based = _is_unit_based_row(row)
        value_snapshot = _is_value_snapshot_row(row)
        if not unit_based and not value_snapshot:
            warnings.append(
                "Missing precise units/cost or approximate value snapshot fields"
            )
        elif value_snapshot and not unit_based:
            row.notes = _append_note(
                row.notes,
                "Approximate value-snapshot import: units were unavailable.",
            )
    if row.currency is None:
        warnings.append("Missing currency")
    return warnings


def _is_unit_based_row(row: ImportDraftRow) -> bool:
    return (
        row.quantity is not None
        and row.quantity > 0
        and row.average_cost is not None
        and row.average_cost > 0
    )


def _snapshot_cost_basis(row: ImportDraftRow) -> Decimal | None:
    if row.cost_basis is not None and row.cost_basis > 0:
        return row.cost_basis
    if row.current_value is None or row.current_value <= 0:
        return None
    if row.gain_amount is not None:
        inferred = row.current_value - row.gain_amount
        return inferred if inferred > 0 else None
    if row.gain_percent is not None and row.gain_percent != Decimal("-100"):
        divisor = Decimal("1") + (row.gain_percent / Decimal("100"))
        if divisor > 0:
            return row.current_value / divisor
    if (
        row.average_cost is not None
        and row.average_cost > 0
        and row.current_price is not None
        and row.current_price > 0
    ):
        inferred_quantity = row.current_value / row.current_price
        return inferred_quantity * row.average_cost
    return None


def _is_value_snapshot_row(row: ImportDraftRow) -> bool:
    return (
        row.current_value is not None
        and row.current_value > 0
        and _snapshot_cost_basis(row) is not None
    )


def _append_note(existing: str | None, extra: str) -> str:
    if existing:
        return f"{existing} {extra}"
    return extra


def _dedupe_warnings(rows: list[ImportDraftRow]) -> None:
    seen: set[str] = set()
    for row in rows:
        if not row.symbol:
            continue
        if row.symbol in seen:
            row.warnings.append("Duplicate symbol in this import draft")
        seen.add(row.symbol)


def parse_csv_rows(content: str, kind: ImportKind) -> list[ImportDraftRow]:
    reader = csv.DictReader(io.StringIO(content))
    rows = [_normalize_row(dict(row), kind) for row in reader]
    _dedupe_warnings(rows)
    return rows


def parse_pasted_rows(content: str, kind: ImportKind) -> list[ImportDraftRow]:
    text = content.strip()
    if not text:
        return []
    delimiter = "\t" if "\t" in text.splitlines()[0] else ","
    if delimiter in text.splitlines()[0]:
        return parse_csv_rows(text, kind)

    rows: list[ImportDraftRow] = []
    for line in text.splitlines():
        if "," in line:
            parts = [part.strip() for part in line.split(",") if part.strip()]
        else:
            parts = [part.strip() for part in line.split() if part.strip()]
        if not parts:
            continue
        raw: dict[str, object] = {"symbol": parts[0]}
        if kind == "portfolio":
            if len(parts) > 1:
                raw["quantity"] = parts[1]
            if len(parts) > 2:
                raw["average_cost"] = parts[2]
            if len(parts) > 3:
                raw["currency"] = parts[3]
            if len(parts) > 4:
                raw["name"] = " ".join(parts[4:])
        else:
            if len(parts) > 1:
                raw["currency"] = parts[1]
            if len(parts) > 2:
                raw["asset_type"] = parts[2]
            if len(parts) > 3:
                raw["name"] = " ".join(parts[3:])
        rows.append(_normalize_row(raw, kind))
    _dedupe_warnings(rows)
    return rows


def _record_to_model(record: ImportDraftRecord) -> ImportDraft:
    rows = [
        ImportDraftRow.model_validate(row)
        for row in json.loads(record.rows_json or "[]")
    ]
    return ImportDraft(
        id=record.id,
        kind=record.kind,  # type: ignore[arg-type]
        source_kind=record.source_kind,  # type: ignore[arg-type]
        status=record.status,  # type: ignore[arg-type]
        rows=rows,
        original_filename=record.original_filename,
        stored_path=record.stored_path,
        notes=record.notes,
        row_count=record.row_count,
        warning_count=record.warning_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
        confirmed_at=record.confirmed_at,
        discarded_at=record.discarded_at,
    )


def create_import_draft(
    session: Session,
    *,
    kind: ImportKind,
    source_kind: ImportSourceKind,
    rows: list[ImportDraftRow] | None = None,
    original_filename: str | None = None,
    stored_path: str | None = None,
    notes: str | None = None,
) -> ImportDraft:
    rows = rows or []
    warning_count = sum(len(row.warnings) for row in rows)
    record = ImportDraftRecord(
        kind=kind,
        source_kind=source_kind,
        status="pending",
        original_filename=original_filename,
        stored_path=stored_path,
        rows_json=json.dumps([row.model_dump(mode="json") for row in rows]),
        notes=notes,
        row_count=len(rows),
        warning_count=warning_count,
    )
    draft_repo.add(session, record)
    return _record_to_model(record)


def get_import_draft(session: Session, draft_id: int) -> ImportDraft | None:
    record = draft_repo.get(session, draft_id)
    return _record_to_model(record) if record else None


def list_import_drafts(session: Session, status: str | None = None) -> list[ImportDraft]:
    return [_record_to_model(record) for record in draft_repo.list_all(session, status=status)]


def _require_pending(session: Session, draft_id: int) -> ImportDraftRecord:
    record = draft_repo.get(session, draft_id)
    if record is None:
        raise ValueError(f"Unknown import draft id: {draft_id}")
    if record.status != "pending":
        raise ValueError(f"Import draft {draft_id} is already {record.status}.")
    return record


def confirm_import_draft(session: Session, draft_id: int) -> ImportDraft:
    record = _require_pending(session, draft_id)
    draft = _record_to_model(record)
    if draft.kind == "portfolio":
        _confirm_portfolio_rows(session, draft.rows)
    elif draft.kind == "watchlist":
        _confirm_watchlist_rows(session, draft.rows)
    else:
        raise ValueError("Screenshot drafts need an agent-extracted row draft before confirmation.")
    record.status = "confirmed"
    record.confirmed_at = datetime.now(UTC).replace(tzinfo=None)
    session.flush()
    return _record_to_model(record)


def discard_import_draft(session: Session, draft_id: int) -> ImportDraft:
    record = _require_pending(session, draft_id)
    record.status = "discarded"
    record.discarded_at = datetime.now(UTC).replace(tzinfo=None)
    session.flush()
    return _record_to_model(record)


def _confirm_portfolio_rows(session: Session, rows: list[ImportDraftRow]) -> None:
    for row in rows:
        if row.warnings:
            raise ValueError("Resolve import warnings before confirming a portfolio draft.")
        quantity, average_cost, current_price, note = _position_import_values(row)
        currency = (row.currency or "GBP").upper()
        inst_repo.get_or_create(
            session,
            symbol=row.symbol,
            provider_symbol=row.symbol,
            name=row.name,
            currency=currency,
            asset_type=row.asset_type,
        )
        total_cost = quantity * average_cost
        deposit(
            session,
            total_cost,
            currency,
            notes=f"Import funding for {row.symbol}",
            on_date=row.trade_date,
        )
        buy(
            session,
            row.symbol,
            quantity,
            price=average_cost,
            currency=currency,
            on_date=row.trade_date,
            notes=note,
        )
        if current_price is not None:
            instrument = inst_repo.get_by_symbol(session, row.symbol)
            if instrument is not None:
                price_repo.upsert_price_bars(
                    session,
                    instrument.id,
                    [
                        PriceBarDTO(
                            symbol=row.symbol,
                            date=date.today(),
                            open=None,
                            high=None,
                            low=None,
                            close=current_price,
                            adjusted_close=current_price,
                            volume=None,
                            currency=currency,
                            source="manual_import",
                        )
                    ],
                )


def _position_import_values(
    row: ImportDraftRow,
) -> tuple[Decimal, Decimal, Decimal | None, str]:
    if _is_unit_based_row(row):
        assert row.quantity is not None
        assert row.average_cost is not None
        note = row.notes or "Imported opening position"
        return row.quantity, row.average_cost, row.current_price, note

    cost_basis = _snapshot_cost_basis(row)
    if cost_basis is None or row.current_value is None:
        raise ValueError("Missing value-snapshot fields for approximate import.")
    note = _append_note(
        row.notes,
        (
            "Approximate value-snapshot import: recorded as one synthetic unit "
            "because broker units were unavailable."
        ),
    )
    return Decimal("1"), cost_basis, row.current_value, note


def _confirm_watchlist_rows(session: Session, rows: list[ImportDraftRow]) -> None:
    for row in rows:
        blocking = [warning for warning in row.warnings if warning.startswith("Missing")]
        if blocking:
            raise ValueError("Resolve import warnings before confirming a watchlist draft.")
        add_to_watchlist(
            session,
            row.symbol,
            name=row.name,
            currency=row.currency,
            asset_type=row.asset_type,
        )
        instrument = inst_repo.get_by_symbol(session, row.symbol)
        if instrument is None:
            continue
        item = watch_repo.get_by_instrument_id(session, instrument.id)
        if item is not None:
            item.target_buy_price = row.target_buy_price
            item.target_sell_price = row.target_sell_price
            item.notes = row.notes
    session.flush()


def get_onboarding_state(session: Session, db_path: Path | None = None) -> OnboardingState:
    portfolio = port_repo.get_or_create_default(session)
    trades = trade_repo.list_trades(session, portfolio.id)
    balances = cash_repo.get_balances_all_currencies(session, portfolio.id)
    watchlist = watch_repo.list_all(session)
    pending = list_import_drafts(session, status="pending")
    profile_ready = False
    try:
        from vmarket.consult import get_profile

        profile_ready = get_profile(session).risk_score is not None
    except Exception:
        profile_ready = False
    steps: list[str] = []
    if not balances:
        steps.append("Add fake cash or import an opening portfolio.")
    if not trades:
        steps.append("Import holdings or start with an empty watchlist.")
    if not watchlist:
        steps.append("Add a watchlist so the agent can infer areas of interest.")
    if not profile_ready:
        steps.append("Set risk score and exclusions for portfolio consultation.")
    if not steps:
        steps.append("Run a portfolio consultation or thematic analysis.")
    return OnboardingState(
        db_path=str(db_path or get_db_path()),
        user_data_dir=str(get_user_data_dir()),
        portfolio_ready=bool(trades),
        watchlist_ready=bool(watchlist),
        profile_ready=profile_ready,
        cash_ready=bool(balances),
        pending_imports=len(pending),
        suggested_next_steps=steps,
    )
