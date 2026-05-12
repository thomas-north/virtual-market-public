from __future__ import annotations

import json

from rich.panel import Panel

from vmarket.cli.common import console, simple_table
from vmarket.themes.models import EtfProfile, ThemeAnalysisResult, ThemeDefinition


def print_theme_analysis(result: ThemeAnalysisResult) -> None:
    fit = result.best_thematic_fit
    risk = result.best_risk_adjusted_option
    allocation = result.portfolio_context.allocation_analysis
    allocation_ratio = (
        allocation.allocation_ratio
        if allocation.allocation_ratio is not None
        else "unspecified"
    )

    console.print(
        Panel.fit(
            f"[bold]{result.theme_label}[/bold]\n{result.theme_summary}\n\n"
            f"Best thematic fit: [bold]{fit.name}[/bold] ({fit.implementation_kind})\n"
            f"Best risk-adjusted option: [bold]{risk.name}[/bold] ({risk.implementation_kind})",
            title="Thematic Analysis",
        )
    )

    console.print("[bold]Portfolio context[/bold]")
    console.print(
        f"- Invested value: {result.portfolio_context.invested_value:,.2f} "
        f"{result.portfolio_context.base_currency}"
    )
    console.print(
        f"- Visible portfolio value: {allocation.visible_portfolio_value:,.2f} "
        f"{result.portfolio_context.base_currency}"
    )
    console.print(
        "- Allocation amount: "
        f"{allocation.allocation_amount or 'unspecified'} "
        f"{allocation.allocation_currency}"
    )
    console.print(
        "- Allocation ratio: "
        f"{allocation_ratio}"
    )
    console.print(f"- Size bucket: {allocation.size_bucket}")
    console.print(f"- Suggested role: {result.portfolio_context.suggested_role}")
    console.print(f"- Theme overlap: {result.portfolio_context.theme_overlap_ratio:.0%}")
    console.print(f"- {result.portfolio_context.concentration_comment}")
    console.print(f"- {allocation.sizing_comment}")
    if result.portfolio_context.overlapping_current_holdings:
        console.print(
            "- Overlapping current holdings: "
            f"{', '.join(result.portfolio_context.overlapping_current_holdings)}"
        )

    console.print("\n[bold]Best thematic fit[/bold]")
    console.print(f"- Why it fits: {fit.recommendation.why_this_fits}")
    console.print(f"- Main risk: {fit.recommendation.main_risk}")
    console.print(f"- What would change it: {fit.recommendation.what_would_change}")
    for reason in fit.recommendation.alternatives_weaker:
        console.print(f"- Alternative weaker fit: {reason}")

    console.print("\n[bold]Best risk-adjusted implementation[/bold]")
    console.print(f"- Why it fits: {risk.recommendation.why_this_fits}")
    console.print(f"- Main risk: {risk.recommendation.main_risk}")
    console.print(f"- What would change it: {risk.recommendation.what_would_change}")
    for reason in risk.recommendation.alternatives_weaker:
        console.print(f"- Alternative weaker fit: {reason}")

    console.print("\n[bold]Why the recommendation can change[/bold]")
    console.print(result.explanation_of_why_result_changed)
    console.print(result.position_sizing_guidance)

    table = simple_table(
        "Idea",
        "Kind",
        "Fit",
        "Risk Adj",
        "Divers.",
        "Simple",
        "Convict.",
        "Rebalance",
    )
    for candidate in result.candidates:
        table.add_row(
            candidate.name,
            candidate.implementation_kind,
            f"{candidate.thematic_fit_score:.1f}",
            f"{candidate.risk_adjusted_score:.1f}",
            f"{candidate.diversification_score:.1f}",
            f"{candidate.simplicity_score:.1f}",
            f"{candidate.conviction_score:.1f}",
            f"{candidate.rebalancing_burden_score:.1f}",
        )
    console.print("\n[bold]Implementation comparison[/bold]")
    console.print(table)

    if result.etf_comparisons:
        console.print("\n[bold]ETF comparison notes[/bold]")
        for comparison in result.etf_comparisons:
            console.print(f"- {comparison.compared_against}: {comparison.weaker_fit_reason}")

    console.print("\n[bold]Warnings[/bold]")
    for warning in result.implementation_warnings:
        console.print(f"- {warning}")
    console.print(f"- {result.analysis_disclaimer}")


def print_theme_analysis_json(result: ThemeAnalysisResult) -> None:
    print(json.dumps(result.model_dump(mode="json"), indent=2))


def print_profile_comparison(matches: list[tuple[ThemeDefinition, EtfProfile]]) -> None:
    table = simple_table(
        "ETF",
        "Theme",
        "Issuer",
        "Primary Listing",
        "TER %",
        "AUM $m",
        "Liquidity",
        "Purity",
    )
    for theme, profile in matches:
        primary = next(
            (listing for listing in profile.facts.listings if listing.is_primary),
            profile.facts.listings[0] if profile.facts.listings else None,
        )
        listing = f"{primary.symbol} ({primary.currency})" if primary is not None else "N/A"
        ter = profile.facts.ter_pct or profile.facts.ocf_pct
        aum = profile.facts.aum_usd_millions
        table.add_row(
            profile.profile_id,
            theme.label,
            profile.issuer,
            listing,
            f"{ter:.2f}" if ter is not None else "N/A",
            f"{aum:.0f}" if aum is not None else "N/A",
            profile.liquidity_bucket,
            str(profile.purity_score),
        )
    console.print(table)


def print_profile_comparison_json(matches: list[tuple[ThemeDefinition, EtfProfile]]) -> None:
    payload = [
        {
            "theme": theme.model_dump(mode="json"),
            "profile": profile.model_dump(mode="json"),
        }
        for theme, profile in matches
    ]
    print(json.dumps(payload, indent=2))


def print_supported_themes(themes: list[ThemeDefinition]) -> None:
    table = simple_table("Theme ID", "Label", "ETF count", "Basket", "Keywords")
    for theme in themes:
        table.add_row(
            theme.theme_id,
            theme.label,
            str(len(theme.candidates)),
            "yes" if theme.starter_stock_basket is not None else "no",
            ", ".join(theme.keywords[:4]),
        )
    console.print(table)


def print_supported_themes_json(themes: list[ThemeDefinition]) -> None:
    print(json.dumps([theme.model_dump(mode="json") for theme in themes], indent=2))
