from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import typer
import uvicorn

from vmarket.cli.common import abort, console, success
from vmarket.consult.models import PortfolioConsultRequest
from vmarket.db import get_session, init_db
from vmarket.services.workspace_service import (
    list_journal_entries,
    list_workflow_session_summaries,
)
from vmarket.themes.models import ThemeAnalysisRequest
from vmarket.web.app import create_app
from vmarket.web.context import (
    build_agent_context_bundle,
    build_prompt_packet,
    render_context_markdown,
    render_prompt_markdown,
)
from vmarket.web.models import WorkflowName

cockpit_app = typer.Typer(help="Serve the local agent cockpit and export context bundles.")


def _maybe_theme_request(
    workflow: WorkflowName,
    theme: str | None,
    amount: float | None,
    allocation_currency: str | None,
    investor_country: str,
    preferred_companies: list[str],
    volatility_tolerance: str,
    time_horizon: str,
    target_role: str,
    implementation_scope: str,
) -> ThemeAnalysisRequest | None:
    if workflow != "thematic-analysis" or not theme:
        return None
    return ThemeAnalysisRequest(
        theme=theme,
        amount=Decimal(str(amount)) if amount is not None else None,
        allocation_currency=allocation_currency,
        investor_country=investor_country,
        preferred_companies=preferred_companies,
        volatility_tolerance=volatility_tolerance,
        time_horizon=time_horizon,
        target_role=target_role,
        implementation_scope=implementation_scope,
    )


def _maybe_consult_request(
    workflow: WorkflowName,
    risk_score: int | None,
    exclusions: list[str],
    preferences: list[str],
    investment_horizon: str | None,
    amount: float | None,
    monthly_amount: float | None,
    income_preference: str | None,
    product_preferences: list[str],
    distribution_preference: str | None,
    country_jurisdiction: str | None,
    base_currency: str | None,
    prefers_uk_listed: bool | None,
    prefers_gbp_lines: bool | None,
) -> PortfolioConsultRequest | None:
    if workflow != "portfolio-consultation":
        return None
    return PortfolioConsultRequest(
        risk_score=risk_score,
        exclusions=exclusions,
        preferences=preferences,
        investment_horizon=investment_horizon,
        amount=Decimal(str(amount)) if amount is not None else None,
        monthly_amount=Decimal(str(monthly_amount)) if monthly_amount is not None else None,
        income_preference=income_preference,
        product_preferences=product_preferences,
        distribution_preference=distribution_preference,
        country_jurisdiction=country_jurisdiction,
        base_currency=base_currency,
        prefers_uk_listed=prefers_uk_listed,
        prefers_gbp_lines=prefers_gbp_lines,
    )


@cockpit_app.command("serve")
def cockpit_serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    db_path: Path | None = typer.Option(None, "--db-path"),
) -> None:
    """Run the local cockpit web app."""
    init_db(db_path)
    success(f"Cockpit available at [bold]http://{host}:{port}[/bold]")
    console.print("[dim]Use Ctrl+C to stop the local server.[/dim]")
    uvicorn.run(create_app(db_path=db_path), host=host, port=port, log_level="info")


@cockpit_app.command("export-context")
def cockpit_export_context(
    format_name: str = typer.Option("json", "--format", help="json or markdown."),
    workflow: WorkflowName = typer.Option("thematic-analysis", "--workflow"),
    theme: str | None = typer.Option(None, "--theme"),
    amount: float | None = typer.Option(None, "--amount"),
    allocation_currency: str | None = typer.Option(None, "--allocation-currency"),
    investor_country: str = typer.Option("GB", "--investor-country"),
    preferred_companies: list[str] = typer.Option([], "--preferred-company"),
    volatility_tolerance: str = typer.Option("medium", "--volatility-tolerance"),
    time_horizon: str = typer.Option("long", "--time-horizon"),
    target_role: str = typer.Option("auto", "--target-role"),
    implementation_scope: str = typer.Option("both", "--implementation-scope"),
    risk_score: int | None = typer.Option(None, "--risk-score", min=1, max=7),
    exclusions: list[str] = typer.Option([], "--exclude"),
    preferences: list[str] = typer.Option([], "--preference"),
    investment_horizon: str | None = typer.Option(None, "--investment-horizon"),
    monthly_amount: float | None = typer.Option(None, "--monthly-amount"),
    income_preference: str | None = typer.Option(None, "--income-preference"),
    product_preferences: list[str] = typer.Option([], "--product-preference"),
    distribution_preference: str | None = typer.Option(None, "--distribution-preference"),
    country_jurisdiction: str | None = typer.Option(None, "--country-jurisdiction"),
    base_currency: str | None = typer.Option(None, "--base-currency"),
    prefers_uk_listed: bool | None = typer.Option(
        None, "--prefers-uk-listed/--no-prefers-uk-listed"
    ),
    prefers_gbp_lines: bool | None = typer.Option(
        None, "--prefers-gbp-lines/--no-prefers-gbp-lines"
    ),
    factsheet_identifier: str | None = typer.Option(None, "--factsheet"),
    session_id: int | None = typer.Option(None, "--session-id"),
    include_prompt: bool = typer.Option(False, "--include-prompt"),
    db_path: Path | None = typer.Option(None, "--db-path"),
) -> None:
    """Export an agent-ready context bundle."""
    theme_request = _maybe_theme_request(
        workflow,
        theme,
        amount,
        allocation_currency,
        investor_country,
        preferred_companies,
        volatility_tolerance,
        time_horizon,
        target_role,
        implementation_scope,
    )
    consult_request = _maybe_consult_request(
        workflow,
        risk_score,
        exclusions,
        preferences,
        investment_horizon,
        amount,
        monthly_amount,
        income_preference,
        product_preferences,
        distribution_preference,
        country_jurisdiction,
        base_currency,
        prefers_uk_listed,
        prefers_gbp_lines,
    )

    init_db(db_path)
    with get_session(db_path) as session:
        try:
            bundle = build_agent_context_bundle(
                session,
                workflow=workflow,
                theme_request=theme_request,
                consult_request=consult_request,
                consult_factsheet_identifier=factsheet_identifier,
                workflow_session_id=session_id,
            )
        except ValueError as exc:
            abort(str(exc))
        packet = build_prompt_packet(bundle) if include_prompt else None

    if format_name == "json":
        payload: dict[str, object] = {"context": bundle.model_dump(mode="json")}
        if packet is not None:
            payload["prompt"] = packet.model_dump(mode="json")
        print(json.dumps(payload, indent=2))
        return
    if format_name == "markdown":
        print(render_context_markdown(bundle))
        if packet is not None:
            print("\n---\n")
            print(render_prompt_markdown(packet))
        return
    abort("Unsupported format. Use --format json or --format markdown.")


@cockpit_app.command("workflows")
def cockpit_workflows(
    limit: int = typer.Option(10, "--limit"),
    db_path: Path | None = typer.Option(None, "--db-path"),
) -> None:
    """List recent saved workflow sessions."""
    init_db(db_path)
    with get_session(db_path) as session:
        items = list_workflow_session_summaries(session, limit=limit)

    if not items:
        console.print("No saved workflow sessions yet.")
        return

    for item in items:
        console.print(
            f"- #{item.id} [{item.workflow}] {item.title} "
            f"({item.updated_at.strftime('%Y-%m-%d %H:%M')})"
        )
        if item.summary:
            console.print(f"  {item.summary}")


@cockpit_app.command("journal")
def cockpit_journal(
    limit: int = typer.Option(10, "--limit"),
    db_path: Path | None = typer.Option(None, "--db-path"),
) -> None:
    """List recent decision journal entries."""
    init_db(db_path)
    with get_session(db_path) as session:
        items = list_journal_entries(session, limit=limit)

    if not items:
        console.print("No decision journal entries yet.")
        return

    for item in items:
        console.print(
            f"- #{item.id} [{item.workflow}] {item.title} "
            f"({item.updated_at.strftime('%Y-%m-%d %H:%M')})"
        )
        console.print(f"  {item.summary}")
