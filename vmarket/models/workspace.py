from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from vmarket.db import Base


class WorkflowSessionRecord(Base):
    __tablename__ = "workflow_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    related_symbols_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    related_themes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    latest_exported_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
    )


class DecisionJournalEntryRecord(Base):
    __tablename__ = "decision_journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    open_questions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    linked_action_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    related_symbols_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    related_themes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    workflow_session_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
    )
