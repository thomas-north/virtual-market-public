from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from vmarket.models.staged_action import StagedActionRecord
from vmarket.repositories import staged_actions as staged_repo
from vmarket.services.trade_service import buy, sell
from vmarket.services.watchlist_service import add_to_watchlist, remove_from_watchlist
from vmarket.web.models import StagedAction, StagedActionKind


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "note"


def _payload_decimal(payload: dict[str, Any], key: str) -> Decimal | None:
    raw = payload.get(key)
    if raw in {None, ""}:
        return None
    return Decimal(str(raw))


def _to_model(record: StagedActionRecord) -> StagedAction:
    return StagedAction(
        id=record.id,
        kind=record.kind,  # type: ignore[arg-type]
        payload=json.loads(record.payload_json),
        source=record.source,
        explanation=record.explanation,
        status=record.status,  # type: ignore[arg-type]
        created_at=record.created_at,
        updated_at=record.updated_at,
        confirmed_at=record.confirmed_at,
        discarded_at=record.discarded_at,
    )


def list_actions(session: Session, status: str | None = None) -> list[StagedAction]:
    return [_to_model(record) for record in staged_repo.list_all(session, status=status)]


def stage_action(
    session: Session,
    kind: StagedActionKind,
    payload: dict[str, Any],
    source: str,
    explanation: str | None = None,
) -> StagedAction:
    record = staged_repo.add(
        session,
        StagedActionRecord(
            kind=kind,
            payload_json=json.dumps(payload, sort_keys=True),
            source=source,
            explanation=explanation,
            status="pending",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )
    return _to_model(record)


def _confirm_research_note(payload: dict[str, Any], root: Path = Path("research")) -> None:
    section = str(payload.get("section") or "questions")
    title = str(payload.get("title") or "Agent note").strip()
    body = str(payload.get("body") or "").strip()
    note_dir = root / "wiki" / section
    note_dir.mkdir(parents=True, exist_ok=True)
    path = note_dir / f"{_slugify(title)}.md"
    content = f"# {title}\n\n{body}\n"
    path.write_text(content, encoding="utf-8")

    log = root / "wiki" / "log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## [{datetime.now(UTC).date().isoformat()}] note saved {title}\n")


def confirm_action(session: Session, action_id: int) -> StagedAction:
    record = staged_repo.get(session, action_id)
    if record is None:
        raise ValueError(f"Unknown staged action id: {action_id}")
    if record.status != "pending":
        raise ValueError(f"Staged action {action_id} is already {record.status}.")

    payload = json.loads(record.payload_json)
    kind = record.kind
    if kind == "buy":
        buy(
            session,
            symbol=str(payload["symbol"]),
            quantity=_payload_decimal(payload, "quantity") or Decimal("0"),
            price=_payload_decimal(payload, "price"),
            currency=payload.get("currency"),
            notes=payload.get("notes"),
        )
    elif kind == "sell":
        sell(
            session,
            symbol=str(payload["symbol"]),
            quantity=_payload_decimal(payload, "quantity") or Decimal("0"),
            price=_payload_decimal(payload, "price"),
            currency=payload.get("currency"),
            notes=payload.get("notes"),
        )
    elif kind == "watch_add":
        add_to_watchlist(
            session,
            symbol=str(payload["symbol"]),
            name=payload.get("name"),
            currency=payload.get("currency"),
            asset_type=payload.get("asset_type"),
        )
    elif kind == "watch_remove":
        remove_from_watchlist(session, symbol=str(payload["symbol"]))
    elif kind == "save_research_note":
        _confirm_research_note(payload)
    else:
        raise ValueError(f"Unsupported staged action kind: {kind}")

    now = datetime.now(UTC)
    record.status = "confirmed"
    record.confirmed_at = now
    record.updated_at = now
    session.flush()
    return _to_model(record)


def discard_action(session: Session, action_id: int) -> StagedAction:
    record = staged_repo.get(session, action_id)
    if record is None:
        raise ValueError(f"Unknown staged action id: {action_id}")
    if record.status != "pending":
        raise ValueError(f"Staged action {action_id} is already {record.status}.")

    now = datetime.now(UTC)
    record.status = "discarded"
    record.discarded_at = now
    record.updated_at = now
    session.flush()
    return _to_model(record)
