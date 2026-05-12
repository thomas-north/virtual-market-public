from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import typer

from vmarket.cli.common import abort, success
from vmarket.consult import (
    ConsultantProfile,
    PortfolioConsultRequest,
    clear_profile,
    consult_area,
    diagnose_portfolio,
    get_profile,
    locate_factsheet,
    save_profile,
)
from vmarket.consult.render import (
    print_area_recommendation,
    print_diagnosis,
    print_factsheet,
    print_json,
    print_profile,
)
from vmarket.db import get_session

consult_app = typer.Typer(help="Portfolio-aware consultation and research direction.")
profile_app = typer.Typer(help="Manage the saved consultant profile.")
consult_app.add_typer(profile_app, name="profile")


def _request_from_options(
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
) -> PortfolioConsultRequest:
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


@profile_app.command("show")
def consult_profile_show(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show the saved consultant profile."""
    with get_session() as session:
        profile = get_profile(session)
    if json_output:
        print_json(profile)
        return
    print_profile(profile)


@profile_app.command("set")
def consult_profile_set(
    risk_score: int | None = typer.Option(None, "--risk-score", min=1, max=7),
    exclusions: list[str] = typer.Option([], "--exclude"),
    product_preferences: list[str] = typer.Option([], "--product-preference"),
    preferences: list[str] = typer.Option([], "--preference"),
    account_wrappers: list[str] = typer.Option([], "--account-wrapper"),
    investment_horizon: str | None = typer.Option(None, "--investment-horizon"),
    amount: float | None = typer.Option(None, "--amount"),
    monthly_amount: float | None = typer.Option(None, "--monthly-amount"),
    income_preference: str | None = typer.Option(None, "--income-preference"),
    distribution_preference: str | None = typer.Option(None, "--distribution-preference"),
    country_jurisdiction: str = typer.Option("UK", "--country-jurisdiction"),
    base_currency: str = typer.Option("GBP", "--base-currency"),
    prefers_uk_listed: bool = typer.Option(True, "--prefers-uk-listed/--no-prefers-uk-listed"),
    prefers_gbp_lines: bool = typer.Option(True, "--prefers-gbp-lines/--no-prefers-gbp-lines"),
) -> None:
    """Save the default consultant profile."""
    profile = ConsultantProfile(
        risk_score=risk_score,
        exclusions=exclusions,
        product_preferences=product_preferences,
        preference_tags=preferences,
        account_wrappers=account_wrappers,
        investment_horizon=investment_horizon,
        amount=Decimal(str(amount)) if amount is not None else None,
        monthly_amount=Decimal(str(monthly_amount)) if monthly_amount is not None else None,
        income_preference=income_preference,
        distribution_preference=distribution_preference,
        country_jurisdiction=country_jurisdiction,
        base_currency=base_currency.upper(),
        prefers_uk_listed=prefers_uk_listed,
        prefers_gbp_lines=prefers_gbp_lines,
    )
    with get_session() as session:
        save_profile(session, profile)
        session.commit()
    success("Consultant profile saved.")


@profile_app.command("clear")
def consult_profile_clear() -> None:
    """Clear the saved consultant profile."""
    with get_session() as session:
        clear_profile(session)
        session.commit()
    success("Consultant profile cleared.")


@consult_app.command("portfolio")
def consult_portfolio(
    risk_score: int | None = typer.Option(None, "--risk-score", min=1, max=7),
    exclusions: list[str] = typer.Option([], "--exclude"),
    preferences: list[str] = typer.Option([], "--preference"),
    investment_horizon: str | None = typer.Option(None, "--investment-horizon"),
    amount: float | None = typer.Option(None, "--amount"),
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
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Diagnose the portfolio and suggest research areas."""
    request = _request_from_options(
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
    with get_session() as session:
        diagnosis = diagnose_portfolio(session, request=request)
    if json_output:
        print_json(diagnosis)
        return
    print_diagnosis(diagnosis)


@consult_app.command("ideas")
def consult_ideas_cmd(
    risk_score: int | None = typer.Option(None, "--risk-score", min=1, max=7),
    exclusions: list[str] = typer.Option([], "--exclude"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show research areas only."""
    request = PortfolioConsultRequest(risk_score=risk_score, exclusions=exclusions)
    with get_session() as session:
        diagnosis = diagnose_portfolio(session, request=request)
    if json_output:
        print_json(diagnosis)
        return
    print_diagnosis(diagnosis, ideas_only=True)


@consult_app.command("area")
def consult_area_cmd(
    area_name: str = typer.Argument(..., help="Research area label."),
    risk_score: int | None = typer.Option(None, "--risk-score", min=1, max=7),
    exclusions: list[str] = typer.Option([], "--exclude"),
    research_root: Path = typer.Option(Path("research"), "--research-root"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Expand one research area into trade-offs and next steps."""
    request = PortfolioConsultRequest(risk_score=risk_score, exclusions=exclusions)
    with get_session() as session:
        try:
            recommendation = consult_area(
                session, area_name, request=request, research_root=research_root
            )
        except ValueError as exc:
            abort(str(exc))
    if json_output:
        print_json(recommendation)
        return
    print_area_recommendation(recommendation)


@consult_app.command("factsheet")
def consult_factsheet_cmd(
    identifier: str = typer.Argument(..., help="Ticker or verified identifier."),
    research_root: Path = typer.Option(Path("research"), "--research-root"),
    no_fetch: bool = typer.Option(False, "--no-fetch", help="Skip live source capture."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Read or fetch a verified factsheet summary."""
    try:
        summary = locate_factsheet(
            identifier,
            research_root=research_root,
            fetch_source=not no_fetch,
        )
    except ValueError as exc:
        abort(str(exc))
    if json_output:
        print_json(summary)
        return
    print_factsheet(summary)
