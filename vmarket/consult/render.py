from __future__ import annotations

import json

from vmarket.cli.common import console, simple_table
from vmarket.consult.models import (
    ConsultantProfile,
    ConsultantRecommendation,
    FactsheetSummary,
    PortfolioDiagnosis,
)


def print_profile(profile: ConsultantProfile) -> None:
    console.print("[bold]Consultant profile[/bold]")
    console.print(f"- Risk score: {profile.risk_score or 'unset'}")
    console.print(f"- Exclusions: {', '.join(profile.exclusions) or 'none'}")
    console.print(f"- Product preferences: {', '.join(profile.product_preferences) or 'none'}")
    console.print(f"- Preference tags: {', '.join(profile.preference_tags) or 'none'}")
    console.print(f"- Horizon: {profile.investment_horizon or 'unset'}")
    console.print(f"- Distribution preference: {profile.distribution_preference or 'unset'}")
    console.print(f"- Jurisdiction: {profile.country_jurisdiction}")
    console.print(f"- Base currency: {profile.base_currency}")
    console.print(f"- Prefers UK-listed lines: {'yes' if profile.prefers_uk_listed else 'no'}")
    console.print(f"- Prefers GBP lines: {'yes' if profile.prefers_gbp_lines else 'no'}")


def print_diagnosis(diagnosis: PortfolioDiagnosis, ideas_only: bool = False) -> None:
    if not ideas_only:
        console.print("[bold]Portfolio diagnosis[/bold]")
        console.print(f"- Risk score: {diagnosis.risk_score} ({diagnosis.risk_score_source})")
        console.print(
            f"- Invested value: {diagnosis.invested_value:,.2f} {diagnosis.base_currency}"
        )
        console.print(f"- Cash: {diagnosis.cash_value:,.2f} {diagnosis.base_currency}")
        for signal in diagnosis.watchlist_signals:
            console.print(f"- Watchlist signal: {signal}")
        for summary in diagnosis.exposure_summaries:
            console.print(f"- {summary.dimension.title()}: {summary.headline}")
        if diagnosis.concentration_warnings:
            console.print("\n[bold]Concentration warnings[/bold]")
            for warning in diagnosis.concentration_warnings:
                console.print(f"- {warning.summary} {warning.details}")
        if diagnosis.gaps:
            console.print("\n[bold]Portfolio gaps[/bold]")
            for gap in diagnosis.gaps:
                console.print(f"- {gap.summary} {gap.rationale}")

    console.print("\n[bold]Research areas[/bold]")
    for idea in diagnosis.research_ideas[:5]:
        console.print(f"- {idea.area}: {idea.summary}")
        console.print(f"  Why now: {idea.why_now}")
        risk_text = ", ".join(idea.main_risks)
        if not risk_text:
            risk_text = "See factsheet and methodology before narrowing to a product."
        console.print(f"  Risks: {risk_text}")

    if diagnosis.follow_up_questions:
        console.print("\n[bold]Questions to narrow this down[/bold]")
        for question in diagnosis.follow_up_questions:
            console.print(f"- {question}")

    console.print(f"\n[dim]{diagnosis.regulated_advice_boundary}[/dim]")


def print_area_recommendation(recommendation: ConsultantRecommendation) -> None:
    console.print(f"[bold]{recommendation.selected_area}[/bold]")
    console.print(recommendation.summary)
    if recommendation.trade_offs:
        console.print("\n[bold]Trade-offs[/bold]")
        for item in recommendation.trade_offs:
            console.print(f"- {item}")
    if recommendation.what_to_research:
        console.print("\n[bold]What to research[/bold]")
        for item in recommendation.what_to_research:
            console.print(f"- {item}")
    console.print(f"\n[bold]Product guidance[/bold]\n- {recommendation.product_guidance}")
    if recommendation.verified_factsheets:
        console.print("\n[bold]Verified factsheets[/bold]")
        for factsheet in recommendation.verified_factsheets:
            console.print(f"- {factsheet.identifier}: {factsheet.fund_name}")
    if recommendation.follow_up_questions:
        console.print("\n[bold]Follow-up questions[/bold]")
        for question in recommendation.follow_up_questions:
            console.print(f"- {question}")


def print_factsheet(summary: FactsheetSummary) -> None:
    console.print(f"[bold]{summary.fund_name}[/bold] ({summary.identifier})")
    table = simple_table("Field", "Value")
    rows = [
        ("Ticker", summary.ticker or "N/A"),
        ("ISIN", summary.isin or "N/A"),
        ("TER %", f"{summary.ter_pct:.2f}" if summary.ter_pct is not None else "N/A"),
        ("OCF %", f"{summary.ocf_pct:.2f}" if summary.ocf_pct is not None else "N/A"),
        ("AUM", summary.aum_value or "N/A"),
        ("Holdings", str(summary.holdings_count or "N/A")),
        ("Distribution", summary.distribution_policy or "N/A"),
        ("Replication", summary.replication_method or "N/A"),
        ("Domicile", summary.domicile or "N/A"),
        ("Benchmark", summary.benchmark_index or "N/A"),
        ("Factsheet date", str(summary.factsheet_date or "N/A")),
        ("Source type", summary.source_type),
        ("Source URL", summary.source_url),
    ]
    for field_name, value in rows:
        table.add_row(field_name, value)
    console.print(table)
    if summary.top_holdings:
        console.print("\n[bold]Top holdings[/bold]")
        for item in summary.top_holdings[:5]:
            weight = f"{item.weight_pct:.2f}%" if item.weight_pct is not None else "N/A"
            console.print(f"- {item.name} ({weight})")
    if summary.verification_notes:
        console.print("\n[bold]Verification notes[/bold]")
        for note in summary.verification_notes:
            console.print(f"- {note}")


def print_json(payload) -> None:
    print(json.dumps(payload.model_dump(mode="json"), indent=2))
