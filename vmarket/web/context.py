from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from sqlalchemy.orm import Session

from vmarket.consult import diagnose_portfolio, locate_factsheet
from vmarket.consult.models import PortfolioConsultRequest
from vmarket.reports.overview import build_portfolio_snapshot_payload
from vmarket.research.brief import render_evidence_brief
from vmarket.research.store import read_symbol_evidence
from vmarket.services.data_quality import build_data_quality_report
from vmarket.services.staged_action_service import list_actions
from vmarket.services.workspace_service import (
    get_workflow_session,
    list_journal_entries,
    list_workflow_session_summaries,
    mark_session_exported,
)
from vmarket.themes import analyze_theme, list_supported_themes
from vmarket.themes.models import ThemeAnalysisRequest
from vmarket.web.models import (
    AgentContextBundle,
    AgentReadySummary,
    CockpitOverviewPayload,
    MemoSummary,
    PromptPacket,
    ResearchBriefPayload,
    ResearchFollowUpTask,
    ResearchSummary,
    ResearchWorkspaceSummary,
    StagedAction,
    StagedActionsSummary,
    WorkflowCard,
    WorkflowName,
    WorkflowsPagePayload,
)

DEFAULT_WORKFLOWS: list[WorkflowName] = [
    "onboarding-import",
    "thematic-analysis",
    "portfolio-consultation",
    "morning-brief",
    "research-follow-up",
    "action-review",
]


def _latest_memo_summary(reports_root: Path = Path("reports")) -> MemoSummary:
    paths = sorted(reports_root.glob("daily_*.md"))
    if not paths:
        return MemoSummary()

    latest = paths[-1]
    lines = [
        line.strip() for line in latest.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    title = lines[0] if lines else latest.name
    excerpt_parts = [line for line in lines[1:] if not line.startswith("#")]
    excerpt = " ".join(excerpt_parts[:3])[:420] if excerpt_parts else None
    return MemoSummary(
        path=str(latest),
        title=title,
        excerpt=excerpt,
        updated_at=datetime.fromtimestamp(latest.stat().st_mtime, UTC).isoformat(),
    )


def _research_summary(root: Path = Path("research")) -> ResearchSummary:
    normalized_root = root / "normalized"
    log_path = root / "wiki" / "log.md"
    if not root.exists():
        return ResearchSummary(exists=False, normalized_files=0)

    files = sorted(normalized_root.glob("*/*.jsonl"), reverse=True)
    tracked_symbols = sorted({path.parent.name for path in files})[:6]
    last_log_line: str | None = None
    if log_path.exists():
        lines = [
            line.strip()
            for line in log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        last_log_line = lines[-1] if lines else None

    return ResearchSummary(
        exists=True,
        normalized_files=len(files),
        tracked_symbols=tracked_symbols,
        log_path=str(log_path) if log_path.exists() else None,
        last_log_line=last_log_line,
    )


def _staged_actions_summary(session: Session) -> StagedActionsSummary:
    actions = list_actions(session)
    pending = sum(1 for action in actions if action.status == "pending")
    confirmed = sum(1 for action in actions if action.status == "confirmed")
    discarded = sum(1 for action in actions if action.status == "discarded")
    return StagedActionsSummary(
        pending_count=pending,
        confirmed_count=confirmed,
        discarded_count=discarded,
    )


def _recommended_commands(
    workflow: WorkflowName,
    theme_request: ThemeAnalysisRequest | None,
    consult_request: PortfolioConsultRequest | None = None,
) -> list[str]:
    if workflow == "onboarding-import":
        return [
            ".venv/bin/vmarket onboard",
            ".venv/bin/vmarket import drafts",
            ".venv/bin/vmarket import show <draft-id>",
            ".venv/bin/vmarket import confirm <draft-id>",
        ]
    if workflow == "thematic-analysis":
        theme = theme_request.theme if theme_request is not None else "<theme>"
        commands = [
            ".venv/bin/vmarket portfolio show",
            ".venv/bin/vmarket cash balance",
            ".venv/bin/vmarket theme list",
        ]
        if theme_request is not None:
            command = f".venv/bin/vmarket theme analyse {theme}"
            if theme_request.amount is not None:
                command += f" --amount {theme_request.amount}"
            for company in theme_request.preferred_companies:
                command += f' --preferred-company "{company}"'
            command += f" --implementation-scope {theme_request.implementation_scope}"
            commands.append(command)
        else:
            commands.append(".venv/bin/vmarket theme discuss <theme>")
        return commands
    if workflow == "portfolio-consultation":
        commands = [
            ".venv/bin/vmarket portfolio show",
            ".venv/bin/vmarket cash balance",
            ".venv/bin/vmarket watch list",
            ".venv/bin/vmarket consult profile show",
        ]
        if consult_request is not None and consult_request.risk_score is not None:
            commands.append(
                f".venv/bin/vmarket consult portfolio --risk-score {consult_request.risk_score}"
            )
        else:
            commands.append(".venv/bin/vmarket consult portfolio")
        return commands
    if workflow == "morning-brief":
        return [
            ".venv/bin/vmarket cash balance",
            ".venv/bin/vmarket portfolio show",
            ".venv/bin/vmarket report memo",
        ]
    if workflow == "research-follow-up":
        return [
            ".venv/bin/vmarket research brief <symbol>",
            ".venv/bin/vmarket theme compare-ideas <theme> --implementation-scope both",
        ]
    return [
        ".venv/bin/vmarket portfolio show",
        ".venv/bin/vmarket watch list",
    ]


def _workflow_cards() -> list[WorkflowCard]:
    return [
        WorkflowCard(
            workflow="onboarding-import",
            title="Onboarding Import",
            summary="Set up private user data and review portfolio/watchlist import drafts.",
            route="/onboarding",
            primary_command=".venv/bin/vmarket onboard",
        ),
        WorkflowCard(
            workflow="morning-brief",
            title="Morning Brief",
            summary="Review portfolio status, memo freshness, and the day’s starting context.",
            route="/agent?workflow=morning-brief",
            primary_command=".venv/bin/vmarket report memo",
        ),
        WorkflowCard(
            workflow="thematic-analysis",
            title="Thematic Analysis",
            summary="Stress-test a theme against current holdings, sizing, and overlap.",
            route="/themes",
            primary_command=".venv/bin/vmarket theme analyse <theme>",
        ),
        WorkflowCard(
            workflow="portfolio-consultation",
            title="Portfolio Consultation",
            summary="Diagnose gaps and concentrations, then suggest 3–5 research areas.",
            route="/consult",
            primary_command=".venv/bin/vmarket consult portfolio",
        ),
        WorkflowCard(
            workflow="research-follow-up",
            title="Research Follow-up",
            summary="Review normalized evidence by symbol and connect it back to the portfolio.",
            route="/research",
            primary_command=".venv/bin/vmarket research brief <symbol>",
        ),
        WorkflowCard(
            workflow="action-review",
            title="Actions & Journal",
            summary="Inspect staged actions, pending confirmations, and decision history.",
            route="/decisions",
            primary_command=".venv/bin/vmarket cockpit export-context --workflow action-review",
        ),
    ]


def build_cockpit_overview(session: Session) -> CockpitOverviewPayload:
    snapshot = build_portfolio_snapshot_payload(session)
    data_quality_report = build_data_quality_report(session)
    themes = list_supported_themes()
    return CockpitOverviewPayload(
        portfolio_snapshot=snapshot,
        data_quality_report=data_quality_report,
        latest_memo=_latest_memo_summary(),
        research_summary=_research_summary(),
        staged_actions_summary=_staged_actions_summary(session),
        agent_summary=AgentReadySummary(
            default_workflow="thematic-analysis",
            available_workflows=DEFAULT_WORKFLOWS,
            external_harness_note=(
                "Use Codex, Claude Code, or OpenClaw as the execution harness. "
                "The cockpit prepares context and prompt packets but does not run the model."
            ),
            recommended_commands=_recommended_commands("thematic-analysis", None),
        ),
        supported_themes=themes,
    )


def build_workflows_page(session: Session) -> WorkflowsPagePayload:
    return WorkflowsPagePayload(
        workflow_cards=_workflow_cards(),
        recent_sessions=list_workflow_session_summaries(session, limit=8),
        recent_journal_entries=list_journal_entries(session, limit=8),
    )


def build_research_workspace(
    symbol: str | None = None,
    root: Path = Path("research"),
) -> tuple[ResearchWorkspaceSummary, ResearchBriefPayload | None]:
    summary = _research_summary(root=root)
    tracked = summary.tracked_symbols
    follow_ups = [
        ResearchFollowUpTask(
            symbol=tracked_symbol,
            summary=f"Review normalized evidence and unresolved questions for {tracked_symbol}.",
            source_workflow="research-follow-up",
            suggested_actions=["Open research brief", "Stage research note"],
        )
        for tracked_symbol in tracked[:6]
    ]
    workspace = ResearchWorkspaceSummary(
        tracked_symbols=tracked,
        normalized_files=summary.normalized_files,
        recent_log_line=summary.last_log_line,
        recent_follow_ups=follow_ups,
    )
    if not symbol:
        return workspace, None

    items = read_symbol_evidence(symbol, root=root)
    rendered = render_evidence_brief(symbol, items)
    return workspace, ResearchBriefPayload(
        symbol=symbol.upper(),
        rendered_markdown=rendered,
        evidence_items=items,
    )


def build_agent_context_bundle(
    session: Session,
    workflow: WorkflowName,
    theme_request: ThemeAnalysisRequest | None = None,
    consult_request: PortfolioConsultRequest | None = None,
    consult_factsheet_identifier: str | None = None,
    staged_actions: list[StagedAction] | None = None,
    workflow_session_id: int | None = None,
) -> AgentContextBundle:
    if workflow_session_id is not None:
        stored = get_workflow_session(session, workflow_session_id)
        if stored is None:
            raise ValueError(f"Unknown workflow session id: {workflow_session_id}")
        workflow = stored.workflow
        theme_input = stored.input_payload.get("theme_request")
        consult_input = stored.input_payload.get("consult_request")
        if workflow == "thematic-analysis" and theme_request is None and theme_input:
            theme_request = ThemeAnalysisRequest.model_validate(theme_input)
        if workflow == "portfolio-consultation" and consult_request is None and consult_input:
            consult_request = PortfolioConsultRequest.model_validate(consult_input)

    overview = build_cockpit_overview(session)
    action_models = (
        staged_actions if staged_actions is not None else list_actions(session, status="pending")
    )
    theme_analysis = None
    consult_diagnosis = None
    consult_factsheet = None
    if workflow == "thematic-analysis" and theme_request is not None:
        theme_analysis = analyze_theme(session, theme_request)
    if workflow == "portfolio-consultation":
        consult_diagnosis = diagnose_portfolio(session, request=consult_request)
        if consult_factsheet_identifier is not None:
            consult_factsheet = locate_factsheet(
                consult_factsheet_identifier,
                fetch_source=False,
            )
    recommended_commands = _recommended_commands(
        workflow,
        theme_request,
        consult_request=consult_request,
    )
    latest_excerpt = overview.latest_memo.excerpt
    return AgentContextBundle(
        workflow=workflow,
        generated_at=datetime.now(UTC),
        overview=overview,
        latest_memo_excerpt=latest_excerpt,
        consult_request=consult_request,
        consult_diagnosis=consult_diagnosis,
        consult_factsheet=consult_factsheet,
        theme_request=theme_request,
        theme_analysis=theme_analysis,
        staged_actions=action_models,
        recommended_commands=recommended_commands,
    )


def build_prompt_packet(bundle: AgentContextBundle) -> PromptPacket:
    workflow_titles = {
        "onboarding-import": "Virtual Market Onboarding Import Packet",
        "thematic-analysis": "Virtual Market Thematic Analysis Packet",
        "portfolio-consultation": "Virtual Market Portfolio Consultant Packet",
        "morning-brief": "Virtual Market Morning Brief Packet",
        "research-follow-up": "Virtual Market Research Follow-up Packet",
        "action-review": "Virtual Market Action Review Packet",
    }
    summary = (
        f"Workflow: {bundle.workflow}. "
        f"Portfolio base currency: {bundle.overview.portfolio_snapshot['base_currency']}."
    )
    return PromptPacket(
        workflow=bundle.workflow,
        title=workflow_titles[bundle.workflow],
        summary=summary,
        recommended_commands=bundle.recommended_commands,
        prompt_markdown=render_context_markdown(bundle),
    )


def note_context_export(session: Session, workflow_session_id: int | None) -> None:
    if workflow_session_id is None:
        return
    mark_session_exported(session, workflow_session_id)


def render_context_markdown(bundle: AgentContextBundle) -> str:
    summary = bundle.overview.portfolio_snapshot["summary"]
    cards = cast(list[dict[str, object]], summary["cards"])
    lines = [
        f"# Virtual Market Agent Context — {bundle.workflow}",
        "",
        "## Portfolio Snapshot",
        f"- Base currency: {bundle.overview.portfolio_snapshot['base_currency']}",
        f"- As of: {bundle.overview.portfolio_snapshot['as_of']}",
    ]
    for card in cards:
        lines.append(f"- {card['label']}: {card['display']}")
    issues = bundle.overview.data_quality_report.issues
    if issues:
        lines.extend(["", "## Data Quality"])
        for issue in issues:
            label = f"- {issue.label}: {issue.message}"
            if issue.symbols:
                label += f" ({', '.join(issue.symbols)})"
            lines.append(label)
    if bundle.latest_memo_excerpt:
        lines.extend(["", "## Latest Memo Excerpt", bundle.latest_memo_excerpt])
    if bundle.theme_request is not None:
        lines.extend(
            [
                "",
                "## Thematic Request",
                f"- Theme: {bundle.theme_request.theme}",
                f"- Amount: {bundle.theme_request.amount or 'unspecified'}",
                (
                    "- Preferred companies: "
                    f"{', '.join(bundle.theme_request.preferred_companies) or 'none'}"
                ),
                f"- Volatility tolerance: {bundle.theme_request.volatility_tolerance}",
                f"- Time horizon: {bundle.theme_request.time_horizon}",
                f"- Target role: {bundle.theme_request.target_role}",
            ]
        )
    if bundle.consult_diagnosis is not None:
        risk_line = (
            "- Risk score: "
            f"{bundle.consult_diagnosis.risk_score} "
            f"({bundle.consult_diagnosis.risk_score_source})"
        )
        lines.extend(
            [
                "",
                "## Consultant Diagnosis",
                risk_line,
                f"- Watchlist signals: {bundle.consult_diagnosis.watchlist_signal_count}",
            ]
        )
        for warning in bundle.consult_diagnosis.concentration_warnings[:3]:
            lines.append(f"- Concentration warning: {warning.summary}")
        for idea in bundle.consult_diagnosis.research_ideas[:5]:
            lines.append(f"- Research area: {idea.area} — {idea.summary}")
    if bundle.consult_factsheet is not None:
        lines.extend(
            [
                "",
                "## Verified Factsheet",
                f"- Identifier: {bundle.consult_factsheet.identifier}",
                f"- Fund: {bundle.consult_factsheet.fund_name}",
                f"- Source type: {bundle.consult_factsheet.source_type}",
            ]
        )
    if bundle.theme_analysis is not None:
        fit = bundle.theme_analysis.best_thematic_fit
        risk = bundle.theme_analysis.best_risk_adjusted_option
        lines.extend(
            [
                "",
                "## Existing Local Analysis",
                f"- Best thematic fit: {fit.name} ({fit.implementation_kind})",
                f"- Best risk-adjusted implementation: {risk.name} ({risk.implementation_kind})",
                f"- Main risk: {fit.recommendation.main_risk}",
                f"- What would change it: {fit.recommendation.what_would_change}",
            ]
        )
    lines.extend(["", "## Recommended CLI Commands"])
    lines.extend(f"- `{command}`" for command in bundle.recommended_commands)
    if bundle.workflow == "onboarding-import":
        lines.extend(
            [
                "",
                "## Onboarding Import Rules",
                "- Inspect portfolio/watchlist state before proposing rows.",
                "- If a screenshot draft is present, extract candidate rows into "
                "the documented import fields.",
                "- Do not confirm imports yourself unless the user explicitly approves.",
                "- Use import drafts so the user can review every row before state changes.",
            ]
        )
    return "\n".join(lines)


def render_prompt_markdown(packet: PromptPacket) -> str:
    lines = [
        f"# {packet.title}",
        "",
        packet.summary,
        "",
        "## Recommended Commands",
    ]
    lines.extend(f"- `{command}`" for command in packet.recommended_commands)
    lines.extend(["", "## Context", packet.prompt_markdown])
    return "\n".join(lines)


def render_context_json(bundle: AgentContextBundle) -> str:
    return json.dumps(bundle.model_dump(mode="json"), indent=2)
