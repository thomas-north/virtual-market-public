from sqlalchemy import select
from sqlalchemy.orm import Session

from vmarket.models.workspace import DecisionJournalEntryRecord, WorkflowSessionRecord


def add_workflow_session(
    session: Session,
    record: WorkflowSessionRecord,
) -> WorkflowSessionRecord:
    session.add(record)
    session.flush()
    return record


def get_workflow_session(session: Session, session_id: int) -> WorkflowSessionRecord | None:
    return session.get(WorkflowSessionRecord, session_id)


def list_workflow_sessions(
    session: Session,
    workflow: str | None = None,
    limit: int | None = None,
) -> list[WorkflowSessionRecord]:
    stmt = select(WorkflowSessionRecord).order_by(WorkflowSessionRecord.updated_at.desc())
    if workflow is not None:
        stmt = stmt.where(WorkflowSessionRecord.workflow == workflow)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def add_journal_entry(
    session: Session,
    record: DecisionJournalEntryRecord,
) -> DecisionJournalEntryRecord:
    session.add(record)
    session.flush()
    return record


def get_journal_entry(session: Session, entry_id: int) -> DecisionJournalEntryRecord | None:
    return session.get(DecisionJournalEntryRecord, entry_id)


def list_journal_entries(
    session: Session,
    workflow: str | None = None,
    limit: int | None = None,
) -> list[DecisionJournalEntryRecord]:
    stmt = select(DecisionJournalEntryRecord).order_by(
        DecisionJournalEntryRecord.updated_at.desc()
    )
    if workflow is not None:
        stmt = stmt.where(DecisionJournalEntryRecord.workflow == workflow)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))
