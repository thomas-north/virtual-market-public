from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from vmarket.models.import_draft import ImportDraftRecord


def add(session: Session, draft: ImportDraftRecord) -> ImportDraftRecord:
    session.add(draft)
    session.flush()
    return draft


def get(session: Session, draft_id: int) -> ImportDraftRecord | None:
    return session.get(ImportDraftRecord, draft_id)


def list_all(session: Session, status: str | None = None) -> list[ImportDraftRecord]:
    query = select(ImportDraftRecord).order_by(ImportDraftRecord.created_at.desc())
    if status is not None:
        query = query.where(ImportDraftRecord.status == status)
    return list(session.scalars(query))
