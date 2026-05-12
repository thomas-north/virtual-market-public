from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from vmarket.models.staged_action import StagedActionRecord


def add(session: Session, action: StagedActionRecord) -> StagedActionRecord:
    session.add(action)
    session.flush()
    return action


def get(session: Session, action_id: int) -> StagedActionRecord | None:
    return session.get(StagedActionRecord, action_id)


def list_all(session: Session, status: str | None = None) -> list[StagedActionRecord]:
    stmt: Select[tuple[StagedActionRecord]] = select(StagedActionRecord)
    if status is not None:
        stmt = stmt.where(StagedActionRecord.status == status)
    stmt = stmt.order_by(StagedActionRecord.created_at.desc(), StagedActionRecord.id.desc())
    return list(session.scalars(stmt))
