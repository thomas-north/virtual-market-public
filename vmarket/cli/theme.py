from __future__ import annotations

from decimal import Decimal

import typer

from vmarket.cli.common import abort
from vmarket.db import get_session
from vmarket.themes import (
    ThemeAnalysisRequest,
    analyze_theme,
    compare_etfs,
    compare_ideas,
    discuss_theme,
    list_supported_themes,
)
from vmarket.themes.render import (
    print_profile_comparison,
    print_profile_comparison_json,
    print_supported_themes,
    print_supported_themes_json,
    print_theme_analysis,
    print_theme_analysis_json,
)

theme_app = typer.Typer(help="Portfolio-aware thematic ETF and basket analysis.")


@theme_app.command("list")
def theme_list(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """List supported starter themes."""
    themes = list_supported_themes()
    if json_output:
        print_supported_themes_json(themes)
        return
    print_supported_themes(themes)


@theme_app.command("analyse")
def theme_analyse(
    theme: str = typer.Argument(..., help="Theme identifier, for example semiconductors."),
    amount: float = typer.Option(..., "--amount", help="Proposed allocation size."),
    allocation_currency: str | None = typer.Option(None, "--allocation-currency"),
    investor_country: str = typer.Option("GB", "--investor-country"),
    preferred_companies: list[str] = typer.Option(
        [],
        "--preferred-company",
        help="Repeat for each preferred company.",
    ),
    volatility_tolerance: str = typer.Option("medium", "--volatility-tolerance"),
    time_horizon: str = typer.Option("long", "--time-horizon"),
    target_role: str = typer.Option("auto", "--target-role"),
    implementation_scope: str = typer.Option("both", "--implementation-scope"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Analyse one theme against the current portfolio."""
    request = ThemeAnalysisRequest(
        theme=theme,
        amount=Decimal(str(amount)),
        allocation_currency=allocation_currency,
        investor_country=investor_country,
        preferred_companies=preferred_companies,
        volatility_tolerance=volatility_tolerance,
        time_horizon=time_horizon,
        target_role=target_role,
        implementation_scope=implementation_scope,
    )

    with get_session() as session:
        try:
            result = analyze_theme(session, request)
        except ValueError as exc:
            abort(str(exc))

    if json_output:
        print_theme_analysis_json(result)
        return
    print_theme_analysis(result)


@theme_app.command("discuss")
def theme_discuss(
    theme: str = typer.Argument(..., help="Theme identifier, for example robotics."),
    amount: float | None = typer.Option(None, "--amount", help="Optional allocation size."),
    allocation_currency: str | None = typer.Option(None, "--allocation-currency"),
    investor_country: str = typer.Option("GB", "--investor-country"),
    preferred_companies: list[str] = typer.Option([], "--preferred-company"),
    volatility_tolerance: str = typer.Option("medium", "--volatility-tolerance"),
    time_horizon: str = typer.Option("long", "--time-horizon"),
    target_role: str = typer.Option("auto", "--target-role"),
    implementation_scope: str = typer.Option("both", "--implementation-scope"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Discuss a theme without requiring a fixed allocation size."""
    request = ThemeAnalysisRequest(
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

    with get_session() as session:
        try:
            result = discuss_theme(session, request)
        except ValueError as exc:
            abort(str(exc))

    if json_output:
        print_theme_analysis_json(result)
        return
    print_theme_analysis(result)


@theme_app.command("compare-etfs")
def theme_compare_etfs(
    identifiers: list[str] = typer.Argument(..., help="ETF profile ids or listing symbols."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Compare ETF profiles from the curated starter universe."""
    try:
        matches = compare_etfs(identifiers)
    except ValueError as exc:
        abort(str(exc))

    if json_output:
        print_profile_comparison_json(matches)
        return
    print_profile_comparison(matches)


@theme_app.command("compare-ideas")
def theme_compare_ideas(
    theme: str = typer.Argument(..., help="Theme identifier."),
    amount: float | None = typer.Option(None, "--amount", help="Optional allocation size."),
    allocation_currency: str | None = typer.Option(None, "--allocation-currency"),
    investor_country: str = typer.Option("GB", "--investor-country"),
    preferred_companies: list[str] = typer.Option([], "--preferred-company"),
    volatility_tolerance: str = typer.Option("medium", "--volatility-tolerance"),
    time_horizon: str = typer.Option("long", "--time-horizon"),
    target_role: str = typer.Option("auto", "--target-role"),
    implementation_scope: str = typer.Option("both", "--implementation-scope"),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Compare ETF and basket implementations for one theme."""
    request = ThemeAnalysisRequest(
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

    with get_session() as session:
        try:
            result = compare_ideas(session, request)
        except ValueError as exc:
            abort(str(exc))

    if json_output:
        print_theme_analysis_json(result)
        return
    print_theme_analysis(result)
