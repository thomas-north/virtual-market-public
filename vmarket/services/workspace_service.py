from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from vmarket.models.workspace import DecisionJournalEntryRecord, WorkflowSessionRecord
from vmarket.repositories import workspace as workspace_repo
from vmarket.web.models import (
    DecisionJournalEntry,
    LinkedArtifactRef,
    WorkflowSession,
    WorkflowSessionSummary,
)


def _json_list(values: list[str] | None) -> str:
    return json.dumps(values or [])


def _to_workflow_session(record: WorkflowSessionRecord) -> WorkflowSession:
    return WorkflowSession(
        id=record.id,
        workflow=record.workflow,  # type: ignore[arg-type]
        title=record.title,
        summary=record.summary,
        input_payload=json.loads(record.input_json or "{}"),
        output_payload=json.loads(record.output_json or "{}"),
        related_symbols=json.loads(record.related_symbols_json or "[]"),
        related_themes=json.loads(record.related_themes_json or "[]"),
        latest_exported_at=record.latest_exported_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_journal_entry(record: DecisionJournalEntryRecord) -> DecisionJournalEntry:
    linked_action_ids = json.loads(record.linked_action_ids_json or "[]")
    linked_artifacts = [
        LinkedArtifactRef(kind="staged_action", ref_id=str(action_id))
        for action_id in linked_action_ids
    ]
    if record.workflow_session_id is not None:
        linked_artifacts.append(
            LinkedArtifactRef(
                kind="workflow_session",
                ref_id=str(record.workflow_session_id),
            )
        )
    return DecisionJournalEntry(
        id=record.id,
        workflow=record.workflow,  # type: ignore[arg-type]
        title=record.title,
        summary=record.summary,
        rationale=record.rationale,
        open_questions=json.loads(record.open_questions_json or "[]"),
        linked_artifacts=linked_artifacts,
        related_symbols=json.loads(record.related_symbols_json or "[]"),
        related_themes=json.loads(record.related_themes_json or "[]"),
        workflow_session_id=record.workflow_session_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def record_workflow_session(
    session: Session,
    *,
    workflow: str,
    title: str,
    summary: str | None,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    related_symbols: list[str] | None = None,
    related_themes: list[str] | None = None,
) -> WorkflowSession:
    record = workspace_repo.add_workflow_session(
        session,
        WorkflowSessionRecord(
            workflow=workflow,
            title=title,
            summary=summary,
            input_json=json.dumps(input_payload, sort_keys=True, default=str),
            output_json=json.dumps(output_payload, sort_keys=True, default=str),
            related_symbols_json=_json_list(related_symbols),
            related_themes_json=_json_list(related_themes),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )
    return _to_workflow_session(record)


def mark_session_exported(session: Session, session_id: int) -> WorkflowSession:
    record = workspace_repo.get_workflow_session(session, session_id)
    if record is None:
        raise ValueError(f"Unknown workflow session id: {session_id}")
    record.latest_exported_at = datetime.now(UTC)
    record.updated_at = datetime.now(UTC)
    session.flush()
    return _to_workflow_session(record)


def get_workflow_session(session: Session, session_id: int) -> WorkflowSession | None:
    record = workspace_repo.get_workflow_session(session, session_id)
    return _to_workflow_session(record) if record is not None else None


def list_workflow_sessions(
    session: Session,
    workflow: str | None = None,
    limit: int | None = None,
) -> list[WorkflowSession]:
    return [
        _to_workflow_session(record)
        for record in workspace_repo.list_workflow_sessions(
            session,
            workflow=workflow,
            limit=limit,
        )
    ]


def list_workflow_session_summaries(
    session: Session,
    workflow: str | None = None,
    limit: int | None = None,
) -> list[WorkflowSessionSummary]:
    return [
        WorkflowSessionSummary(
            id=item.id,
            workflow=item.workflow,
            title=item.title,
            summary=item.summary,
            related_symbols=item.related_symbols,
            related_themes=item.related_themes,
            latest_exported_at=item.latest_exported_at,
            updated_at=item.updated_at,
        )
        for item in list_workflow_sessions(session, workflow=workflow, limit=limit)
    ]


def create_journal_entry(
    session: Session,
    *,
    workflow: str,
    title: str,
    summary: str,
    rationale: str | None = None,
    open_questions: list[str] | None = None,
    linked_action_ids: list[int] | None = None,
    related_symbols: list[str] | None = None,
    related_themes: list[str] | None = None,
    workflow_session_id: int | None = None,
) -> DecisionJournalEntry:
    record = workspace_repo.add_journal_entry(
        session,
        DecisionJournalEntryRecord(
            workflow=workflow,
            title=title,
            summary=summary,
            rationale=rationale,
            open_questions_json=json.dumps(open_questions or []),
            linked_action_ids_json=json.dumps(linked_action_ids or []),
            related_symbols_json=_json_list(related_symbols),
            related_themes_json=_json_list(related_themes),
            workflow_session_id=workflow_session_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )
    return _to_journal_entry(record)


def list_journal_entries(
    session: Session,
    workflow: str | None = None,
    limit: int | None = None,
) -> list[DecisionJournalEntry]:
    return [
        _to_journal_entry(record)
        for record in workspace_repo.list_journal_entries(
            session,
            workflow=workflow,
            limit=limit,
        )
    ]
