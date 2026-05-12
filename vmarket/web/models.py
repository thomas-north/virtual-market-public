from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from vmarket.consult.models import (
    ConsultantProfile,
    FactsheetSummary,
    PortfolioConsultRequest,
    PortfolioDiagnosis,
)
from vmarket.research.schema import NormalizedEvidenceItem
from vmarket.services.data_quality import DataQualityReport
from vmarket.themes.models import (
    ThemeAnalysisRequest,
    ThemeAnalysisResult,
    ThemeDefinition,
)

WorkflowName = Literal[
    "onboarding-import",
    "thematic-analysis",
    "portfolio-consultation",
    "morning-brief",
    "research-follow-up",
    "action-review",
]

StagedActionStatus = Literal["pending", "confirmed", "discarded"]
StagedActionKind = Literal["buy", "sell", "watch_add", "watch_remove", "save_research_note"]


class MemoSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    title: str | None = None
    excerpt: str | None = None
    updated_at: str | None = None


class ResearchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exists: bool
    normalized_files: int
    tracked_symbols: list[str] = Field(default_factory=list)
    log_path: str | None = None
    last_log_line: str | None = None


class StagedActionsSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pending_count: int = 0
    confirmed_count: int = 0
    discarded_count: int = 0


class AgentReadySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_workflow: WorkflowName
    available_workflows: list[WorkflowName] = Field(default_factory=list)
    external_harness_note: str
    recommended_commands: list[str] = Field(default_factory=list)


class CockpitOverviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_snapshot: dict[str, Any]
    data_quality_report: DataQualityReport
    latest_memo: MemoSummary
    research_summary: ResearchSummary
    staged_actions_summary: StagedActionsSummary
    agent_summary: AgentReadySummary
    supported_themes: list[ThemeDefinition] = Field(default_factory=list)


class StagedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    kind: StagedActionKind
    payload: dict[str, Any]
    source: str
    explanation: str | None = None
    status: StagedActionStatus
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None = None
    discarded_at: datetime | None = None


class LinkedArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["workflow_session", "staged_action", "factsheet", "research_note"]
    ref_id: str
    label: str | None = None


class WorkflowSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    workflow: WorkflowName
    title: str
    summary: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    related_symbols: list[str] = Field(default_factory=list)
    related_themes: list[str] = Field(default_factory=list)
    latest_exported_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowSessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    workflow: WorkflowName
    title: str
    summary: str | None = None
    related_symbols: list[str] = Field(default_factory=list)
    related_themes: list[str] = Field(default_factory=list)
    latest_exported_at: datetime | None = None
    updated_at: datetime


class DecisionJournalEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    workflow: WorkflowName
    title: str
    summary: str
    rationale: str | None = None
    open_questions: list[str] = Field(default_factory=list)
    linked_artifacts: list[LinkedArtifactRef] = Field(default_factory=list)
    related_symbols: list[str] = Field(default_factory=list)
    related_themes: list[str] = Field(default_factory=list)
    workflow_session_id: int | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: WorkflowName
    title: str
    summary: str
    route: str
    primary_command: str


class ResearchBriefPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    rendered_markdown: str
    evidence_items: list[NormalizedEvidenceItem] = Field(default_factory=list)


class ResearchFollowUpTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    summary: str
    source_workflow: WorkflowName
    suggested_actions: list[str] = Field(default_factory=list)


class ResearchWorkspaceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tracked_symbols: list[str] = Field(default_factory=list)
    normalized_files: int = 0
    recent_follow_ups: list[ResearchFollowUpTask] = Field(default_factory=list)
    recent_log_line: str | None = None


class AgentContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: WorkflowName
    generated_at: datetime
    overview: CockpitOverviewPayload
    latest_memo_excerpt: str | None = None
    consult_request: PortfolioConsultRequest | None = None
    consult_diagnosis: PortfolioDiagnosis | None = None
    consult_factsheet: FactsheetSummary | None = None
    theme_request: ThemeAnalysisRequest | None = None
    theme_analysis: ThemeAnalysisResult | None = None
    staged_actions: list[StagedAction] = Field(default_factory=list)
    recommended_commands: list[str] = Field(default_factory=list)


class ConsultantPagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved_profile: ConsultantProfile
    diagnosis: PortfolioDiagnosis
    factsheet_summary: FactsheetSummary | None = None


class WorkflowsPagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_cards: list[WorkflowCard] = Field(default_factory=list)
    recent_sessions: list[WorkflowSessionSummary] = Field(default_factory=list)
    recent_journal_entries: list[DecisionJournalEntry] = Field(default_factory=list)


class PromptPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: WorkflowName
    title: str
    summary: str
    recommended_commands: list[str] = Field(default_factory=list)
    prompt_markdown: str
